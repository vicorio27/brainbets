"""Warning labels for a football match: reasons not to trust (or to read carefully) what the model says.

The numbers the cards show come from a Poisson model fed by each team's own history. When a team has no
recent history in the league (a newly promoted side, the 22-nov Levante-Racing Santander with 3.6 expected
goals because Racing's parameters came from 2011-12), the model quietly falls back to old or generic values.
These labels say so on the match card, so it can be taken into account. Display only: they change nothing.

Each flag: {key, level: "warn" | "info", text}. `warn` = the numbers are probably unreliable.
"""
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.domain.models import CompetitorStat

STALE_GAP = 2            # seasons without data from which a team counts as returning / newly promoted
FEW_VENUE = 8            # matches at this venue (home or away) this season below which a team's strength is thin
BIG_SIDE_GOALS = 2.8     # expected goals of one side above which the match looks like a data problem
BIG_TOTAL_GOALS = 4.2


def season_start(code: Optional[str]) -> Optional[int]:
    """'2627' -> 26 (the year the season starts, two digits)."""
    try:
        return int(str(code)[:2])
    except (TypeError, ValueError):
        return None


def team_status(db: Session, team_id, season: str, league_id) -> Dict[str, Any]:
    """What we hold on a team in this league: matches this season and the latest earlier season with parameters."""
    q = db.query(CompetitorStat).filter(CompetitorStat.competitor_id == team_id, CompetitorStat.surface.is_(None))
    if league_id:
        q = q.filter(CompetitorStat.league_id == league_id)
    rows = [r for r in q.all() if (r.extra_data or {}).get("poisson")]
    current = next((r for r in rows if r.season == season), None)
    earlier = sorted((r.season for r in rows if r.season and r.season < season), reverse=True)
    p = (current.extra_data or {}).get("poisson", {}) if current else {}
    return {"currentMatches": (current.matches_played or 0) if current else 0, "hasCurrent": current is not None,
            "lastEarlier": earlier[0] if earlier else None,
            "homeMatches": p.get("home_matches", 0), "awayMatches": p.get("away_matches", 0)}


def build_flags(home: str, away: str, league: Optional[str], season: str, hs: Dict[str, Any], as_: Dict[str, Any],
                lh: Optional[float], la: Optional[float], has_price: bool, scheduled: bool) -> List[Dict[str, str]]:
    flags: List[Dict[str, str]] = []
    cur = season_start(season)
    for name, st, venue_key, venue in ((home, hs, "homeMatches", "de local"), (away, as_, "awayMatches", "de visitante")):
        if not st["hasCurrent"] and not st["lastEarlier"]:
            flags.append({"key": "no_history", "level": "warn",
                          "text": f"{name} no tiene historial en esta liga en nuestros datos (recién ascendido o liga nueva): "
                                  "sus goles esperados salen del promedio de la liga."})
            continue
        last = season_start(st["lastEarlier"])
        if not st["hasCurrent"] and last is not None and cur is not None and cur - last >= STALE_GAP:
            flags.append({"key": "promoted", "level": "warn",
                          "text": f"{name} vuelve a esta liga (recién ascendido): sus parámetros son de la temporada 20{last:02d}-{last + 1:02d}, "
                                  "no de ahora. Los goles esperados son poco fiables."})
        elif st[venue_key] < FEW_VENUE and not (league or "").lower().startswith("champions"):
            flags.append({"key": "few_matches", "level": "info",
                          "text": f"{name} solo lleva {st[venue_key]} partidos {venue} esta temporada en nuestros datos: "
                                  "su fuerza en ese campo se calcula con muy poca muestra y puede salir exagerada (para bien o para mal)."})
    if lh is not None and la is not None and (max(lh, la) > BIG_SIDE_GOALS or lh + la > BIG_TOTAL_GOALS):
        flags.append({"key": "extreme_goals", "level": "warn",
                      "text": f"Goles esperados fuera de lo normal ({lh:.1f} y {la:.1f}): "
                              "casi nunca una goleada segura: suele ser un equipo con poca muestra en ese campo. No te fíes de los porcentajes de goles."})
    if (league or "").lower().startswith("champions"):
        flags.append({"key": "cup", "level": "info",
                      "text": "Champions League: cada equipo juega pocos partidos en la competición y los parámetros salen ruidosos; "
                              "mira la cuota de la casa antes que el modelo."})
    if scheduled and not has_price:
        flags.append({"key": "no_price", "level": "info", "text": "Sin cuota de la casa para este partido: lo que se ve viene solo del modelo."})
    return flags


def flags_for(db: Session, match, home_id, away_id, home_name: str, away_name: str,
              lh: Optional[float], la: Optional[float]) -> List[Dict[str, str]]:
    season = match.season or ""
    meta = match.extra_data or {}
    return build_flags(
        home_name, away_name, match.league.name if match.league else None, season,
        team_status(db, home_id, season, match.league_id), team_status(db, away_id, season, match.league_id),
        lh, la, bool(meta.get("odds_markets")), match.status == "SCHEDULED",
    )
