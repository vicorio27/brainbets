"""Walk-forward validation for the tennis Match Winner ensemble: does
`ensemble_weights_service`'s per-regime weight fit actually generalize to
predictions it never saw, or is it fitting noise in a validated sample
that's still only in the hundreds?

Why this needs its own check, separate from the Caja's flat-stake yield:
the ensemble's weights get refit from ALL validated outcomes every time
`train_ensemble_weights` runs, and are then used to generate NEW predictions
going forward -- which is the correct day-to-day serving procedure, not a
leak by itself. What it leaves unanswered is whether the REGRESSION ITSELF
is finding something real: with only a few hundred validated outcomes and
six correlated signals (several are rank/form-derived and move together),
an NNLS fit can trade weight between two signals based on noise specific to
whatever sample it saw, in a way that looks like a better fit on that sample
but doesn't hold up on new matches.

This module answers that directly: freeze weights fit on only the EARLIEST
`cutoff_frac` of validated outcomes, and score them on the LATER portion the
fit never saw. Each validated Match Winner prediction already carries every
component model's own probability in `reasoning_data` (elo, surface_elo,
xgboost, catboost, ml, odds) -- `ensemble_weights_service._extract_row`
turns one into a training row, and this reuses that extraction and the
exact same NNLS+ridge fit (`_fit_regime`) verbatim, just on a chronological
split instead of everything at once. The held-out rows' own stored
component probabilities get recombined with the frozen train-only weights,
so scoring them needs no re-run of the feature pipeline.

Three numbers per regime, all scored on the SAME held-out rows:
  - `baseline`: the historical hardcoded constants (DEFAULT_WEIGHTS) --
    did fitting anything help at all?
  - `walkForward`: weights fit on the train portion only, frozen -- the
    honest "would this have worked going forward" number.
  - `inSample`: weights fit on train+test together (what the live service
    does today), scored on the test rows anyway -- the gap between this and
    `walkForward` is a direct measure of overfitting.
"""
import math
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from src.application.ensemble_weights_service import (
    DEFAULT_WEIGHTS,
    MIN_SAMPLES,
    MODEL_KEYS,
    _extract_row,
    _fit_regime,
)
from src.domain.models import Match, Prediction, Sport

# Below this many held-out rows, accuracy/log-loss swing too much on one or
# two matches to mean anything -- report "insufficient_data" instead of a
# number that looks precise but isn't.
MIN_TEST_SAMPLES = 15


def _weighted_prob(features: Dict[str, Optional[float]], weights: Dict[str, float]) -> float:
    """Recombine a row's stored component probabilities with a given weight
    set -- the same weighted average `ensemble_tennis` computes at predict
    time, done here against already-stored values instead of fresh signals."""
    num = 0.0
    den = 0.0
    for key in MODEL_KEYS:
        v = features.get(key)
        w = weights.get(key, 0.0)
        if v is None or w <= 0:
            continue
        num += w * v
        den += w
    return num / den if den > 0 else 0.5


def _score(rows: List[Dict[str, Any]], weights: Dict[str, float]) -> Dict[str, Any]:
    """Accuracy + log-loss of `weights` on `rows`, scored against each row's
    real outcome (`label` -- the match's actual winner, never touched by
    weight fitting)."""
    if not rows:
        return {"n": 0, "accuracy": None, "logLoss": None}
    eps = 1e-6
    correct = 0
    loss = 0.0
    for r in rows:
        p = min(max(_weighted_prob(r["features"], weights), eps), 1 - eps)
        predicted_side = 1.0 if p >= 0.5 else 0.0
        if predicted_side == r["label"]:
            correct += 1
        loss += -(r["label"] * math.log(p) + (1 - r["label"]) * math.log(1 - p))
    n = len(rows)
    return {"n": n, "accuracy": round(correct / n * 100, 2), "logLoss": round(loss / n, 4)}


def _verdict(walk_forward: Dict[str, Any], baseline: Dict[str, Any], in_sample: Dict[str, Any]) -> str:
    """Plain-language read of the three scores together, not just the raw
    numbers -- "beats the old constants" and "doesn't just overfit" are two
    different questions and both matter."""
    beats_baseline = (
        walk_forward["accuracy"] is not None
        and baseline["accuracy"] is not None
        and walk_forward["accuracy"] > baseline["accuracy"]
        and walk_forward["logLoss"] < baseline["logLoss"]
    )
    overfit_gap = (
        in_sample["accuracy"] - walk_forward["accuracy"]
        if in_sample["accuracy"] is not None and walk_forward["accuracy"] is not None
        else 0.0
    )
    if beats_baseline and overfit_gap < 5.0:
        return "generaliza: le gana a los pesos fijos en datos que nunca vio, sin caerse mucho frente al fit con todos los datos"
    if beats_baseline and overfit_gap >= 5.0:
        return "mejora sobre los pesos fijos, pero con sobreajuste notable: el fit con todos los datos luce bastante mejor que el walk-forward honesto"
    return "no generaliza todavia: no le gana a los pesos fijos hardcodeados en datos que nunca vio -- el ajuste probablemente esta memorizando ruido de la muestra"


def _load_rows(db: Session) -> List[Dict[str, Any]]:
    """Validated Match Winner training rows, oldest first."""
    raw = (
        db.query(Match.match_date, Prediction.reasoning_data, Prediction.probabilities, Prediction.status)
        .join(Match, Prediction.match_id == Match.id)
        .join(Sport, Match.sport_id == Sport.id)
        .filter(Sport.code == "tennis")
        .filter(Prediction.market == "Match Winner")
        .filter(Prediction.status.in_(["VALIDATED", "FAILED"]))
        .order_by(Match.match_date.asc())
        .all()
    )
    rows = []
    for _match_date, reasoning_data, probabilities, status in raw:
        row = _extract_row(reasoning_data, probabilities, status)
        if row is not None:
            rows.append(row)
    return rows


def walk_forward_ensemble(db: Session, cutoff_frac: float = 0.7) -> Dict[str, Any]:
    """Per regime: fit weights on the earliest `cutoff_frac` of validated
    outcomes, score them -- frozen -- on the rest, and compare against the
    hardcoded defaults and against weights fit on everything (today's live
    procedure), both scored on that same held-out set."""
    cutoff_frac = min(0.9, max(0.5, float(cutoff_frac)))
    rows = _load_rows(db)

    by_regime: Dict[str, List[Dict[str, Any]]] = {"both": [], "elo_only": [], "rank_only": []}
    for row in rows:  # `rows` is already date-ordered; filtering preserves that order.
        by_regime[row["regime"]].append(row)

    results: Dict[str, Any] = {}
    for regime, regime_rows in by_regime.items():
        n = len(regime_rows)
        split = int(n * cutoff_frac)
        train_rows, test_rows = regime_rows[:split], regime_rows[split:]
        defaults = DEFAULT_WEIGHTS[regime]

        if len(train_rows) < MIN_SAMPLES or len(test_rows) < MIN_TEST_SAMPLES:
            results[regime] = {
                "status": "insufficient_data",
                "totalSamples": n,
                "trainSamples": len(train_rows),
                "testSamples": len(test_rows),
                "note": f"hace falta >= {MIN_SAMPLES} para entrenar y >= {MIN_TEST_SAMPLES} para evaluar; "
                        "con esta cantidad el walk-forward seria ruido, no señal",
            }
            continue

        walk_forward_weights, _, _ = _fit_regime(train_rows, defaults)
        all_data_weights, _, _ = _fit_regime(regime_rows, defaults)  # today's live procedure
        walk_forward_weights = walk_forward_weights or defaults
        all_data_weights = all_data_weights or defaults

        scores = {
            "baseline": _score(test_rows, defaults),
            "walkForward": _score(test_rows, walk_forward_weights),
            "inSample": _score(test_rows, all_data_weights),
        }
        results[regime] = {
            "status": "ok",
            "totalSamples": n,
            "trainSamples": len(train_rows),
            "testSamples": len(test_rows),
            "walkForwardWeights": walk_forward_weights,
            **scores,
            "verdict": _verdict(scores["walkForward"], scores["baseline"], scores["inSample"]),
        }

    return {"cutoffFrac": cutoff_frac, "regimes": results}
