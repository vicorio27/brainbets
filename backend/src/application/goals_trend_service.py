"""How many goals each team's matches carry: goals scored and conceded, how often
the match goes over 1.5 / 2.5 goals, how often both teams score.

Some teams (a side fighting relegation, an open attack with a weak defence) end
up in high-scoring matches week after week; others in tight ones. This reads that
from each team's last matches, from its own side of the score. Information only:
it is not measured against the bookmaker's price.
"""
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from src.domain.models import Match, MatchCompetitor, MatchScore

LAST = 10            # matches read per team
MIN_MATCHES = 5      # fewer than this says nothing
HIGH, LOW = 0.70, 0.30
MAX_AGE_DAYS = 365   # older matches are another squad: say nothing rather than mislead


def summarize(results: List[Tuple[int, int]]) -> Optional[Dict[str, Any]]:
    """results: (goals for, goals against) of each match, newest first."""
    n = len(results)
    if n < MIN_MATCHES:
        return None
    over25 = sum(1 for f, a in results if f + a >= 3) / n
    over15 = sum(1 for f, a in results if f + a >= 2) / n
    btts = sum(1 for f, a in results if f > 0 and a > 0) / n
    out = {"n": n, "goalsFor": round(sum(f for f, _ in results) / n, 2),
           "goalsAgainst": round(sum(a for _, a in results) / n, 2),
           "over15": round(over15, 2), "over25": round(over25, 2), "btts": round(btts, 2),
           "cleanSheets": sum(1 for _, a in results if a == 0), "notes": []}
    if over25 >= HIGH:
        out["notes"].append(f"Más de 2.5 goles en {round(over25 * n)} de sus últimos {n}")
    elif over25 <= LOW:
        out["notes"].append(f"Más de 2.5 goles en solo {round(over25 * n)} de sus últimos {n}")
    if btts >= HIGH:
        out["notes"].append(f"Marca y recibe en {round(btts * n)} de sus últimos {n}")
    elif btts <= LOW:
        out["notes"].append(f"Marca y recibe en solo {round(btts * n)} de sus últimos {n}")
    return out


def combine(home: Optional[Dict[str, Any]], away: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not home or not away:
        return None
    return {"over25": round((home["over25"] + away["over25"]) / 2, 2),
            "btts": round((home["btts"] + away["btts"]) / 2, 2),
            "goals": round((home["goalsFor"] + home["goalsAgainst"] + away["goalsFor"] + away["goalsAgainst"]) / 2, 2)}


def team_results(db: Session, competitor_id, before) -> List[Tuple[int, int]]:
    rows = (db.query(MatchCompetitor.side, MatchScore.home_score, MatchScore.away_score)
            .join(Match, Match.id == MatchCompetitor.match_id)
            .join(MatchScore, (MatchScore.match_id == Match.id) & (MatchScore.period == "FULL_TIME"))
            .filter(MatchCompetitor.competitor_id == competitor_id, Match.status == "FINISHED",
                    Match.match_date < before, Match.match_date >= before - timedelta(days=MAX_AGE_DAYS))
            .order_by(Match.match_date.desc()).limit(LAST).all())
    out = []
    for side, h, a in rows:
        if h is None or a is None:
            continue
        out.append((h, a) if side == "home" else (a, h))
    return out


def trend_for_match(db: Session, match: Match) -> Optional[Dict[str, Any]]:
    sides = {c.side: c for c in match.competitors}
    if "home" not in sides or "away" not in sides or not match.match_date:
        return None
    home = summarize(team_results(db, sides["home"].competitor_id, match.match_date))
    away = summarize(team_results(db, sides["away"].competitor_id, match.match_date))
    if not home and not away:
        return None
    return {"home": home, "away": away, "both": combine(home, away)}
