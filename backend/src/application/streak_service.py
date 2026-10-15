"""Tournament streak tags for tennis players: information, not a betting signal.

For each player of a match, what they did earlier in the SAME tournament:
how many matches they won and whether the last one was an upset (they won as
the underdog). Tested on 27k ATP matches with Pinnacle closing odds
(2010-2020, AGENTS.md 2026-10-15): the price already includes these, so no tag
here marks value. Ranked > 100 on a run is the one the market tends to
overrate (they won 26.7% vs 27.5% priced).
"""
from datetime import timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from src.domain.models import Match, MatchCompetitor, MatchScore

WINDOW_DAYS = 16          # a Grand Slam spans two weeks
UPSET_FAIR = 0.40         # won while priced at or below this
UPSET_RANK_RATIO = 2.0    # no price: won against someone ranked at least 2x better
LOW_RANK = 100


def _fair(extra: Dict[str, Any], side: str) -> Optional[float]:
    for key in ("odds_markets", "odds_markets_backfill"):
        ref = (extra.get(key) or {}).get("matchWinner") or {}
        try:
            r1, r2 = float(ref["p1"]), float(ref["p2"])
        except (KeyError, TypeError, ValueError):
            continue
        if r1 > 1.0 and r2 > 1.0:
            fair1 = (1.0 / r1) / (1.0 / r1 + 1.0 / r2)
            return fair1 if side == "p1" else 1.0 - fair1
    return None


def was_upset(fair: Optional[float], my_rank: Optional[int], opp_rank: Optional[int]) -> bool:
    """A win counts as an upset if the price had us at <= 40%, or, without a price,
    the opponent was ranked at least twice as well."""
    if fair is not None:
        return fair <= UPSET_FAIR
    if my_rank and opp_rank:
        return my_rank >= UPSET_RANK_RATIO * opp_rank
    return False


def player_streak(history: List[Tuple[bool, bool]], rank: Optional[int]) -> Optional[Dict[str, Any]]:
    """history: chronological (won, upset) for this player's earlier matches in the event."""
    wins = sum(1 for won, _ in history if won)
    last_upset = bool(history) and history[-1][0] and history[-1][1]
    upsets = sum(1 for won, upset in history if won and upset)
    if not wins:
        return None
    return {
        "wins": wins,
        "upsets": upsets,
        "lastUpset": last_upset,
        "lowRankRun": bool(rank and rank > LOW_RANK and wins >= 2),
    }


def streaks_for_matches(db: Session, matches: Iterable[Match]) -> Dict[Any, Dict[str, Any]]:
    """{match_id: {"p1": streak|None, "p2": streak|None}} for tennis matches not yet finished."""
    targets = [m for m in matches if m.league_id and m.match_date and m.status != "FINISHED"]
    if not targets:
        return {}
    start = min(m.match_date for m in targets) - timedelta(days=WINDOW_DAYS)
    end = max(m.match_date for m in targets)
    prior = (
        db.query(Match)
        .filter(
            Match.league_id.in_({m.league_id for m in targets}),
            Match.status == "FINISHED",
            Match.match_date >= start,
            Match.match_date < end,
        )
        .order_by(Match.match_date.asc())
        .all()
    )
    ids = [m.id for m in prior]
    links: Dict[Any, List[MatchCompetitor]] = {}
    for mc in db.query(MatchCompetitor).filter(MatchCompetitor.match_id.in_(ids)).all() if ids else []:
        links.setdefault(mc.match_id, []).append(mc)
    scores = {
        s.match_id: s
        for s in db.query(MatchScore).filter(MatchScore.match_id.in_(ids), MatchScore.period == "FULL_TIME").all()
    } if ids else {}

    # (league, competitor) -> [(date, won, upset)]
    played: Dict[Tuple[Any, Any], List[Tuple[Any, bool, bool]]] = {}
    for m in prior:
        sc = scores.get(m.id)
        sides = {("p1" if mc.side in ("player1", "home") else "p2"): mc for mc in links.get(m.id, [])}
        if not sc or len(sides) != 2 or sc.home_score is None or sc.away_score is None or sc.home_score == sc.away_score:
            continue
        p1_won = sc.home_score > sc.away_score
        extra = m.extra_data or {}
        for side, other in (("p1", "p2"), ("p2", "p1")):
            mc, opp = sides[side], sides[other]
            won = p1_won if side == "p1" else not p1_won
            upset = won and was_upset(_fair(extra, side), mc.pre_match_ranking, opp.pre_match_ranking)
            played.setdefault((m.league_id, mc.competitor_id), []).append((m.match_date, won, upset))

    out: Dict[Any, Dict[str, Any]] = {}
    for m in targets:
        entry = {}
        for mc in m.competitors:
            side = "p1" if mc.side in ("player1", "home") else "p2"
            history = [
                (won, upset)
                for when, won, upset in played.get((m.league_id, mc.competitor_id), [])
                if m.match_date - timedelta(days=WINDOW_DAYS) <= when < m.match_date
            ]
            entry[side] = player_streak(history, mc.pre_match_ranking)
        out[m.id] = entry
    return out
