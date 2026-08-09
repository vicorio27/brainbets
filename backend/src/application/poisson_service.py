"""Poisson attack/defense model for football.

Computes team-level attack and defense strengths per season/league
from historical match results, stores them in feature_store, and
provides expected goals for fixtures.
"""
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.domain.models import CompetitorStat, FeatureStore, Match, Sport


DEFAULT_LEAGUE_AVG_HOME_GOALS = 1.5
DEFAULT_LEAGUE_AVG_AWAY_GOALS = 1.1


def _safe_div(a: float, b: float, default: float = 1.0) -> float:
    return a / b if b else default


class TeamSeasonMetrics:
    def __init__(self, team_id: str, season: str, league_id: str) -> None:
        self.team_id = team_id
        self.season = season
        self.league_id = league_id
        self.home_matches = 0
        self.away_matches = 0
        self.home_goals_for = 0
        self.home_goals_against = 0
        self.away_goals_for = 0
        self.away_goals_against = 0

    def home_attack(self, league_home_avg: float) -> float:
        return _safe_div(self.home_goals_for / max(self.home_matches, 1), league_home_avg)

    def home_defense(self, league_home_avg: float) -> float:
        return _safe_div(self.home_goals_against / max(self.home_matches, 1), league_home_avg)

    def away_attack(self, league_away_avg: float) -> float:
        return _safe_div(self.away_goals_for / max(self.away_matches, 1), league_away_avg)

    def away_defense(self, league_away_avg: float) -> float:
        return _safe_div(self.away_goals_against / max(self.away_matches, 1), league_away_avg)


def _load_football_matches(db: Session, sport_id) -> List[Tuple]:
    """Load finished football matches with scores, season, league, and sides."""
    rows = db.execute(
        text("""
            SELECT
                m.id,
                m.season,
                m.league_id,
                mc_home.competitor_id AS home_id,
                mc_away.competitor_id AS away_id,
                ms.home_score,
                ms.away_score
            FROM matches m
            JOIN match_scores ms ON ms.match_id = m.id AND ms.period = 'FULL_TIME'
            JOIN match_competitors mc_home ON mc_home.match_id = m.id AND mc_home.side = 'home'
            JOIN match_competitors mc_away ON mc_away.match_id = m.id AND mc_away.side = 'away'
            WHERE m.sport_id::text = :sport_id AND m.status = 'FINISHED'
              AND m.season IS NOT NULL
        """),
        {"sport_id": str(sport_id)},
    ).fetchall()
    return rows


def compute_poisson_parameters(
    db: Session,
    sport_code: str = "football",
) -> Dict[str, Dict[str, Any]]:
    """Compute Poisson attack/defense parameters for football by season and league.

    Returns a nested dict: season -> league_id -> team_count.
    """
    sport = db.query(Sport).filter(Sport.code == sport_code).first()
    if not sport:
        return {}

    rows = _load_football_matches(db, sport.id)

    # Aggregate metrics
    metrics_by_key: Dict[str, TeamSeasonMetrics] = {}
    league_averages: Dict[str, Dict[str, float]] = defaultdict(
        lambda: {"home_gf": 0.0, "home_ga": 0.0, "away_gf": 0.0, "away_ga": 0.0, "matches": 0.0}
    )

    def _get_metric(team_id: str, season: str, league_id: str) -> TeamSeasonMetrics:
        key = f"{team_id}:{season}:{league_id}"
        if key not in metrics_by_key:
            metrics_by_key[key] = TeamSeasonMetrics(team_id, season, league_id)
        return metrics_by_key[key]

    for match_id, season, league_id, home_id, away_id, home_score, away_score in rows:
        if home_score is None or away_score is None:
            continue

        home_id = str(home_id)
        away_id = str(away_id)
        season = str(season)
        league_id = str(league_id)

        home_metric = _get_metric(home_id, season, league_id)
        away_metric = _get_metric(away_id, season, league_id)

        home_metric.home_matches += 1
        home_metric.home_goals_for += int(home_score)
        home_metric.home_goals_against += int(away_score)

        away_metric.away_matches += 1
        away_metric.away_goals_for += int(away_score)
        away_metric.away_goals_against += int(home_score)

        league_avg = league_averages[f"{season}:{league_id}"]
        league_avg["home_gf"] += int(home_score)
        league_avg["away_ga"] += int(home_score)
        league_avg["away_gf"] += int(away_score)
        league_avg["home_ga"] += int(away_score)
        league_avg["matches"] += 1

    # Normalize league averages
    normalized_averages: Dict[str, Dict[str, float]] = {}
    for key, avg in league_averages.items():
        n = avg["matches"]
        normalized_averages[key] = {
            "home_avg": avg["home_gf"] / n if n else DEFAULT_LEAGUE_AVG_HOME_GOALS,
            "away_avg": avg["away_gf"] / n if n else DEFAULT_LEAGUE_AVG_AWAY_GOALS,
        }

    # Build per-team parameters and store in CompetitorStat
    summary: Dict[str, Dict[str, int]] = defaultdict(dict)
    now = datetime.now(timezone.utc)

    # Load existing stats to update
    stat_keys = {(m.team_id, m.season, m.league_id) for m in metrics_by_key.values()}
    existing_stats = {
        (str(s.competitor_id), str(s.season), str(s.league_id)): s
        for s in db.query(CompetitorStat).filter(
            CompetitorStat.surface.is_(None),
        ).all()
        if s.season and s.league_id
    }

    for key, metric in metrics_by_key.items():
        avg_key = f"{metric.season}:{metric.league_id}"
        avgs = normalized_averages.get(avg_key, {"home_avg": DEFAULT_LEAGUE_AVG_HOME_GOALS, "away_avg": DEFAULT_LEAGUE_AVG_AWAY_GOALS})

        params = {
            "home_attack": round(metric.home_attack(avgs["home_avg"]), 4),
            "home_defense": round(metric.home_defense(avgs["home_avg"]), 4),
            "away_attack": round(metric.away_attack(avgs["away_avg"]), 4),
            "away_defense": round(metric.away_defense(avgs["away_avg"]), 4),
            "home_goals_avg": round(metric.home_goals_for / max(metric.home_matches, 1), 3),
            "away_goals_avg": round(metric.away_goals_for / max(metric.away_matches, 1), 3),
            "home_matches": metric.home_matches,
            "away_matches": metric.away_matches,
            "league_home_avg": round(avgs["home_avg"], 4),
            "league_away_avg": round(avgs["away_avg"], 4),
        }

        stat = existing_stats.get((metric.team_id, metric.season, metric.league_id))
        if not stat:
            stat = CompetitorStat(
                id=uuid4(),
                competitor_id=metric.team_id,
                league_id=metric.league_id,
                season=metric.season,
                matches_played=metric.home_matches + metric.away_matches,
                goals_for=metric.home_goals_for + metric.away_goals_for,
                goals_against=metric.home_goals_against + metric.away_goals_against,
                expected_goals=params["home_attack"] * avgs["home_avg"],
                extra_data={"poisson": params},
                calculated_at=now,
            )
            db.add(stat)
        else:
            stat.matches_played = metric.home_matches + metric.away_matches
            stat.goals_for = metric.home_goals_for + metric.away_goals_for
            stat.goals_against = metric.home_goals_against + metric.away_goals_against
            stat.expected_goals = params["home_attack"] * avgs["home_avg"]
            extra = stat.extra_data or {}
            extra["poisson"] = params
            stat.extra_data = extra
            stat.calculated_at = now

        summary[metric.season][metric.league_id] = summary[metric.season].get(metric.league_id, 0) + 1

    db.commit()
    return dict(summary)


def expected_goals_for_fixture(
    db: Session,
    home_team_id: str,
    away_team_id: str,
    season: str,
    league_id: Optional[str] = None,
) -> Tuple[float, float, Dict[str, Any]]:
    """Return (home_expected_goals, away_expected_goals, metadata) for a fixture.

    Falls back to league averages if a team has no recorded parameters.
    """
    home_team_id = str(home_team_id)
    away_team_id = str(away_team_id)

    def _team_params(team_id: str):
        query = db.query(CompetitorStat).filter(
            CompetitorStat.competitor_id == team_id,
            CompetitorStat.season == season,
            CompetitorStat.surface.is_(None),
        )
        if league_id:
            query = query.filter(CompetitorStat.league_id == league_id)
        return query.first()

    home_stat = _team_params(home_team_id)
    away_stat = _team_params(away_team_id)

    home_poisson = (home_stat.extra_data or {}).get("poisson", {}) if home_stat else {}
    away_poisson = (away_stat.extra_data or {}).get("poisson", {}) if away_stat else {}

    league_home_avg = home_poisson.get("league_home_avg", DEFAULT_LEAGUE_AVG_HOME_GOALS)
    league_away_avg = away_poisson.get("league_away_avg", DEFAULT_LEAGUE_AVG_AWAY_GOALS)

    home_attack = home_poisson.get("home_attack", 1.0)
    away_defense = away_poisson.get("away_defense", 1.0)
    away_attack = away_poisson.get("away_attack", 1.0)
    home_defense = home_poisson.get("home_defense", 1.0)

    home_xg = home_attack * away_defense * league_home_avg
    away_xg = away_attack * home_defense * league_away_avg

    meta = {
        "home_attack": home_attack,
        "away_defense": away_defense,
        "away_attack": away_attack,
        "home_defense": home_defense,
        "league_home_avg": league_home_avg,
        "league_away_avg": league_away_avg,
    }
    return home_xg, away_xg, meta


def run_poisson_training(db: Session) -> Dict[str, Any]:
    """Train Poisson parameters and return summary."""
    summary = compute_poisson_parameters(db, sport_code="football")
    return {"football": summary}
