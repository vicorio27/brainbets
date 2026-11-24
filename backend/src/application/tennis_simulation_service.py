"""Tennis match simulation: how a match still to play should unfold, set by set.

Built on the point model that is already running (serve-point probabilities of each player, exact
game -> tiebreak -> set -> match chain, see `point_model_service` and `games_model_service`), so it adds
no new model, only a different view of it:
- the likeliest set scores and who wins the match;
- set by set: games expected in each set, the chance the set is played, the chance of a tiebreak in it and
  of player 1 winning it;
- service holds and breaks expected for each player;
- aces per match each player has been averaging, and the H2H, as information.

The point model has NOT beaten the bookmaker (2,272 matches of 2026), and the corrections for games, tiebreak
and deciding set are the ones frozen on 2026-10-16. This describes the likeliest match; it is not a signal.
"""
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session, joinedload

from src.application import games_model_service as gms
from src.application.point_model_service import game_prob, upcoming_set_probabilities
from src.domain.models import Match

RECENT_ACES = 20


def per_set(pa: float, pb: float, best_of: int) -> List[Dict[str, Any]]:
    """For set n = 1..best_of: P(set is played), expected games in it, P(tiebreak | played), P(player1 wins it | played).
    Exact chain from the serve-point probabilities, coin toss for who serves first. Uncorrected games."""
    pa, pb = round(pa, 4), round(pb, 4)
    need = 3 if best_of >= 5 else 2
    rows = [{"played": 0.0, "games": 0.0, "tb": 0.0, "p1": 0.0} for _ in range(best_of)]
    state = {(0, 0, True): 0.5, (0, 0, False): 0.5}
    while state:
        nxt: Dict[Tuple[int, int, bool], float] = defaultdict(float)
        for (sa, sb, srv), p in state.items():
            n = sa + sb
            for a_won, games, nsrv, set_tb, q in gms._set_outcomes(pa, pb, srv):
                pq = p * q
                r = rows[n]
                r["played"] += pq
                r["games"] += pq * games
                r["tb"] += pq * (1.0 if set_tb else 0.0)
                r["p1"] += pq * (1.0 if a_won else 0.0)
                na, nb = (sa + 1, sb) if a_won else (sa, sb + 1)
                if na < need and nb < need:
                    nxt[(na, nb, nsrv)] += pq
        state = nxt
    out = []
    for i, r in enumerate(rows):
        pl = r["played"]
        out.append({"set": i + 1, "played": round(pl, 4),
                    "games": round(r["games"] / pl, 2) if pl > 1e-9 else None,
                    "tiebreak": round(r["tb"] / pl, 4) if pl > 1e-9 else None,
                    "p1Wins": round(r["p1"] / pl, 4) if pl > 1e-9 else None})
    return out


def apply_games_shift(sets: List[Dict[str, Any]], shift: float) -> List[Dict[str, Any]]:
    """Spread the frozen games correction evenly over the sets that get played: each set's games move by
    shift / (expected sets), so the match total moves by exactly `shift`."""
    total = sum(s["played"] for s in sets) or 1.0
    out = []
    for s in sets:
        g = None if s["games"] is None else round(max(s["games"] + shift / total, 0.0), 2)
        out.append({**s, "games": g})
    return out


def _with_corrected_decider(sets: List[Dict[str, Any]], decider: float) -> List[Dict[str, Any]]:
    """The last set is played exactly when the match goes the distance: use the corrected (frozen) probability."""
    out = [dict(x) for x in sets]
    out[-1]["played"] = round(decider, 4)
    return out


def holds_and_breaks(pa: float, pb: float, expected_games: float) -> Dict[str, Any]:
    """Service games held and breaks per player. About half of the games are on each serve (a tiebreak counts as a game)."""
    ha, hb = game_prob(pa), game_prob(pb)
    served = expected_games / 2.0
    return {"p1": {"hold": round(ha, 3), "breaksExpected": round(served * (1 - hb), 2)},
            "p2": {"hold": round(hb, 3), "breaksExpected": round(served * (1 - ha), 2)}}


def _aces(db: Session, competitor_id) -> Optional[Dict[str, Any]]:
    from src.domain.models import MatchCompetitor

    rows = (db.query(Match, MatchCompetitor.side).join(MatchCompetitor, MatchCompetitor.match_id == Match.id)
            .filter(MatchCompetitor.competitor_id == competitor_id, Match.status == "FINISHED",
                    Match.extra_data["score_stats"].isnot(None))
            .order_by(Match.match_date.desc()).limit(60).all())
    vals = []
    for m, side in rows:
        ss = (m.extra_data or {}).get("score_stats") or {}
        v = ss.get("homeAces" if side in ("home", "player1") else "awayAces")
        if v is not None:
            vals.append(float(v))
        if len(vals) >= RECENT_ACES:
            break
    return {"perMatch": round(sum(vals) / len(vals), 1), "matches": len(vals)} if len(vals) >= 3 else None


def simulate(db: Session, external_id: str) -> Optional[Dict[str, Any]]:
    from src.application.h2h_service import h2h_for_matches

    m = (db.query(Match).options(joinedload(Match.competitors)).filter(Match.external_id == external_id).first())
    if m is None:
        return None
    view = upcoming_set_probabilities(db).get(external_id)
    if not view or "pa" not in view:
        return {"available": False, "reason": "Sin estadísticas de saque suficientes para este partido o ya empezó."}
    league = (m.league.name if m.league else "") or ""
    best_of = 5 if any(s in league.lower() for s in gms.SLAMS) else 3
    pa, pb = view["pa"], view["pb"]
    gv = gms.games_view(pa, pb, best_of)
    markets = gms.point_markets(pa, pb, best_of)
    sides = {("p1" if mc.side in ("home", "player1") else "p2"): mc for mc in m.competitors}
    names = {k: v.competitor.name for k, v in sides.items()}
    scores = sorted(({"score": k, "p": v} for k, v in markets["setScores"].items()), key=lambda x: -x["p"])
    h2h = h2h_for_matches(db, [m]).get(m.id)
    return {
        "available": True, "bestOf": best_of, "player1": names.get("p1"), "player2": names.get("p2"),
        "trust": round(view["trust"], 2),
        "servePointsWon": {"p1": round(pa, 3), "p2": round(pb, 3)},
        "matchWin": {"p1": markets["matchP1"], "p2": round(1 - markets["matchP1"], 4)},
        "setScores": scores,
        "expectedGames": gv["expectedGames"], "tiebreak": gv["tiebreak"], "decider": gv["decider"],
        "sets": _with_corrected_decider(apply_games_shift(per_set(pa, pb, best_of), gv["shift"]), gv["decider"]),
        "serve": holds_and_breaks(pa, pb, gv["expectedGames"]),
        "aces": {"p1": _aces(db, sides["p1"].competitor_id) if "p1" in sides else None,
                 "p2": _aces(db, sides["p2"].competitor_id) if "p2" in sides else None},
        "h2h": h2h,
        "note": ("Vista del modelo de puntos de saque y resto: no le ha ganado a la cuota (2.272 partidos de 2026), así que "
                 "describe el partido más probable y no es una señal de apuesta. Los games por set llevan la corrección "
                 "congelada el 16-oct repartida entre los sets."),
    }
