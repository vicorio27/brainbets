"""Football stats enrichment service.

Computes real team form, league standings, head-to-head records and xG-like
metrics from historical matches stored in PostgreSQL. Used by the data
collection workflow to replace placeholder stats with data-backed values.
"""
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from src.domain.models import Competitor, Match, MatchCompetitor, MatchScore, Sport


DEFAULT_FORM_MATCHES = int(os.environ.get("FOOTBALL_FORM_MATCHES", "5"))
DEFAULT_H2H_MATCHES = int(os.environ.get("FOOTBALL_H2H_MATCHES", "5"))


def _team_name(db: Session, competitor_id: Any) -> Optional[str]:
    competitor = db.query(Competitor).filter(Competitor.id == competitor_id).first()
    return competitor.name if competitor else None


def _match_full_time_score(match: Match) -> Optional[Tuple[int, int]]:
    for score in match.scores or []:
        if score.period == "FULL_TIME":
            return (score.home_score or 0, score.away_score or 0)
    return None


def _team_side_in_match(match: Match, competitor_id: Any) -> Optional[str]:
    for c in match.competitors:
        if c.competitor_id == competitor_id:
            return c.side
    return None


def _team_matches(
    db: Session,
    competitor_id: Any,
    before_date: Optional[datetime] = None,
    league_id: Optional[Any] = None,
    season: Optional[str] = None,
    status: str = "FINISHED",
    limit: int = DEFAULT_FORM_MATCHES,
) -> List[Match]:
    """Return recent finished matches for a team, ordered by date desc."""
    query = (
        db.query(Match)
        .join(MatchCompetitor, Match.id == MatchCompetitor.match_id)
        .filter(MatchCompetitor.competitor_id == competitor_id)
        .filter(Match.status == status)
    )
    if before_date is not None:
        query = query.filter(Match.match_date < before_date)
    if league_id is not None:
        query = query.filter(Match.league_id == league_id)
    if season is not None:
        query = query.filter(Match.season == season)
    return query.order_by(Match.match_date.desc()).limit(limit).all()


def _team_goals_in_match(match: Match, competitor_id: Any) -> Optional[Tuple[int, int]]:
    """Return (goals_for, goals_against) for a team in a finished match."""
    full_time = _match_full_time_score(match)
    if full_time is None:
        return None
    home_score, away_score = full_time
    side = _team_side_in_match(match, competitor_id)
    if side == "home":
        return (home_score, away_score)
    if side == "away":
        return (away_score, home_score)
    return None


def compute_team_form(
    db: Session,
    competitor_id: Any,
    before_date: Optional[datetime] = None,
    league_id: Optional[Any] = None,
    season: Optional[str] = None,
    limit: int = DEFAULT_FORM_MATCHES,
) -> Dict[str, Any]:
    """Compute recent form for a team.

    Returns a dict with form string (e.g. 'WWDLW'), wins/draws/losses,
    goals scored/conceded and points.
    """
    matches = _team_matches(db, competitor_id, before_date, league_id, season, limit=limit)
    form_chars = []
    wins = draws = losses = 0
    goals_for = goals_against = 0

    for match in matches:
        goals = _team_goals_in_match(match, competitor_id)
        if goals is None:
            continue
        gf, ga = goals
        goals_for += gf
        goals_against += ga
        if gf > ga:
            form_chars.append("W")
            wins += 1
        elif gf < ga:
            form_chars.append("L")
            losses += 1
        else:
            form_chars.append("D")
            draws += 1

    played = wins + draws + losses
    points = wins * 3 + draws
    return {
        "form": "".join(form_chars) if form_chars else "N/A",
        "played": played,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "points": points,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "goal_difference": goals_for - goals_against,
        "matches": [
            {
                "match_id": str(m.id),
                "date": m.match_date.isoformat() if m.match_date else None,
                "goals_for": _team_goals_in_match(m, competitor_id)[0] if _team_goals_in_match(m, competitor_id) else None,
                "goals_against": _team_goals_in_match(m, competitor_id)[1] if _team_goals_in_match(m, competitor_id) else None,
            }
            for m in matches
        ],
    }


def compute_league_standings(
    db: Session,
    league_id: Any,
    season: Optional[str] = None,
    before_date: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Compute league table from finished matches in the DB."""
    query = (
        db.query(Match)
        .filter(Match.league_id == league_id)
        .filter(Match.status == "FINISHED")
    )
    if season is not None:
        query = query.filter(Match.season == season)
    if before_date is not None:
        query = query.filter(Match.match_date < before_date)

    matches = query.all()
    table: Dict[Any, Dict[str, Any]] = defaultdict(
        lambda: {
            "played": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "goals_for": 0,
            "goals_against": 0,
            "points": 0,
        }
    )

    for match in matches:
        full_time = _match_full_time_score(match)
        if full_time is None:
            continue
        home_score, away_score = full_time
        competitors = {c.side: c.competitor_id for c in match.competitors}
        home_id = competitors.get("home")
        away_id = competitors.get("away")
        if not home_id or not away_id:
            continue

        table[home_id]["played"] += 1
        table[away_id]["played"] += 1
        table[home_id]["goals_for"] += home_score
        table[home_id]["goals_against"] += away_score
        table[away_id]["goals_for"] += away_score
        table[away_id]["goals_against"] += home_score

        if home_score > away_score:
            table[home_id]["wins"] += 1
            table[home_id]["points"] += 3
            table[away_id]["losses"] += 1
        elif home_score < away_score:
            table[away_id]["wins"] += 1
            table[away_id]["points"] += 3
            table[home_id]["losses"] += 1
        else:
            table[home_id]["draws"] += 1
            table[away_id]["draws"] += 1
            table[home_id]["points"] += 1
            table[away_id]["points"] += 1

    standings = []
    for competitor_id, stats in table.items():
        stats["competitor_id"] = str(competitor_id)
        stats["name"] = _team_name(db, competitor_id)
        stats["goal_difference"] = stats["goals_for"] - stats["goals_against"]
        standings.append(stats)

    standings.sort(
        key=lambda x: (x["points"], x["goal_difference"], x["goals_for"]),
        reverse=True,
    )
    for idx, row in enumerate(standings, start=1):
        row["position"] = idx

    return standings


def compute_head_to_head(
    db: Session,
    home_id: Any,
    away_id: Any,
    before_date: Optional[datetime] = None,
    limit: int = DEFAULT_H2H_MATCHES,
) -> Dict[str, Any]:
    """Compute head-to-head record between two teams."""
    query = (
        db.query(Match)
        .join(MatchCompetitor, Match.id == MatchCompetitor.match_id)
        .filter(Match.status == "FINISHED")
        .filter(MatchCompetitor.competitor_id.in_([home_id, away_id]))
    )
    if before_date is not None:
        query = query.filter(Match.match_date < before_date)

    matches = query.order_by(Match.match_date.desc()).all()
    h2h_matches = []
    for match in matches:
        competitor_ids = {c.side: c.competitor_id for c in match.competitors}
        if competitor_ids.get("home") in (home_id, away_id) and competitor_ids.get("away") in (home_id, away_id):
            h2h_matches.append(match)
        if len(h2h_matches) >= limit:
            break

    home_wins = away_wins = draws = 0
    home_goals = away_goals = 0
    details = []
    for match in h2h_matches:
        full_time = _match_full_time_score(match)
        if full_time is None:
            continue
        h_score, a_score = full_time
        competitor_ids = {c.side: c.competitor_id for c in match.competitors}
        actual_home = competitor_ids.get("home")
        actual_away = competitor_ids.get("away")

        if actual_home == home_id:
            home_goals += h_score
            away_goals += a_score
            if h_score > a_score:
                home_wins += 1
            elif h_score < a_score:
                away_wins += 1
            else:
                draws += 1
        else:
            home_goals += a_score
            away_goals += h_score
            if a_score > h_score:
                home_wins += 1
            elif a_score < h_score:
                away_wins += 1
            else:
                draws += 1

        details.append(
            {
                "match_id": str(match.id),
                "date": match.match_date.isoformat() if match.match_date else None,
                "home_score": h_score,
                "away_score": a_score,
            }
        )

    return {
        "matches": len(h2h_matches),
        "home_wins": home_wins,
        "away_wins": away_wins,
        "draws": draws,
        "home_goals": home_goals,
        "away_goals": away_goals,
        "details": details,
    }


def compute_team_xg_proxy(
    db: Session,
    competitor_id: Any,
    before_date: Optional[datetime] = None,
    league_id: Optional[Any] = None,
    season: Optional[str] = None,
    limit: int = DEFAULT_FORM_MATCHES,
) -> Dict[str, Any]:
    """Compute xG-like metrics from historical goals data.

    Uses real xG from match.extra_data when available, otherwise falls back
    to average goals scored/conceded.
    """
    matches = _team_matches(db, competitor_id, before_date, league_id, season, limit=limit)
    xg_for_sum = xg_against_sum = 0.0
    goals_for_sum = goals_against_sum = 0
    matches_with_xg = 0

    for match in matches:
        goals = _team_goals_in_match(match, competitor_id)
        if goals is None:
            continue
        gf, ga = goals
        goals_for_sum += gf
        goals_against_sum += ga

        # Try to read real xG from match extra_data if available.
        meta = match.extra_data or {}
        home_score_meta = meta.get("home_xg") or meta.get("home_xG") or meta.get("xG_home")
        away_score_meta = meta.get("away_xg") or meta.get("away_xG") or meta.get("xG_away")
        side = _team_side_in_match(match, competitor_id)
        if side == "home" and home_score_meta is not None:
            xg_for_sum += float(home_score_meta)
            xg_against_sum += float(away_score_meta) if away_score_meta is not None else ga
            matches_with_xg += 1
        elif side == "away" and away_score_meta is not None:
            xg_for_sum += float(away_score_meta)
            xg_against_sum += float(home_score_meta) if home_score_meta is not None else ga
            matches_with_xg += 1

    played = len(matches)
    if played == 0:
        return {"xg_for": None, "xg_against": None, "source": "none"}

    if matches_with_xg > 0:
        return {
            "xg_for": round(xg_for_sum / matches_with_xg, 3),
            "xg_against": round(xg_against_sum / matches_with_xg, 3),
            "source": "historical_xg",
            "matches_with_xg": matches_with_xg,
        }

    return {
        "xg_for": round(goals_for_sum / played, 3),
        "xg_against": round(goals_against_sum / played, 3),
        "source": "goals_proxy",
    }


def enrich_football_match(
    db: Session,
    match: Match,
    form_limit: int = DEFAULT_FORM_MATCHES,
    h2h_limit: int = DEFAULT_H2H_MATCHES,
) -> Dict[str, Any]:
    """Return real computed stats for a football match.

    The returned dict follows the field names expected by the prediction
    engine and the frontend (camelCase).
    """
    competitors = {c.side: c for c in match.competitors}
    home = competitors.get("home")
    away = competitors.get("away")
    if not home or not away:
        return {}

    before_date = match.match_date or datetime.now(timezone.utc)
    league_id = match.league_id
    season = match.season

    home_form = compute_team_form(
        db, home.competitor_id, before_date, league_id, season, limit=form_limit
    )
    away_form = compute_team_form(
        db, away.competitor_id, before_date, league_id, season, limit=form_limit
    )

    standings = compute_league_standings(db, league_id, season, before_date)
    home_position = next(
        (row["position"] for row in standings if row["competitor_id"] == str(home.competitor_id)),
        None,
    )
    away_position = next(
        (row["position"] for row in standings if row["competitor_id"] == str(away.competitor_id)),
        None,
    )

    h2h = compute_head_to_head(
        db, home.competitor_id, away.competitor_id, before_date, limit=h2h_limit
    )

    home_xg = compute_team_xg_proxy(
        db, home.competitor_id, before_date, league_id, season, limit=form_limit
    )
    away_xg = compute_team_xg_proxy(
        db, away.competitor_id, before_date, league_id, season, limit=form_limit
    )

    return {
        "homePosition": home_position,
        "awayPosition": away_position,
        "homeForm": home_form.get("form"),
        "awayForm": away_form.get("form"),
        "homeFormStats": home_form,
        "awayFormStats": away_form,
        "homeXg": home_xg.get("xg_for"),
        "awayXg": away_xg.get("xg_for"),
        "homeXgAgainst": home_xg.get("xg_against"),
        "awayXgAgainst": away_xg.get("xg_against"),
        "homeCorners": None,  # Not available in DB without detailed event data.
        "awayCorners": None,
        "headToHead": h2h,
        "leagueStandings": standings,
        "dataQuality": "real" if (home_form.get("played") or 0) > 0 else "fallback",
    }
