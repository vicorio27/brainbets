"""Anchor the model's probability to the bookmaker's price.

Audit of 2026-10-10 (452 settled bets placed before the match, with odds):
bets showing a positive calibrated edge promised +26.4% on average and
returned -6.3%; in the 20-50% edge bucket the model said 55.8%, the market
41.6%, and the real hit rate was 31.6%. The calibrated probability barely
moves inside a market (it collapses to the base rate), so `p * odds - 1`
ends up ranking bets by odds alone: "high edge" meant "underdog".

A bookmaker's price is itself a strong forecast. The probability served for
anything with odds is therefore a blend

    p = w * p_model + (1 - w) * p_market

where p_market is the implied probability with the margin removed and `w`
(how much the model is trusted against the market) is fitted per market on
settled bets by log-loss. With w = 0 the edge of every bet is minus the
bookmaker's margin, which is the honest answer when the model adds nothing.

The artifact lives next to calibration.json (no DB migration).
"""
import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session, joinedload

from src.application.calibration_service import (
    _NO_CALIBRATED_EV_MARKETS,
    _odds_for_outcome,
    calibrated_probability,
)
from src.domain.models import Match, MatchCompetitor, Prediction, PredictionResult, Sport

logger = logging.getLogger(__name__)

ANCHOR_DIR = os.environ.get("CALIBRATION_MODEL_DIR", "/storage/models")
ANCHOR_PATH = os.path.join(ANCHOR_DIR, "market_anchor.json")

# Until a market has enough settled bets its weight falls back to the sport,
# then the global fit, then this: trust the market almost entirely.
DEFAULT_MODEL_WEIGHT = 0.1
# Per-market fits on fewer bets than this were pure noise on 2026-10-10
# (Exact Set Score, n=95: 0.45 in sample, 0.0 when fitted on the first 70%).
MIN_SAMPLES = 150
# Pseudo-bets pulling the fit towards w = 0 (pure market). A few dozen real
# bets can make any weight look best by luck; the model has to earn it.
PRIOR_STRENGTH = 30.0
WEIGHT_GRID = [i / 20.0 for i in range(21)]
# Margin assumed when only the chosen selection's price is known.
DEFAULT_OVERROUND = 1.07

_cache: Dict[str, Any] = {"mtime": None, "data": None}


def _valid(odd: Any) -> Optional[float]:
    try:
        value = float(odd)
    except (TypeError, ValueError):
        return None
    return value if value > 1.0 else None


def market_probability(
    reasoning_data: Optional[Dict[str, Any]],
    chosen_odds: Optional[float],
    odds_markets: Optional[Dict[str, Any]] = None,
) -> Optional[float]:
    """Implied probability of the chosen selection with the margin removed.

    Uses every price of the same market when they are known (both players,
    over/under, or the whole Set Betting board from `odds_markets`) so the
    implied probabilities sum to 1; otherwise assumes `DEFAULT_OVERROUND`.
    """
    chosen = _valid(chosen_odds)
    if not chosen:
        return None
    odds = (reasoning_data or {}).get("oddsDecimal")
    odds = odds if isinstance(odds, dict) else {}

    board: List[float] = []
    for keys in (("player1", "player2"), ("home", "draw", "away"), ("over", "under")):
        prices = [_valid(odds.get(k)) for k in keys if k in odds]
        if len(prices) >= 2 and all(prices):
            board = [p for p in prices if p]
            break
    if not board and odds.get("key"):
        set_betting = (odds_markets or {}).get("setBetting") or {}
        prices = [_valid(v) for v in set_betting.values()]
        if len(prices) >= 3 and all(prices):
            board = [p for p in prices if p]

    overround = sum(1.0 / p for p in board) if board else DEFAULT_OVERROUND
    if overround < 1.0:  # an incomplete board would inflate the probability
        overround = DEFAULT_OVERROUND
    return min(0.99, max(0.01, (1.0 / chosen) / overround))


def model_probability(sport: Optional[str], market: Optional[str], confidence: Optional[int]) -> Optional[float]:
    """The model's own probability: calibrated, except for markets whose
    confidence is not a binary pick (Exact Set Score keeps the raw value)."""
    if confidence is None:
        return None
    raw = max(0.01, min(0.99, int(confidence) / 100.0))
    if (market or "").strip().lower() in _NO_CALIBRATED_EV_MARKETS:
        return raw
    calibrated = calibrated_probability(sport, market, confidence)
    return calibrated if calibrated is not None else raw


def _log_loss(rows: Sequence[Tuple[float, float, int]], w: float) -> float:
    total = 0.0
    for p_model, p_market, won in rows:
        p = min(0.999, max(0.001, w * p_model + (1.0 - w) * p_market))
        total -= math.log(p if won else 1.0 - p)
    return total


def fit_weight(rows: Sequence[Tuple[float, float, int]]) -> Optional[Dict[str, Any]]:
    """Best model weight for (p_model, p_market, won) rows, shrunk towards 0.

    The penalty is the log-loss the candidate would add on `PRIOR_STRENGTH`
    imaginary bets where the market was exactly right, i.e. the average extra
    loss per bet of moving away from the market, scaled.
    """
    n = len(rows)
    if n < MIN_SAMPLES:
        return None
    market_only = _log_loss(rows, 0.0)
    best_w, best_score = 0.0, market_only
    for w in WEIGHT_GRID:
        loss = _log_loss(rows, w)
        penalty = PRIOR_STRENGTH * w * w * (market_only / n) * 0.1
        if loss + penalty < best_score - 1e-9:
            best_w, best_score = w, loss + penalty
    return {
        "weight": best_w,
        "samples": n,
        "logLossMarket": round(market_only / n, 4),
        "logLossModel": round(_log_loss(rows, 1.0) / n, 4),
        "logLossBlend": round(_log_loss(rows, best_w) / n, 4),
    }


def load_training_rows(db: Session) -> List[Dict[str, Any]]:
    """Settled predictions made before the match started, with odds, oldest first."""
    query = (
        db.query(Prediction, PredictionResult, Match, Sport)
        .join(PredictionResult, PredictionResult.prediction_id == Prediction.id)
        .join(Match, Match.id == Prediction.match_id)
        .join(Sport, Sport.id == Match.sport_id)
        .options(
            joinedload(Prediction.match)
            .joinedload(Match.competitors)
            .joinedload(MatchCompetitor.competitor)
        )
        .filter(PredictionResult.is_successful.isnot(None))
        .filter(Prediction.created_at < Match.match_date)
        .order_by(Match.match_date.asc(), Prediction.id.asc())
    )
    rows = []
    for prediction, result, match, sport in query.all():
        home = away = None
        for mc in match.competitors:
            name = mc.competitor.name if mc.competitor else None
            if mc.side in ("home", "player1"):
                home = name
            elif mc.side in ("away", "player2"):
                away = name
        odds = _odds_for_outcome(prediction.reasoning_data, prediction.predicted_outcome, home, away)
        p_market = market_probability(
            prediction.reasoning_data, odds, (match.extra_data or {}).get("odds_markets")
        )
        p_model = model_probability(sport.code, prediction.market, prediction.confidence)
        if not odds or p_market is None or p_model is None:
            continue
        rows.append(
            {
                "sport": sport.code,
                "market": prediction.market,
                "date": match.match_date,
                "odds": odds,
                "pModel": p_model,
                "pMarket": p_market,
                "won": 1 if result.is_successful else 0,
            }
        )
    return rows


def train_market_anchor(db: Session) -> Dict[str, Any]:
    """Fit the model weight per (sport, market), per sport and globally."""
    rows = load_training_rows(db)

    def _triples(items):
        return [(r["pModel"], r["pMarket"], r["won"]) for r in items]

    by_market: Dict[str, List[Dict[str, Any]]] = {}
    by_sport: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_market.setdefault(f"{r['sport']}|{r['market']}", []).append(r)
        by_sport.setdefault(r["sport"], []).append(r)

    markets = {k: fit for k, v in sorted(by_market.items()) if (fit := fit_weight(_triples(v)))}
    sports = {k: fit for k, v in sorted(by_sport.items()) if (fit := fit_weight(_triples(v)))}
    artifact = {
        "version": 1,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "min_samples": MIN_SAMPLES,
        "prior_strength": PRIOR_STRENGTH,
        "default_weight": DEFAULT_MODEL_WEIGHT,
        "markets": markets,
        "sports": sports,
        "global": fit_weight(_triples(rows)),
    }
    os.makedirs(ANCHOR_DIR, exist_ok=True)
    with open(ANCHOR_PATH, "w") as f:
        json.dump(artifact, f, indent=2)
    _cache["mtime"] = None
    _cache["data"] = None
    return {"status": "success", "artifact": ANCHOR_PATH, "total_outcomes": len(rows), **{
        k: artifact[k] for k in ("markets", "sports", "global")
    }}


def _load() -> Optional[Dict[str, Any]]:
    try:
        mtime = os.path.getmtime(ANCHOR_PATH)
    except OSError:
        return None
    if _cache["data"] is not None and _cache["mtime"] == mtime:
        return _cache["data"]
    try:
        with open(ANCHOR_PATH) as f:
            data = json.load(f)
    except Exception:
        return None
    _cache["mtime"] = mtime
    _cache["data"] = data
    return data


def model_weight(sport: Optional[str], market: Optional[str]) -> float:
    """How much the model counts against the market: market -> sport -> global -> default."""
    data = _load() or {}
    for fit in (
        (data.get("markets") or {}).get(f"{sport}|{market}"),
        (data.get("sports") or {}).get(sport or ""),
        data.get("global"),
    ):
        if fit and fit.get("weight") is not None:
            return float(fit["weight"])
    return DEFAULT_MODEL_WEIGHT


def anchored_probability(
    sport: Optional[str],
    market: Optional[str],
    confidence: Optional[int],
    reasoning_data: Optional[Dict[str, Any]],
    chosen_odds: Optional[float],
    odds_markets: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, float]]:
    """Blend of the model and the no-margin market probability for one pick.

    Returns None when the pick has no usable odds: the caller keeps the
    model's probability, there is no market to anchor to.
    """
    p_market = market_probability(reasoning_data, chosen_odds, odds_markets)
    p_model = model_probability(sport, market, confidence)
    if p_market is None or p_model is None:
        return None
    w = model_weight(sport, market)
    p = w * p_model + (1.0 - w) * p_market
    return {
        "probability": p,
        "modelProbability": p_model,
        "marketProbability": p_market,
        "modelWeight": w,
        "edge": p * float(chosen_odds) - 1.0,
    }
