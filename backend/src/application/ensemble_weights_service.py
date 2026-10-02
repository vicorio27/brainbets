"""Data-driven ensemble weights for the tennis prediction engine.

`n8n/prediction_engine/tennis.py::ensemble_tennis` combines six signals
(surface Elo, general Elo, the two "-like" heuristics, the trained ML model
and market odds) with hand-picked weights that vary by data-availability
regime (whether real Elo/surface-Elo ratings exist for both players). This
module fits those weights instead from validated/failed Match Winner outcomes
already sitting in `predictions.reasoning_data`, using the same
train/artifact/serve pattern as `calibration_service.py`: a JSON file under
the models dir, an internal retrain endpoint, and a cached loader the
prediction engine calls over HTTP (falling back to the historical constants
when a regime hasn't accumulated enough validated outcomes yet).
"""
import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from scipy.optimize import nnls
from sqlalchemy.orm import Session

from src.domain.models import Match, Prediction, Sport

logger = logging.getLogger(__name__)

WEIGHTS_DIR = os.environ.get("ENSEMBLE_WEIGHTS_MODEL_DIR", "/storage/models")
WEIGHTS_PATH = os.path.join(WEIGHTS_DIR, "tennis_ensemble_weights.json")

MODEL_KEYS = ("surface_elo", "elo", "xgboost", "catboost", "ml", "odds")
MIN_SAMPLES = 30

# Ridge shrinkage (Tikhonov, via augmented rows) pulling fitted weights toward
# DEFAULT_WEIGHTS, in "equivalent pseudo-samples". The six signals are
# correlated (rank/form-derived), so with only a few dozen real samples a raw
# least-squares fit can zero out a perfectly good signal (e.g. real Elo) just
# because another correlated signal explained the same variance marginally
# better in that particular sample. This keeps early fits close to the
# historical constants and lets them drift only as more data accumulates.
#
# 100 was picked empirically via ensemble_walkforward_service.py, not chosen
# up front: the original value of 20 was shown by the walk-forward check to
# actively lose to the hardcoded DEFAULT_WEIGHTS on held-out data at every
# tested cutoff (-4 to -6 points of accuracy on the "both" regime's ~230
# validated outcomes) -- the fit was real, but it didn't generalize, meaning
# 20 pseudo-samples wasn't enough shrinkage for how few real samples exist
# so far. 100 was the smallest value in a sweep (20/50/100/200/400/800/1600)
# that stopped losing to the baseline across most cutoffs while still
# letting the real data move the weights (200+ converges to indistinguishable
# from the defaults given today's sample sizes). Re-run the walk-forward
# check (GET /internal/validate/tennis-ensemble-walkforward) after the
# validated sample grows substantially -- the right shrinkage shrinks as the
# real sample does.
PRIOR_STRENGTH = 100.0

# The constants that were hardcoded in `ensemble_tennis` before weights became
# data-driven. Served as-is for a regime until it has >= MIN_SAMPLES complete
# validated outcomes (all six signals present) to fit from.
DEFAULT_WEIGHTS: Dict[str, Dict[str, float]] = {
    "both": {"surface_elo": 0.25, "elo": 0.20, "xgboost": 0.10, "catboost": 0.10, "ml": 0.20, "odds": 0.15},
    "elo_only": {"surface_elo": 0.15, "elo": 0.20, "xgboost": 0.15, "catboost": 0.10, "ml": 0.25, "odds": 0.15},
    "rank_only": {"surface_elo": 0.10, "elo": 0.10, "xgboost": 0.15, "catboost": 0.15, "ml": 0.25, "odds": 0.25},
}

_cache: Dict[str, Any] = {"mtime": None, "data": None}


def _regime(reasoning_data: Dict[str, Any]) -> str:
    has_elo = reasoning_data.get("eloSource") == "real"
    has_surface_elo = reasoning_data.get("surfaceEloSource") == "real"
    if has_elo and has_surface_elo:
        return "both"
    if has_elo:
        return "elo_only"
    return "rank_only"


def _extract_row(
    reasoning_data: Optional[Dict[str, Any]],
    probabilities: Optional[Dict[str, Any]],
    pred_status: str,
) -> Optional[Dict[str, Any]]:
    """Turn one Match Winner prediction into a training row, or None if unusable."""
    if not reasoning_data or reasoning_data.get("model") != "ensemble":
        return None
    p1 = (probabilities or {}).get("player1")
    p2 = (probabilities or {}).get("player2")
    if p1 is None or p2 is None:
        return None
    predicted_side = "player1" if p1 >= p2 else "player2"
    if pred_status == "VALIDATED":
        actual_side = predicted_side
    elif pred_status == "FAILED":
        actual_side = "player2" if predicted_side == "player1" else "player1"
    else:
        return None

    def _side1(key: str) -> Optional[float]:
        block = reasoning_data.get(key)
        if not isinstance(block, dict):
            return None
        value = block.get("player1")
        return float(value) if value is not None else None

    features = {key: _side1(key) for key in MODEL_KEYS}
    if any(features[key] is None for key in ("surface_elo", "elo", "xgboost", "catboost")):
        return None

    return {
        "regime": _regime(reasoning_data),
        "features": features,
        "label": 1.0 if actual_side == "player1" else 0.0,
    }


def _fit_regime(rows: List[Dict[str, Any]], defaults: Dict[str, float]) -> Tuple[Dict[str, float], int, str]:
    """Fit non-negative weights minimizing squared error of the ensemble's
    weighted-average probability against the actual outcome, ridge-shrunk
    toward `defaults` (see PRIOR_STRENGTH).

    Only rows where all six signals are present are used, so the fitted
    weights stay directly comparable to the units `weighted_average` already
    combines (raw win probabilities, not logits).
    """
    complete = [r for r in rows if all(r["features"][k] is not None for k in MODEL_KEYS)]
    n = len(complete)
    if n < MIN_SAMPLES:
        return {}, n, "insufficient_samples"

    a_matrix = [[r["features"][k] for k in MODEL_KEYS] for r in complete]
    b_vector = [r["label"] for r in complete]

    scale = math.sqrt(PRIOR_STRENGTH)
    for i, key in enumerate(MODEL_KEYS):
        prior_row = [0.0] * len(MODEL_KEYS)
        prior_row[i] = scale
        a_matrix.append(prior_row)
        b_vector.append(scale * defaults[key])

    solution, _residual = nnls(a_matrix, b_vector)
    total = float(sum(solution))
    if total <= 1e-9:
        return {}, n, "degenerate_fit"

    weights = {k: round(float(w) / total, 4) for k, w in zip(MODEL_KEYS, solution)}
    return weights, n, "fitted"


def train_ensemble_weights(db: Session) -> Dict[str, Any]:
    """Recompute per-regime tennis ensemble weights from validated outcomes."""
    rows_raw = (
        db.query(Prediction.reasoning_data, Prediction.probabilities, Prediction.status)
        .join(Match, Prediction.match_id == Match.id)
        .join(Sport, Match.sport_id == Sport.id)
        .filter(Sport.code == "tennis")
        .filter(Prediction.market == "Match Winner")
        .filter(Prediction.status.in_(["VALIDATED", "FAILED"]))
        .all()
    )

    by_regime: Dict[str, List[Dict[str, Any]]] = {"both": [], "elo_only": [], "rank_only": []}
    skipped = 0
    for reasoning_data, probabilities, pred_status in rows_raw:
        row = _extract_row(reasoning_data, probabilities, pred_status)
        if row is None:
            skipped += 1
            continue
        by_regime[row["regime"]].append(row)

    regimes: Dict[str, Any] = {}
    for regime, rows in by_regime.items():
        weights, n, source = _fit_regime(rows, DEFAULT_WEIGHTS[regime])
        regimes[regime] = {
            "weights": weights or DEFAULT_WEIGHTS[regime],
            "samples": n,
            "source": source,
        }

    artifact = {
        "version": 1,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "min_samples": MIN_SAMPLES,
        "model_keys": list(MODEL_KEYS),
        "regimes": regimes,
    }
    os.makedirs(WEIGHTS_DIR, exist_ok=True)
    with open(WEIGHTS_PATH, "w") as f:
        json.dump(artifact, f, indent=2)
    _cache["mtime"] = None
    _cache["data"] = None

    return {
        "status": "success",
        "artifact": WEIGHTS_PATH,
        "total_outcomes": len(rows_raw),
        "skipped": skipped,
        "regimes": {k: {"weights": v["weights"], "samples": v["samples"], "source": v["source"]} for k, v in regimes.items()},
    }


def _load() -> Optional[Dict[str, Any]]:
    try:
        mtime = os.path.getmtime(WEIGHTS_PATH)
    except OSError:
        return None
    if _cache["data"] is not None and _cache["mtime"] == mtime:
        return _cache["data"]
    try:
        with open(WEIGHTS_PATH) as f:
            data = json.load(f)
    except Exception:
        return None
    _cache["mtime"] = mtime
    _cache["data"] = data
    return data


def get_ensemble_weights() -> Dict[str, Dict[str, float]]:
    """Current per-regime weights: fitted values, falling back to the
    historical hardcoded constants for any regime without enough data."""
    data = _load()
    regimes = (data or {}).get("regimes", {})
    return {
        regime: (regimes.get(regime) or {}).get("weights") or defaults
        for regime, defaults in DEFAULT_WEIGHTS.items()
    }
