"""Head-to-head between the two players of each tennis match, from our DB.

Read by competitor id (the players linked to the match), never by name, so a
name variant can't hide a meeting. One query for a whole page of matches.
"""
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.timezone import to_bogota

# tennis-data.co.uk rows ('TENNIS-2023-11-01_00:00:00-Winner-Loser') store the
# winner as player1: 29,043 of the 29,389 that have a score. 207 of them have
# no score at all, and for those this is the only way to know who won.
TENNIS_DATA_ID = re.compile(r"^TENNIS-\d{4}-\d{2}-\d{2}_")

MAX_MEETINGS_SHOWN = 6


def meeting_winner(external_id: Optional[str], home: Optional[int], away: Optional[int]) -> Optional[str]:
    """'player1' / 'player2' / None for a finished meeting, from the meeting's own sides."""
    if home is not None and away is not None and home != away:
        return "player1" if home > away else "player2"
    if external_id and TENNIS_DATA_ID.match(external_id):
        return "player1"
    return None


def summarize(meetings: List[Dict[str, Any]], limit: int = MAX_MEETINGS_SHOWN) -> Optional[Dict[str, Any]]:
    """Record and latest meetings from player1's side of the match being shown.

    Each meeting: {date (datetime), tournament, surface, p1Won (bool|None),
    sets ('2-1' from p1's side or None), games (['6-4', ...] or None)}.
    The same match stored twice (two sources, dates a day apart) counts once.
    """
    rows = sorted((m for m in meetings if m.get("date") is not None), key=lambda m: m["date"], reverse=True)
    kept: List[Dict[str, Any]] = []
    for m in rows:
        if any(abs((k["date"] - m["date"]).days) <= 2 for k in kept):
            continue
        kept.append(m)
    decided = [m for m in kept if m.get("p1Won") is not None]
    if not decided:
        return None
    p1 = sum(1 for m in decided if m["p1Won"])
    return {
        "p1Wins": p1,
        "p2Wins": len(decided) - p1,
        "total": len(decided),
        "meetings": [
            {
                "date": to_bogota(m["date"]).strftime("%Y-%m-%d"),
                "tournament": m.get("tournament"),
                "surface": m.get("surface"),
                "winner": "p1" if m["p1Won"] else "p2",
                # scores read from the winner's side: 'ganó X 3-1 · 6-4 ...'
                "sets": m.get("sets") if m["p1Won"] or not m.get("sets") else _flip(m["sets"]),
                "games": m.get("games") if m["p1Won"] or not m.get("games") else [_flip(g) for g in m["games"]],
            }
            for m in decided[:limit]
        ],
    }


def _flip(score: str) -> str:
    a, b = score.split("-")
    return f"{b}-{a}"


def h2h_for_matches(db: Session, matches: List[Any]) -> Dict[Any, Optional[Dict[str, Any]]]:
    """{match.id: summarize(...) or None} for tennis matches with both players linked."""
    pairs = []
    for m in matches:
        sides = {c.side: c.competitor_id for c in (m.competitors or [])}
        if sides.get("player1") and sides.get("player2") and m.match_date:
            pairs.append((str(m.id), str(sides["player1"]), str(sides["player2"]), m.match_date.isoformat()))
    if not pairs:
        return {}
    rows = db.execute(
        text("""
        select p.mid, m.external_id, m.match_date, l.name, m.extra_data->>'surface',
               ma.side, s.home_score, s.away_score, m.extra_data->'score_stats'->'sets'
        from unnest(cast(:mids as uuid[]), cast(:p1s as uuid[]), cast(:p2s as uuid[]), cast(:dates as timestamptz[]))
             as p(mid, p1, p2, d)
        join match_competitors ma on ma.competitor_id = p.p1
        join match_competitors mb on mb.match_id = ma.match_id and mb.competitor_id = p.p2
        join matches m on m.id = ma.match_id and m.status = 'FINISHED' and m.match_date < p.d
        left join leagues l on l.id = m.league_id
        left join match_scores s on s.match_id = m.id and s.period = 'FULL_TIME'
        """),
        {
            "mids": [p[0] for p in pairs],
            "p1s": [p[1] for p in pairs],
            "p2s": [p[2] for p in pairs],
            "dates": [p[3] for p in pairs],
        },
    ).fetchall()
    found: Dict[str, List[Dict[str, Any]]] = {}
    for mid, ext, date, league, surface, p1_side, home, away, sets in rows:
        winner = meeting_winner(ext, home, away)
        same_side = p1_side == "player1"  # this match's player1 was player1 in that meeting too
        sets_str = f"{home}-{away}" if home is not None and away is not None else None
        games = None
        if isinstance(sets, list) and sets:
            try:
                # archive rows pad unplayed sets with 0-0
                games = [f"{int(x.get('p1'))}-{int(x.get('p2'))}" for x in sets
                         if int(x.get('p1') or 0) or int(x.get('p2') or 0)] or None
            except (TypeError, ValueError, AttributeError):
                games = None
        if not same_side:
            sets_str = _flip(sets_str) if sets_str else None
            games = [_flip(g) for g in games] if games else None
        found.setdefault(str(mid), []).append({
            "date": date,
            "tournament": league,
            "surface": (surface or "").lower() or None,
            "p1Won": None if winner is None else (winner == "player1") == same_side,
            "sets": sets_str,
            "games": games,
        })
    by_id = {str(m.id): m.id for m in matches}
    return {by_id[mid]: summarize(ms) for mid, ms in found.items() if mid in by_id}
