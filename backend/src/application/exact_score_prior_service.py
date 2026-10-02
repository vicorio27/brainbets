"""Empirical exact-set-score prior for tennis: the redesign of the "Exact
Set Score" market after it showed a statistically significant loss that got
WORSE, not better, as more data came in (see bankroll_service's significance
test and temporal_stability).

Why the old model needed replacing: `n8n/prediction_engine/tennis.py` built
the 6-way exact-score distribution from a pure i.i.d. binomial over sets --
every set assumed to be won with the SAME probability, independent of what
happened in the previous one. Real tennis isn't like that: a set up often
cruises, a set down often digs in, fatigue and momentum compound across a
match. An i.i.d. model systematically over-predicts clean sweeps for
favorites and under-predicts matches going the distance, which is exactly
the shape of a 21.4% hit rate at 3.57 average odds losing money both in the
first AND the second half of its validated history.

This module fits the empirical alternative instead of another theoretical
formula: conditional on how big the ranking gap is and whether the match is
best-of-3 or best-of-5, what fraction of REAL historical matches ended in
straight sets vs. went the distance? It uses the FULL historical dataset
(tennis-data.co.uk 2010+, tens of thousands of matches) rather than the
~100 live-era validated Exact Set Score outcomes -- that live sample is
nowhere near enough to fit anything new (it's exactly what revealed the old
model doesn't work, not enough to replace it on its own).

Serving: the engine fetches this artifact once per predict run (same
pattern as `ensemble_weights_service`) and blends the empirical "sets lost
by the match favorite" distribution with the ensemble's match-win
probability to build `exact_scores`, instead of the old pure i.i.d. formula.
Falls back to the i.i.d. formula for a (best_of, rank-gap) combination that
hasn't accumulated `MIN_SAMPLES_PER_BUCKET` historical matches yet.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session, aliased

from src.domain.models import League, Match, MatchCompetitor, MatchScore, Sport

logger = logging.getLogger(__name__)

PRIOR_DIR = os.environ.get("EXACT_SCORE_PRIOR_MODEL_DIR", "/storage/models")
PRIOR_PATH = os.path.join(PRIOR_DIR, "tennis_exact_score_prior.json")

MIN_SAMPLES_PER_BUCKET = 50
LAPLACE_ALPHA = 1.0

GRAND_SLAMS = ("us open", "wimbledon", "australian open", "roland garros", "french open")

# Ranking-gap buckets: how much better the favorite is on paper. Boundaries
# chosen so each bucket holds a meaningfully different "how lopsided is
# this matchup" regime, not for statistical optimality -- there isn't
# enough data to tune bucket edges without overfitting them too.
RANK_BUCKETS: List[Tuple[float, float, str]] = [
    (0, 10, "0-10"),
    (10, 25, "10-25"),
    (25, 50, "25-50"),
    (50, 100, "50-100"),
    (100, float("inf"), "100+"),
]

_cache: Dict[str, Any] = {"mtime": None, "data": None}


def _best_of(extra_data: Optional[Dict[str, Any]], tournament_name: Optional[str]) -> int:
    bo = (extra_data or {}).get("best_of")
    if bo:
        try:
            return int(bo)
        except (TypeError, ValueError):
            pass
    t = (tournament_name or "").lower()
    return 5 if any(gs in t for gs in GRAND_SLAMS) else 3


def _rank_bucket_label(rank_diff: float) -> str:
    for lo, hi, label in RANK_BUCKETS:
        if lo <= rank_diff < hi:
            return label
    return RANK_BUCKETS[-1][2]


def _smoothed_distribution(counts: Dict[int, int], best_of: int) -> Dict[str, float]:
    """Laplace-smoothed P(winner loses k sets) over k in [0, best_of // 2],
    from raw observation counts. Smoothing keeps a bucket that happens to
    have zero observations of some outcome (e.g. no sweeps seen yet) from
    serving a hard zero probability."""
    max_lost = best_of // 2
    total = sum(counts.values())
    denom = total + LAPLACE_ALPHA * (max_lost + 1)
    return {
        str(lost): round((counts.get(lost, 0) + LAPLACE_ALPHA) / denom, 4)
        for lost in range(max_lost + 1)
    }


def train_exact_score_prior(db: Session) -> Dict[str, Any]:
    """Fit the empirical "sets lost by the match winner" distribution from
    every finished tennis match with a full-time score -- historical
    ingestion (2010+) and live-collected matches alike."""
    p1 = aliased(MatchCompetitor)
    p2 = aliased(MatchCompetitor)
    rows = (
        db.query(
            MatchScore.home_score,
            MatchScore.away_score,
            Match.extra_data,
            League.name,
            p1.pre_match_ranking,
            p2.pre_match_ranking,
        )
        .select_from(MatchScore)
        .join(Match, Match.id == MatchScore.match_id)
        .join(Sport, Sport.id == Match.sport_id)
        .outerjoin(League, League.id == Match.league_id)
        .join(p1, (p1.match_id == Match.id) & (p1.side == "player1"))
        .join(p2, (p2.match_id == Match.id) & (p2.side == "player2"))
        .filter(Sport.code == "tennis")
        .filter(MatchScore.period == "FULL_TIME")
        .filter(Match.status == "FINISHED")
        .all()
    )

    # counts[bucket_key][sets_lost_by_winner] = number of matches
    counts: Dict[str, Dict[int, int]] = {}
    skipped = 0
    for home_score, away_score, extra_data, league_name, rank1, rank2 in rows:
        if home_score is None or away_score is None:
            skipped += 1
            continue
        winner_sets, loser_sets = (
            (home_score, away_score) if home_score >= away_score else (away_score, home_score)
        )
        bo = _best_of(extra_data, league_name)
        sets_to_win = bo // 2 + 1
        # A valid completed match has the winner at exactly sets_to_win and
        # the loser short of it; anything else is a retirement/walkover/bad
        # row that would corrupt the "how many sets did it take" signal.
        if winner_sets != sets_to_win or loser_sets >= sets_to_win or loser_sets < 0:
            skipped += 1
            continue

        bucket_label = (
            _rank_bucket_label(abs(rank1 - rank2)) if rank1 is not None and rank2 is not None else "unknown"
        )
        key = f"bo{bo}_{bucket_label}"
        counts.setdefault(key, {})
        counts[key][loser_sets] = counts[key].get(loser_sets, 0) + 1

    priors: Dict[str, Any] = {}
    for key, dist in counts.items():
        total = sum(dist.values())
        if total < MIN_SAMPLES_PER_BUCKET:
            continue
        bo = 5 if key.startswith("bo5") else 3
        priors[key] = {"distribution": _smoothed_distribution(dist, bo), "samples": total}

    artifact = {
        "version": 1,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "rank_buckets": [
            {"min": lo, "max": (hi if hi != float("inf") else None), "label": label}
            for lo, hi, label in RANK_BUCKETS
        ],
        "min_samples_per_bucket": MIN_SAMPLES_PER_BUCKET,
        "priors": priors,
    }
    os.makedirs(PRIOR_DIR, exist_ok=True)
    with open(PRIOR_PATH, "w") as f:
        json.dump(artifact, f, indent=2)
    _cache["mtime"] = None  # force reload

    return {
        "status": "success",
        "artifact": PRIOR_PATH,
        "matchesConsidered": len(rows),
        "matchesSkipped": skipped,
        "buckets": len(priors),
        "bucketSamples": {k: v["samples"] for k, v in sorted(priors.items())},
    }


def _load() -> Optional[Dict[str, Any]]:
    try:
        mtime = os.path.getmtime(PRIOR_PATH)
    except OSError:
        return None
    if _cache["data"] is not None and _cache["mtime"] == mtime:
        return _cache["data"]
    try:
        with open(PRIOR_PATH) as f:
            data = json.load(f)
    except Exception:
        return None
    _cache["mtime"] = mtime
    _cache["data"] = data
    return data


def get_exact_score_priors() -> Dict[str, Any]:
    """Full artifact, served as-is to the prediction engine (it picks the
    bucket for its own best_of/rank_diff -- see `n8n/prediction_engine/
    tennis.py`'s `_sets_lost_prior()`)."""
    data = _load()
    return data.get("priors", {}) if data else {}


def sets_lost_distribution(best_of: int, rank_diff: float) -> Optional[Tuple[Dict[int, float], int]]:
    """Empirical P(winner loses 0/1[/2] sets) for this (best_of, rank gap),
    falling back to the "unknown ranking" bucket for that best_of. Returns
    (distribution, sample_count), or None below `MIN_SAMPLES_PER_BUCKET`."""
    priors = get_exact_score_priors()
    if not priors:
        return None
    label = _rank_bucket_label(rank_diff)
    entry = priors.get(f"bo{best_of}_{label}") or priors.get(f"bo{best_of}_unknown")
    if not entry:
        return None
    return {int(k): v for k, v in entry["distribution"].items()}, entry["samples"]
