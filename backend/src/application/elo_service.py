"""Elo rating computation service.

Computes standard Elo ratings from historical match results and stores
current ratings in competitor_stats and rating history in competitor_elo_history.
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from src.domain.models import Competitor, CompetitorEloHistory, CompetitorStat, Match, Sport


DEFAULT_ELO = 1500.0
K_FACTOR = 32.0
HOME_ADVANTAGE = 65.0


def _expected_score(rating_a: float, rating_b: float) -> float:
    """Elo expected score for player A against player B."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def _k_factor_for_match(match: Match) -> float:
    """K-factor adjusted by match importance."""
    return K_FACTOR


def _get_match_surface(match: Match) -> Optional[str]:
    """Normalize surface string from match extra_data."""
    surface = (match.extra_data or {}).get("surface")
    if surface:
        return str(surface).lower().strip()
    return None


def _load_matches(
    db: Session,
    sport_id: UUID,
) -> List[Tuple[UUID, UUID, UUID, int, int, datetime, Optional[str]]]:
    """Load all finished matches for a sport with scores and competitor sides.

    Returns list of (match_id, home_id, away_id, home_score, away_score, match_date, surface).
    For tennis, 'home' maps to player1 and 'away' to player2.
    """
    results = (
        db.query(
            Match.id,
            Match.match_date,
            Match.extra_data,
        )
        .filter(Match.sport_id == sport_id, Match.status == "FINISHED")
        .order_by(Match.match_date.asc())
        .all()
    )

    match_ids = [r.id for r in results]
    if not match_ids:
        return []

    # Load competitors for these matches in bulk
    competitor_rows = (
        db.query(Match.id.label("match_id"))
        .filter(Match.id.in_(match_ids))
        .all()
    )

    from sqlalchemy import text
    raw = db.execute(
        text("""
            SELECT
                mc.match_id,
                mc.side,
                mc.competitor_id
            FROM match_competitors mc
            WHERE mc.match_id::text = ANY(:match_ids)
        """),
        {"match_ids": [str(m) for m in match_ids]},
    ).fetchall()

    competitors_by_match: Dict[UUID, Dict[str, UUID]] = {}
    for match_id, side, competitor_id in raw:
        competitors_by_match.setdefault(match_id, {})[side] = competitor_id

    # Load scores in bulk
    from src.domain.models import MatchScore
    score_rows = (
        db.query(MatchScore.match_id, MatchScore.home_score, MatchScore.away_score)
        .filter(MatchScore.match_id.in_(match_ids), MatchScore.period == "FULL_TIME")
        .all()
    )
    scores_by_match = {s.match_id: (s.home_score, s.away_score) for s in score_rows}

    output = []
    for r in results:
        comps = competitors_by_match.get(r.id, {})
        home_id = comps.get("home") or comps.get("player1")
        away_id = comps.get("away") or comps.get("player2")
        score = scores_by_match.get(r.id)
        if not home_id or not away_id or not score:
            continue
        home_score, away_score = score
        if home_score is None or away_score is None:
            continue
        output.append((
            r.id,
            home_id,
            away_id,
            int(home_score),
            int(away_score),
            r.match_date,
            _get_match_surface(r),
        ))

    return output


def _train_elo_for_sport(
    db: Session,
    sport_id: UUID,
    surface: Optional[str] = None,
) -> Dict[UUID, float]:
    """Compute Elo ratings for a sport/surface and persist results."""
    matches = _load_matches(db, sport_id)
    if surface:
        matches = [m for m in matches if m[6] == surface]

    if not matches:
        return {}

    # Load existing stats for relevant competitors
    competitor_ids = set()
    for _, home_id, away_id, _, _, _, _ in matches:
        competitor_ids.add(home_id)
        competitor_ids.add(away_id)

    existing_stats = {
        s.competitor_id: s
        for s in db.query(CompetitorStat).filter(
            CompetitorStat.competitor_id.in_(competitor_ids),
            CompetitorStat.surface == surface,
            CompetitorStat.season.is_(None),
            CompetitorStat.league_id.is_(None),
        ).all()
    }

    now = datetime.now(timezone.utc)

    # Prepare stat objects (create if missing)
    stats_map: Dict[UUID, CompetitorStat] = {}
    for cid in competitor_ids:
        stat = existing_stats.get(cid)
        if not stat:
            stat = CompetitorStat(
                id=uuid4(),
                competitor_id=cid,
                surface=surface,
                season=None,
                league_id=None,
                current_elo=DEFAULT_ELO,
                matches_played=0,
                wins=0,
                draws=0,
                losses=0,
                calculated_at=now,
            )
            db.add(stat)
        stats_map[cid] = stat

    # Clear old Elo history for this sport/surface so training is idempotent
    db.query(CompetitorEloHistory).filter(
        CompetitorEloHistory.surface == surface,
        CompetitorEloHistory.competitor_id.in_(competitor_ids),
    ).delete(synchronize_session=False)

    ratings: Dict[UUID, float] = {}
    history_records = []

    for match_id, home_id, away_id, home_score, away_score, match_date, _ in matches:
        home_rating = ratings.get(home_id, DEFAULT_ELO)
        away_rating = ratings.get(away_id, DEFAULT_ELO)

        home_expected = _expected_score(home_rating + HOME_ADVANTAGE, away_rating)
        away_expected = 1.0 - home_expected

        if home_score > away_score:
            home_actual, away_actual = 1.0, 0.0
        elif home_score < away_score:
            home_actual, away_actual = 0.0, 1.0
        else:
            home_actual, away_actual = 0.5, 0.5

        k = K_FACTOR
        home_new = home_rating + k * (home_actual - home_expected)
        away_new = away_rating + k * (away_actual - away_expected)

        ratings[home_id] = home_new
        ratings[away_id] = away_new

        history_records.append({
            "id": uuid4(),
            "competitor_id": home_id,
            "match_id": match_id,
            "elo_before": home_rating,
            "elo_after": home_new,
            "surface": surface,
            "calculated_at": match_date or now,
        })
        history_records.append({
            "id": uuid4(),
            "competitor_id": away_id,
            "match_id": match_id,
            "elo_before": away_rating,
            "elo_after": away_new,
            "surface": surface,
            "calculated_at": match_date or now,
        })

        home_stat = stats_map[home_id]
        away_stat = stats_map[away_id]
        home_stat.matches_played += 1
        away_stat.matches_played += 1
        home_stat.current_elo = home_new
        away_stat.current_elo = away_new
        home_stat.calculated_at = now
        away_stat.calculated_at = now
        if home_actual == 1.0:
            home_stat.wins += 1
            away_stat.losses += 1
        elif home_actual == 0.0:
            home_stat.losses += 1
            away_stat.wins += 1
        else:
            home_stat.draws += 1
            away_stat.draws += 1

    # Bulk insert history
    if history_records:
        db.execute(insert(CompetitorEloHistory).values(history_records))

    db.commit()
    return ratings


def compute_elo_ratings(
    db: Session,
    sport_code: str,
    surface: Optional[str] = None,
) -> Dict[UUID, float]:
    """Compute Elo ratings for all competitors of a sport from historical matches.

    If surface is provided, computes surface-specific Elo ratings.
    Returns a mapping competitor_id -> current rating.
    """
    sport = db.query(Sport).filter(Sport.code == sport_code).first()
    if not sport:
        return {}
    return _train_elo_for_sport(db, sport.id, surface=surface)


def run_elo_training(
    db: Session,
    sports: Optional[List[str]] = None,
) -> Dict[str, Dict[str, int]]:
    """Train Elo ratings for configured sports.

    For tennis, also computes surface-specific ratings (hard, clay, grass).
    """
    sports = sports or ["football", "tennis"]
    summary = {}

    for sport_code in sports:
        ratings = compute_elo_ratings(db, sport_code, surface=None)
        summary[sport_code] = {"overall": len(ratings)}

        if sport_code == "tennis":
            for surface in ["hard", "clay", "grass"]:
                surface_ratings = compute_elo_ratings(db, sport_code, surface=surface)
                summary[sport_code][surface] = len(surface_ratings)

    return summary
