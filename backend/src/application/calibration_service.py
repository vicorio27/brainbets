"""Calibration service for BrainBets predictions.

Computes binned calibration curves from validated prediction outcomes
(VALIDATED/FAILED) and applies them to served predictions so the confidence
numbers users see match historical reality (e.g. when the model says 90%,
how often did it actually win?).

Design notes:
- Curves are computed per (sport, market) with fallbacks to per-sport and
  global when samples are scarce (MIN_SAMPLES per curve).
- Bins are [0-60), [60-70), [70-80), [80-90), [90-100]. Laplace smoothing
  (alpha=10, prior=curve overall rate) avoids extreme rates on tiny bins.
- The artifact is stored as JSON in the models dir (same pattern as the
  tennis XGBoost artifact) so retraining does not require a DB migration.
"""
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from src.domain.models import Match, Prediction, Sport

logger = logging.getLogger(__name__)

CALIBRATION_DIR = os.environ.get("CALIBRATION_MODEL_DIR", "/storage/models")
CALIBRATION_PATH = os.path.join(CALIBRATION_DIR, "calibration.json")

BINS: List[Tuple[int, int]] = [(0, 60), (60, 70), (70, 80), (80, 90), (90, 101)]
MIN_SAMPLES = 30
SMOOTHING_ALPHA = 10.0

# Simple in-process cache: reload when the artifact mtime changes.
_cache: Dict[str, Any] = {"mtime": None, "data": None}


def _bin_index(confidence: int) -> int:
    for i, (lo, hi) in enumerate(BINS):
        if lo <= confidence < hi:
            return i
    return len(BINS) - 1


def _fit_curve(pairs: List[Tuple[int, int]]) -> Optional[Dict[str, Any]]:
    """Fit one binned curve from (confidence, outcome) pairs."""
    n = len(pairs)
    if n < MIN_SAMPLES:
        return None
    outcomes = [o for _, o in pairs]
    if all(o == outcomes[0] for o in outcomes):
        return None  # single-class: nothing to calibrate
    prior = sum(outcomes) / n

    bin_rates: List[Optional[float]] = []
    bin_counts: List[int] = []
    for lo, hi in BINS:
        in_bin = [(c, o) for c, o in pairs if lo <= c < hi]
        wins = sum(o for _, o in in_bin)
        cnt = len(in_bin)
        rate = (wins + SMOOTHING_ALPHA * prior) / (cnt + SMOOTHING_ALPHA) if cnt or prior else prior
        bin_rates.append(round(rate, 4))
        bin_counts.append(cnt)

    return {
        "bin_rates": bin_rates,
        "bin_counts": bin_counts,
        "samples": n,
        "base_rate": round(prior, 4),
    }


def train_calibration(db: Session) -> Dict[str, Any]:
    """Compute calibration curves from validated predictions and persist them."""
    rows = (
        db.query(Prediction.confidence, Prediction.status, Prediction.market, Sport.code)
        .join(Match, Prediction.match_id == Match.id)
        .join(Sport, Match.sport_id == Sport.id)
        .filter(Prediction.status.in_(["VALIDATED", "FAILED"]))
        .all()
    )

    by_market: Dict[Tuple[str, str], List[Tuple[int, int]]] = {}
    by_sport: Dict[str, List[Tuple[int, int]]] = {}
    overall: List[Tuple[int, int]] = []
    for confidence, status, market, sport_code in rows:
        outcome = 1 if status == "VALIDATED" else 0
        pair = (int(confidence or 0), outcome)
        by_market.setdefault((sport_code, market), []).append(pair)
        by_sport.setdefault(sport_code, []).append(pair)
        overall.append(pair)

    curves: Dict[str, Any] = {}
    for (sport_code, market), pairs in sorted(by_market.items()):
        curve = _fit_curve(pairs)
        if curve:
            curves[f"{sport_code}|{market}"] = curve
    sport_curves: Dict[str, Any] = {}
    for sport_code, pairs in sorted(by_sport.items()):
        curve = _fit_curve(pairs)
        if curve:
            sport_curves[sport_code] = curve
    global_curve = _fit_curve(overall)

    artifact = {
        "version": 1,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "bins": [[lo, hi] for lo, hi in BINS],
        "min_samples": MIN_SAMPLES,
        "smoothing_alpha": SMOOTHING_ALPHA,
        "curves": curves,
        "sport_curves": sport_curves,
        "global_curve": global_curve,
    }
    os.makedirs(CALIBRATION_DIR, exist_ok=True)
    with open(CALIBRATION_PATH, "w") as f:
        json.dump(artifact, f, indent=2)
    _cache["mtime"] = None  # force reload
    _cache["data"] = None

    return {
        "status": "success",
        "artifact": CALIBRATION_PATH,
        "total_outcomes": len(overall),
        "market_curves": len(curves),
        "sport_curves": len(sport_curves),
        "global": bool(global_curve),
    }


def _load() -> Optional[Dict[str, Any]]:
    try:
        mtime = os.path.getmtime(CALIBRATION_PATH)
    except OSError:
        return None
    if _cache["data"] is not None and _cache["mtime"] == mtime:
        return _cache["data"]
    try:
        with open(CALIBRATION_PATH) as f:
            data = json.load(f)
    except Exception:
        return None
    _cache["mtime"] = mtime
    _cache["data"] = data
    return data


def calibrated_probability(sport: Optional[str], market: Optional[str], confidence: Optional[int]) -> Optional[float]:
    """Map a raw confidence to a calibrated probability using the best curve.

    Falls back market -> sport -> global -> None (caller keeps the raw value).
    """
    if confidence is None:
        return None
    data = _load()
    if not data:
        return None
    conf = max(0, min(100, int(confidence)))
    idx = _bin_index(conf)
    for curve in (
        (data.get("curves") or {}).get(f"{sport}|{market}"),
        (data.get("sport_curves") or {}).get(sport or ""),
        data.get("global_curve"),
    ):
        if curve and curve.get("bin_rates"):
            rate = curve["bin_rates"][idx]
            if rate is not None:
                return float(rate)
    return None


# Markets whose "confidence" is not a Match-Winner-style binary probability
# (Exact Set Score is a 6-way market — its low "confidence" fed through a
# binary calibration curve produces nonsense EV). Keep the raw EV for these.
_NO_CALIBRATED_EV_MARKETS = {"exact set score"}


def _odds_for_outcome(
    reasoning_data: Optional[Dict[str, Any]],
    predicted_outcome: Optional[str],
    home_name: Optional[str],
    away_name: Optional[str],
) -> Optional[float]:
    """Find the decimal odds for the predicted outcome inside reasoning_data."""
    if not reasoning_data or not predicted_outcome:
        return None
    odds = reasoning_data.get("oddsDecimal")
    if not isinstance(odds, dict):
        return None
    outcome = predicted_outcome.strip()
    # Football 1X2 keys.
    if "home" in odds or "draw" in odds or "away" in odds:
        if outcome.lower() == "draw":
            value = odds.get("draw")
        elif home_name and outcome == home_name:
            value = odds.get("home")
        elif away_name and outcome == away_name:
            value = odds.get("away")
        else:
            value = None
    # Tennis Home/Away keys (player1 = home side).
    elif "player1" in odds or "player2" in odds:
        if home_name and outcome == home_name:
            value = odds.get("player1")
        elif away_name and outcome == away_name:
            value = odds.get("player2")
        else:
            value = None
    # Markets whose outcome isn't a player name (Total Sets, Exact Set Score):
    # the engine puts the chosen selection's odd under "chosen".
    elif "chosen" in odds:
        value = odds.get("chosen")
    else:
        value = None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value > 1.0 else None


def apply_calibration(
    sport: Optional[str],
    market: Optional[str],
    confidence: Optional[int],
    reasoning_data: Optional[Dict[str, Any]],
    predicted_outcome: Optional[str],
    home_name: Optional[str],
    away_name: Optional[str],
) -> Tuple[Optional[int], Optional[float]]:
    """Return (calibrated_confidence, calibrated_expected_value) for serving.

    The calibrated EV recomputes p*odds-1 with the calibrated probability when
    the outcome's odds are available in reasoning_data.
    """
    prob = calibrated_probability(sport, market, confidence)
    if prob is None:
        return None, None
    calibrated_conf = max(1, min(99, int(round(prob * 100))))
    odds = _odds_for_outcome(reasoning_data, predicted_outcome, home_name, away_name)
    calibrated_ev = (
        round(prob * odds - 1.0, 4)
        if odds and (market or "").strip().lower() not in _NO_CALIBRATED_EV_MARKETS
        else None
    )
    return calibrated_conf, calibrated_ev
