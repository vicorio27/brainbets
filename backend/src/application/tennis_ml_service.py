"""Tennis machine learning model training service.

Trains an XGBoost classifier on historical tennis matches using Elo, surface
Elo, ranking and form features. The trained model is persisted to disk so the
backend can expose an inference endpoint for the n8n prediction engine.
"""
import json
import os
import pickle
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session, joinedload

from src.domain.models import CompetitorEloHistory, Match, MatchCompetitor, Sport


MODEL_DIR = os.environ.get("TENNIS_ML_MODEL_DIR", "/storage/models")
MODEL_PATH = os.path.join(MODEL_DIR, "tennis_xgb.pkl")
METADATA_PATH = os.path.join(MODEL_DIR, "tennis_xgb_metadata.json")

# Cap training set size to keep training fast in memory.
MAX_TRAINING_MATCHES = int(os.environ.get("TENNIS_ML_MAX_MATCHES", "15000"))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _parse_surface(match: Match) -> Optional[str]:
    if not match.extra_data:
        return None
    surface = match.extra_data.get("surface")
    if surface:
        return str(surface).lower()
    return None


def _load_elo_index(
    db: Session, competitor_ids: List[Any]
) -> Dict[Any, List[Tuple[datetime, Optional[str], float]]]:
    """Bulk load Elo history and index by competitor -> [(calculated_at, surface, elo)]."""
    rows = (
        db.query(CompetitorEloHistory)
        .filter(CompetitorEloHistory.competitor_id.in_(competitor_ids))
        .order_by(CompetitorEloHistory.calculated_at)
        .all()
    )
    index: Dict[Any, List[Tuple[datetime, Optional[str], float]]] = defaultdict(list)
    for row in rows:
        elo = float(row.elo_before) if row.elo_before else None
        if elo is None:
            continue
        index[row.competitor_id].append((row.calculated_at, row.surface, elo))
    return index


def _get_elo_before(
    elo_index: Dict[Any, List[Tuple[datetime, Optional[str], float]]],
    competitor_id: Any,
    before_date: datetime,
    surface: Optional[str] = None,
) -> Optional[float]:
    """Return the most recent Elo rating for a competitor before a match date."""
    entries = elo_index.get(competitor_id, [])
    if not entries:
        return None

    # Surface-specific lookup.
    if surface:
        surface_entries = [e for e in entries if e[1] == surface]
        if surface_entries:
            idx = bisect_right(surface_entries, before_date, key=lambda x: x[0])
            if idx:
                return surface_entries[idx - 1][2]

    # General lookup (surface is None).
    general_entries = [e for e in entries if e[1] is None]
    if general_entries:
        idx = bisect_right(general_entries, before_date, key=lambda x: x[0])
        if idx:
            return general_entries[idx - 1][2]
    return None


def _match_full_time_score(match: Match) -> Optional[Tuple[int, int]]:
    """Return (home_score, away_score) from the FULL_TIME MatchScore row."""
    for score in match.scores or []:
        if score.period == "FULL_TIME":
            return (score.home_score or 0, score.away_score or 0)
    return None


def _load_recent_records(
    matches: List[Match],
) -> Tuple[
    Dict[Any, List[Tuple[datetime, Optional[str], int, int]]],
    Dict[Any, List[Tuple[datetime, Optional[str], int, int]]],
]:
    """Build per-competitor match histories: list of (date, surface, won, lost).

    Returns two dicts: all-surface history and surface-specific history.
    """
    all_history: Dict[Any, List[Tuple[datetime, Optional[str], int, int]]] = defaultdict(list)
    surface_history: Dict[Any, List[Tuple[datetime, Optional[str], int, int]]] = defaultdict(list)

    for match in matches:
        if match.status != "FINISHED":
            continue
        competitors = list(match.competitors)
        if len(competitors) != 2:
            continue
        full_time = _match_full_time_score(match)
        if full_time is None:
            continue
        home_score, away_score = full_time
        if home_score == away_score:
            continue

        # Map sides to home/away. Player1 is treated as home; if sides are
        # missing we fall back to competitor order.
        by_side = {c.side: c for c in competitors}
        home_comp = by_side.get("player1") or competitors[0]
        away_comp = by_side.get("player2") or competitors[1]
        surface = _parse_surface(match)
        date = match.match_date

        all_history[home_comp.competitor_id].append(
            (date, None, 1 if home_score > away_score else 0, 1 if home_score < away_score else 0)
        )
        all_history[away_comp.competitor_id].append(
            (date, None, 1 if away_score > home_score else 0, 1 if away_score < home_score else 0)
        )
        if surface:
            surface_history[home_comp.competitor_id].append(
                (date, surface, 1 if home_score > away_score else 0, 1 if home_score < away_score else 0)
            )
            surface_history[away_comp.competitor_id].append(
                (date, surface, 1 if away_score > home_score else 0, 1 if away_score < home_score else 0)
            )

    for competitor_id, entries in all_history.items():
        entries.sort(key=lambda x: x[0])
    for competitor_id, entries in surface_history.items():
        entries.sort(key=lambda x: x[0])

    return all_history, surface_history


def _recent_win_rate(
    history: List[Tuple[datetime, Optional[str], int, int]],
    before_date: datetime,
    limit: int = 10,
) -> float:
    """Return recent win rate from a sorted history list before a given date."""
    relevant = [h for h in history if h[0] < before_date]
    recent = relevant[-limit:]
    if not recent:
        return 0.5
    wins = sum(h[2] for h in recent)
    total = len(recent)
    return wins / total


def _days_since_last_match(
    history: List[Tuple[datetime, Optional[str], int, int]],
    before_date: datetime,
) -> Optional[float]:
    """Return days since the competitor's last finished match."""
    relevant = [h for h in history if h[0] < before_date]
    if not relevant:
        return None
    return (before_date - relevant[-1][0]).days


def _matches_in_window(
    history: List[Tuple[datetime, Optional[str], int, int]],
    before_date: datetime,
    days: int,
) -> int:
    """Count finished matches in the N days before a given date."""
    since = before_date - timedelta(days=days)
    return sum(1 for h in history if since <= h[0] < before_date)


def _build_feature_row(
    match: Match,
    p1: MatchCompetitor,
    p2: MatchCompetitor,
    elo_index: Dict[Any, List[Tuple[datetime, Optional[str], float]]],
    all_history: Dict[Any, List[Tuple[datetime, Optional[str], int, int]]],
    surface_history: Dict[Any, List[Tuple[datetime, Optional[str], int, int]]],
) -> Optional[Dict[str, Any]]:
    """Build a feature row + label for one finished tennis match."""
    if match.status != "FINISHED" or not p1 or not p2:
        return None

    full_time = _match_full_time_score(match)
    if full_time is None:
        return None
    home_score, away_score = full_time
    if home_score == away_score:
        return None

    before_date = match.match_date
    surface = _parse_surface(match)

    p1_elo = _get_elo_before(elo_index, p1.competitor_id, before_date)
    p2_elo = _get_elo_before(elo_index, p2.competitor_id, before_date)

    if p1_elo is None or p2_elo is None:
        return None

    p1_surface_elo = _get_elo_before(elo_index, p1.competitor_id, before_date, surface=surface)
    p2_surface_elo = _get_elo_before(elo_index, p2.competitor_id, before_date, surface=surface)

    p1_rank = p1.pre_match_ranking or 1000
    p2_rank = p2.pre_match_ranking or 1000

    p1_all_hist = all_history.get(p1.competitor_id, [])
    p2_all_hist = all_history.get(p2.competitor_id, [])
    p1_surf_hist = surface_history.get(p1.competitor_id, [])
    p2_surf_hist = surface_history.get(p2.competitor_id, [])

    # Label = 1 if player1 (home side) won.
    label = 1 if home_score > away_score else 0

    return {
        "elo_diff": p1_elo - p2_elo,
        "surface_elo_diff": (p1_surface_elo or p1_elo) - (p2_surface_elo or p2_elo),
        "rank_diff": p2_rank - p1_rank,
        "p1_recent_win_rate": _recent_win_rate(p1_all_hist, before_date),
        "p2_recent_win_rate": _recent_win_rate(p2_all_hist, before_date),
        "surface_p1_recent_win_rate": _recent_win_rate(p1_surf_hist, before_date),
        "surface_p2_recent_win_rate": _recent_win_rate(p2_surf_hist, before_date),
        "p1_days_since_last_match": _days_since_last_match(p1_all_hist, before_date),
        "p2_days_since_last_match": _days_since_last_match(p2_all_hist, before_date),
        "p1_matches_last_30_days": _matches_in_window(p1_all_hist, before_date, 30),
        "p2_matches_last_30_days": _matches_in_window(p2_all_hist, before_date, 30),
        "label": label,
    }


def _extract_features(row: Dict[str, Any]) -> List[float]:
    return [
        row["elo_diff"],
        row["surface_elo_diff"],
        row["rank_diff"],
        row["p1_recent_win_rate"],
        row["p2_recent_win_rate"],
        row["surface_p1_recent_win_rate"],
        row["surface_p2_recent_win_rate"],
        _safe_float(row.get("p1_days_since_last_match"), 7.0),
        _safe_float(row.get("p2_days_since_last_match"), 7.0),
        _safe_float(row.get("p1_matches_last_30_days"), 2.0),
        _safe_float(row.get("p2_matches_last_30_days"), 2.0),
    ]


FEATURE_NAMES = [
    "elo_diff",
    "surface_elo_diff",
    "rank_diff",
    "p1_recent_win_rate",
    "p2_recent_win_rate",
    "surface_p1_recent_win_rate",
    "surface_p2_recent_win_rate",
    "p1_days_since_last_match",
    "p2_days_since_last_match",
    "p1_matches_last_30_days",
    "p2_matches_last_30_days",
]


def train_tennis_ml_model(db: Session) -> Dict[str, Any]:
    """Build a dataset from finished tennis matches and train an XGBoost model."""
    sport = db.query(Sport).filter(Sport.code == "tennis").first()
    if not sport:
        return {"status": "error", "message": "Tennis sport not found"}

    # Elo history only covers matches up to the latest historical training run.
    # Training the ML model on matches beyond that date would starve it of Elo
    # features, so we cap the match window to the latest available Elo snapshot.
    from sqlalchemy import func

    max_elo_date = db.query(func.max(CompetitorEloHistory.calculated_at)).scalar()
    if not max_elo_date:
        return {"status": "error", "message": "No Elo history available for tennis"}

    matches = (
        db.query(Match)
        .options(joinedload(Match.competitors), joinedload(Match.scores))
        .filter(Match.sport_id == sport.id)
        .filter(Match.status == "FINISHED")
        .filter(Match.match_date <= max_elo_date)
        .order_by(Match.match_date.desc())
        .limit(MAX_TRAINING_MATCHES)
        .all()
    )

    if len(matches) < 100:
        return {
            "status": "error",
            "message": f"Insufficient training data: {len(matches)} matches",
        }

    # Collect competitor ids.
    competitor_ids = set()
    for match in matches:
        for c in match.competitors:
            competitor_ids.add(c.competitor_id)

    # Bulk load Elo and recent records.
    elo_index = _load_elo_index(db, list(competitor_ids))
    all_history, surface_history = _load_recent_records(matches)

    rows = []
    skipped = 0
    for match in matches:
        competitors = list(match.competitors)
        if len(competitors) != 2:
            skipped += 1
            continue
        p1 = next((c for c in competitors if c.side == "player1"), None)
        p2 = next((c for c in competitors if c.side == "player2"), None)
        if not p1 or not p2:
            # Fallback: order by competitor id for deterministic assignment.
            competitors.sort(key=lambda c: str(c.competitor_id))
            p1, p2 = competitors[0], competitors[1]
        row = _build_feature_row(match, p1, p2, elo_index, all_history, surface_history)
        if row:
            rows.append(row)
        else:
            skipped += 1

    if len(rows) < 100:
        return {
            "status": "error",
            "message": f"Insufficient training rows: {len(rows)}",
            "skipped": skipped,
        }

    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    import xgboost as xgb
    import numpy as np

    X = np.array([_extract_features(r) for r in rows])
    y = np.array([r["label"] for r in rows])

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        random_state=42,
        n_jobs=2,
    )
    model.fit(X_train_scaled, y_train)

    train_acc = float(model.score(X_train_scaled, y_train))
    test_acc = float(model.score(X_test_scaled, y_test))

    os.makedirs(MODEL_DIR, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"model": model, "scaler": scaler, "feature_names": FEATURE_NAMES}, f)

    metadata = {
        "sport": "tennis",
        "model_type": "xgboost",
        "feature_names": FEATURE_NAMES,
        "train_accuracy": round(train_acc, 4),
        "test_accuracy": round(test_acc, 4),
        "samples": len(rows),
        "max_matches_used": MAX_TRAINING_MATCHES,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(METADATA_PATH, "w") as f:
        json.dump(metadata, f, indent=2)

    return {
        "status": "success",
        "model_path": MODEL_PATH,
        "metadata_path": METADATA_PATH,
        "train_accuracy": round(train_acc, 4),
        "test_accuracy": round(test_acc, 4),
        "samples": len(rows),
        "skipped": skipped,
    }


def load_tennis_ml_model() -> Optional[Dict[str, Any]]:
    """Load the persisted XGBoost model and scaler."""
    if not os.path.exists(MODEL_PATH):
        return None
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


def _parse_form_win_rate(form_str: Optional[str]) -> float:
    """Approximate a win rate from a form string like 'WWDLW'."""
    if not form_str or form_str == "N/A":
        return 0.5
    form_str = str(form_str).upper()
    if not form_str:
        return 0.5
    wins = form_str.count("W")
    total = len(form_str)
    return wins / total if total > 0 else 0.5


def _extract_features_from_match(match: Dict[str, Any]) -> List[float]:
    """Build the feature vector from a match dict.

    Prefers rich features computed by FeatureService (last_20 win rates,
    surface-specific form, fatigue) and falls back to form strings / defaults.
    """
    p1_elo = _safe_float(match.get("eloPlayer1"))
    p2_elo = _safe_float(match.get("eloPlayer2"))
    p1_surface_elo = _safe_float(match.get("eloSurfacePlayer1"), p1_elo)
    p2_surface_elo = _safe_float(match.get("eloSurfacePlayer2"), p2_elo)
    p1_rank = _safe_float(match.get("rankingPlayer1"), 1000)
    p2_rank = _safe_float(match.get("rankingPlayer2"), 1000)

    p1_features = (match.get("features") or {}).get("player1", {})
    p2_features = (match.get("features") or {}).get("player2", {})

    p1_win_rate = _safe_float(
        p1_features.get("last_20", {}).get("win_rate"),
        _parse_form_win_rate(match.get("formPlayer1")),
    )
    p2_win_rate = _safe_float(
        p2_features.get("last_20", {}).get("win_rate"),
        _parse_form_win_rate(match.get("formPlayer2")),
    )
    p1_surface_win_rate = _safe_float(
        p1_features.get("surface_last_20", {}).get("win_rate"),
        p1_win_rate,
    )
    p2_surface_win_rate = _safe_float(
        p2_features.get("surface_last_20", {}).get("win_rate"),
        p2_win_rate,
    )

    # Fatigue / freshness features.
    p1_days_since = _safe_float(
        p1_features.get("days_since_last_match"),
        7.0,
    )
    p2_days_since = _safe_float(
        p2_features.get("days_since_last_match"),
        7.0,
    )
    p1_matches_30 = _safe_float(
        p1_features.get("matches_last_30_days"),
        2.0,
    )
    p2_matches_30 = _safe_float(
        p2_features.get("matches_last_30_days"),
        2.0,
    )

    return [
        p1_elo - p2_elo,
        p1_surface_elo - p2_surface_elo,
        p2_rank - p1_rank,
        p1_win_rate,
        p2_win_rate,
        p1_surface_win_rate,
        p2_surface_win_rate,
        p1_days_since,
        p2_days_since,
        p1_matches_30,
        p2_matches_30,
    ]


def _align_features(
    row: Dict[str, Any], expected_names: List[str]
) -> List[float]:
    """Build a feature vector aligned to the model's expected columns.

    Supports backward compatibility with older models trained on fewer
    features by selecting the appropriate subset.
    """
    if "elo_diff" in row:
        # Pre-computed named features.
        return [_safe_float(row.get(name), 0.0) for name in expected_names]

    # Match dict: extract the full modern feature vector and pick what the
    # model expects.
    full_vector = _extract_features_from_match(row)
    if len(expected_names) == len(full_vector):
        return full_vector

    # Backward compatibility: old models expect only the first 7 features.
    if len(expected_names) == 7 and len(full_vector) >= 7:
        return full_vector[:7]

    name_to_value = dict(zip(FEATURE_NAMES, full_vector))
    return [_safe_float(name_to_value.get(name), 0.0) for name in expected_names]


def predict_tennis_ml(features: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """Return player1/player2 win probabilities from the trained XGBoost model.

    Accepts either pre-computed feature names or a match dict with fields
    like eloPlayer1/eloPlayer2, eloSurfacePlayer1/eloSurfacePlayer2,
    rankingPlayer1/rankingPlayer2, formPlayer1/formPlayer2 and the optional
    FeatureService features block.
    """
    artifact = load_tennis_ml_model()
    if not artifact:
        return None

    import numpy as np

    model = artifact["model"]
    scaler = artifact["scaler"]
    expected_names = artifact.get("feature_names", FEATURE_NAMES[:7])

    x = np.array([_align_features(features, expected_names)])

    x_scaled = scaler.transform(x)
    proba = model.predict_proba(x_scaled)[0]
    return {"player1": float(proba[1]), "player2": float(proba[0])}


def predict_tennis_ml_batch(matches: List[Dict[str, Any]]) -> Optional[List[Dict[str, float]]]:
    """Return player1/player2 probabilities for a batch of matches."""
    artifact = load_tennis_ml_model()
    if not artifact:
        return None

    import numpy as np

    model = artifact["model"]
    scaler = artifact["scaler"]
    expected_names = artifact.get("feature_names", FEATURE_NAMES[:7])

    rows = [_align_features(m, expected_names) for m in matches]
    if not rows:
        return []

    X = np.array(rows)
    X_scaled = scaler.transform(X)
    probas = model.predict_proba(X_scaled)
    return [{"player1": float(p[1]), "player2": float(p[0])} for p in probas]
