"""Total games, tiebreaks and deciding sets from the serve/return point model.

`point_model_service` gives each player's point probability on serve against
this opponent. From there the scoring rules give, exactly, the distribution of
total games in the match, the chance of at least one tiebreak and the chance
of a deciding set (3rd set in best of 3, 4th or 5th in best of 5).

Treating every point as independent makes the chain run long: before the
correction it expected 29.3 games where 27.5 were played (AGENTS.md,
2026-10-16). One correction per format, fitted ONLY on matches before
`FROZEN_AT` and written here as constants:
  * GAMES_SHIFT: added to the total games,
  * TIEBREAK_SHIFT / DECIDER_SHIFT: added to the logit of each probability.

Frozen 2026-10-16. The `pointsTotalGames` lab (set1_lab_service.LABS) measures
it walk-forward against the bookmaker's main total-games line; only matches
after the freeze count for the verdict. Do not refit these constants against
post-freeze numbers; if they change, move `FROZEN_AT`.
"""
import math
from collections import defaultdict
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

from src.application.point_model_service import game_prob, match_prob, set_prob, tiebreak_prob

FROZEN_AT = "2026-10-16"
# Fitted on the 2,671 complete matches of 2025-01-01 .. 2026-10-15 (2,092 best
# of 3, 579 best of 5; scratchpad fit_games.py). Before the correction:
#   bo3 games 25.47 vs 23.46 played, tiebreak 48.0% vs 38.5%, deciding set 47.5% vs 35.5%
#   bo5 games 41.40 vs 39.47 played, tiebreak 63.8% vs 56.5%, deciding set 70.4% vs 61.8%
# The chain sees matches as more even than they are.
GAMES_SHIFT = {3: -2.01, 5: -1.94}
TIEBREAK_SHIFT = {3: -0.396, 5: -0.314}
DECIDER_SHIFT = {3: -0.501, 5: -0.391}


def _r(p: float) -> float:
    return round(p, 4)


@lru_cache(maxsize=4096)
def _set_outcomes(pa: float, pb: float, a_serves: bool) -> Tuple[Tuple[bool, int, bool, bool, float], ...]:
    """(A won the set, games in it, A serves first next set, went to a tiebreak, prob)."""
    ha, hb = game_prob(pa), game_prob(pb)
    tb_a = tiebreak_prob(pa, pb) if a_serves else 1.0 - tiebreak_prob(pb, pa)
    out: Dict[Tuple[bool, int, bool, bool], float] = defaultdict(float)
    layer = {(0, 0): 1.0}
    while layer:
        nxt: Dict[Tuple[int, int], float] = defaultdict(float)
        for (ga, gb), p in layer.items():
            games = ga + gb
            server_a = a_serves if games % 2 == 0 else not a_serves
            if ga == 6 and gb == 6:
                # The player who served first in the set receives first in the next one.
                out[(True, 13, not a_serves, True)] += p * tb_a
                out[(False, 13, not a_serves, True)] += p * (1.0 - tb_a)
                continue
            win_a = ha if server_a else 1.0 - hb
            for a_wins, q in ((True, win_a), (False, 1.0 - win_a)):
                na, nb = (ga + 1, gb) if a_wins else (ga, gb + 1)
                if (na >= 6 or nb >= 6) and abs(na - nb) >= 2:
                    next_a = a_serves if (na + nb) % 2 == 0 else not a_serves
                    out[(na > nb, na + nb, next_a, False)] += p * q
                else:
                    nxt[(na, nb)] += p * q
        layer = nxt
    return tuple((k[0], k[1], k[2], k[3], v) for k, v in out.items())


def raw_games_view(pa: float, pb: float, best_of: int) -> Dict[str, Any]:
    """Uncorrected chain: distribution of total games, P(tiebreak), P(deciding set)."""
    pa, pb = round(pa, 4), round(pb, 4)
    need = 3 if best_of >= 5 else 2
    dist: Dict[int, float] = defaultdict(float)
    tiebreak = decider = 0.0
    # state: (sets A, sets B, A serves first, games so far, any tiebreak) -> prob; coin toss for first serve
    state = {(0, 0, True, 0, False): 0.5, (0, 0, False, 0, False): 0.5}
    while state:
        nxt: Dict[Tuple[int, int, bool, int, bool], float] = defaultdict(float)
        for (sa, sb, srv, g, tb), p in state.items():
            for a_won, games, nsrv, set_tb, q in _set_outcomes(pa, pb, srv):
                na, nb = (sa + 1, sb) if a_won else (sa, sb + 1)
                pq = p * q
                any_tb = tb or set_tb
                if na == need or nb == need:
                    dist[g + games] += pq
                    if any_tb:
                        tiebreak += pq
                    if min(na, nb) >= 1:
                        decider += pq
                else:
                    nxt[(na, nb, nsrv, g + games, any_tb)] += pq
        state = nxt
    return {"dist": dict(dist), "tiebreak": tiebreak, "decider": decider}


def _shift_logit(p: float, shift: float) -> float:
    p = min(0.999, max(0.001, p))
    return 1.0 / (1.0 + math.exp(-(math.log(p / (1.0 - p)) + shift)))


def games_view(pa: float, pb: float, best_of: int) -> Dict[str, Any]:
    """Corrected view: expected games, P(tiebreak), P(deciding set), and the dist to price lines."""
    bo = 5 if best_of >= 5 else 3
    raw = raw_games_view(pa, pb, bo)
    shift = GAMES_SHIFT[bo]
    expected = sum(g * p for g, p in raw["dist"].items()) + shift
    return {
        "bestOf": bo,
        "expectedGames": round(expected, 1),
        "tiebreak": _r(_shift_logit(raw["tiebreak"], TIEBREAK_SHIFT[bo])),
        "decider": _r(_shift_logit(raw["decider"], DECIDER_SHIFT[bo])),
        "dist": raw["dist"],
        "shift": shift,
    }


def set_scores(s: float, best_of: int, decider: float) -> Dict[str, float]:
    """Final set score ("2-0", "1-2", ... from player1's side) given P(player1
    wins a set) and the corrected P(deciding set).

    Independent sets fix who wins (`match_prob`, what the pointsMatch lab
    measures) and the split inside each cell; the 2x2 table winner x
    straight-sets is then fitted (iterative proportional fitting) to keep
    P(player1 wins) and make P(not straight sets) = `decider`."""
    need = 3 if best_of >= 5 else 2
    iid: Dict[Tuple[int, int], float] = {}
    for lost in range(need):
        ways = math.comb(need - 1 + lost, lost)
        iid[(need, lost)] = ways * s ** need * (1 - s) ** lost
        iid[(lost, need)] = ways * (1 - s) ** need * s ** lost
    cell = lambda k: (k[0] > k[1], min(k) == 0)
    sums: Dict[Tuple[bool, bool], float] = defaultdict(float)
    for k, p in iid.items():
        sums[cell(k)] += p
    target_win, target_straight = match_prob(s, need * 2 - 1), 1.0 - decider
    table = dict(sums)
    for _ in range(50):
        for w, tgt in ((True, target_win), (False, 1 - target_win)):
            tot = table[(w, True)] + table[(w, False)]
            for st in (True, False):
                table[(w, st)] *= tgt / tot if tot else 0.0
        for st, tgt in ((True, target_straight), (False, 1 - target_straight)):
            tot = table[(True, st)] + table[(False, st)]
            for w in (True, False):
                table[(w, st)] *= tgt / tot if tot else 0.0
    return {f"{a}-{b}": _r(p * table[cell((a, b))] / sums[cell((a, b))]) for (a, b), p in iid.items()}


@lru_cache(maxsize=4096)
def point_markets(pa: float, pb: float, best_of: int) -> Dict[str, Any]:
    """The point model's probability for each predicted tennis market, player1's side.
    Cached: callers must not mutate the result."""
    bo = 5 if best_of >= 5 else 3
    view = games_view(pa, pb, bo)
    s = set_prob(pa, pb)
    return {
        "set1P1": _r(s),
        "matchP1": _r(match_prob(s, bo)),
        "decider": view["decider"],
        "setScores": set_scores(s, bo, view["decider"]),
    }


def over_probability(view: Dict[str, Any], line: float) -> float:
    """P(total games > line) with the frozen shift applied to the games."""
    return sum(p for g, p in view["dist"].items() if g + view["shift"] > line)


def complete_sets(sets: Any) -> Optional[Tuple[int, int, int, bool]]:
    """(games played, sets won by p1, sets won by p2, any tiebreak) for a match
    played to the end; None for a retirement or broken score."""
    from src.application.set1_lab_service import _set_games

    played = [_set_games(s) for s in sets or []]
    if not played or any(g is None for g in played):
        return None
    w1 = w2 = games = 0
    tb = False
    for a, b in played:
        hi, lo = max(a, b), min(a, b)
        if not ((hi == 6 and lo <= 4) or (hi == 7 and lo in (5, 6))):
            return None
        tb = tb or (hi == 7 and lo == 6)
        games += a + b
        w1, w2 = w1 + (a > b), w2 + (b > a)
    need = 3 if max(w1, w2) >= 3 else 2
    if max(w1, w2) != need:
        return None
    return games, w1, w2, tb


def rated_matches(db: Any, until: Optional[str] = None):
    """Finished matches in date order with the point model's (pa, pb, trust) from
    earlier matches only. Yields (match, pa, pb, trust)."""
    from sqlalchemy.orm import joinedload

    from src.application import point_model_service as pm
    from src.domain.models import Match, Sport

    tennis = db.query(Sport).filter(Sport.code == "tennis").first()
    if not tennis:
        return
    q = (
        db.query(Match)
        .options(joinedload(Match.competitors))
        .filter(Match.sport_id == tennis.id, Match.status == "FINISHED", Match.match_date >= pm.HISTORY_START)
    )
    if until:
        q = q.filter(Match.match_date < until)
    logs: Dict[Any, pm.PlayerLog] = defaultdict(pm.PlayerLog)
    tour = defaultdict(lambda: [0.0, 0.0])
    for m in q.order_by(Match.match_date.asc(), Match.id.asc()).all():
        sides = {("p1" if mc.side in ("home", "player1") else "p2"): mc.competitor_id for mc in m.competitors}
        if len(sides) != 2:
            continue
        extra = m.extra_data or {}
        surface = pm._surface(extra)
        won_t, played_t = tour[surface]
        tour_serve = won_t / played_t if played_t >= pm.MIN_TOUR_POINTS else pm.DEFAULT_SERVE_WON
        a = logs[sides["p1"]].rates(m.match_date, surface, tour_serve)
        b = logs[sides["p2"]].rates(m.match_date, surface, tour_serve)
        pa, pb = pm.serve_point_probs(a, b, tour_serve)
        yield m, pa, pb, min(1.0, min(a[2], b[2]) / pm.RELIABLE_POINTS)
        serve = (extra.get("score_stats") or {}).get("serve") or {}
        home = pm._counts(serve.get("home") or {}, serve.get("away") or {})
        away = pm._counts(serve.get("away") or {}, serve.get("home") or {})
        if home and away:
            logs[sides["p1"]].add(m.match_date, surface, *home)
            logs[sides["p2"]].add(m.match_date, surface, *away)
            tour[surface][0] += home[0] + away[0]
            tour[surface][1] += home[1] + away[1]


def build_games_rows(db: Any, include_backfill: bool = False) -> Dict[str, list]:
    """Rows for the `pointsTotalGames` lab: finished matches with the bookmaker's
    main total-games line collected before the start. Same row shape as the
    other labs; the target is "over the line"."""
    from src.application.clv_service import main_line
    from src.timezone import BOGOTA_TZ

    rows = []
    for m, pa, pb, trust in rated_matches(db):
        extra = m.extra_data or {}
        lines = extra.get("odds_lines") or {}
        if extra.get("odds_lines_source") == "backfill":
            if not include_backfill:
                continue
        elif not (m.created_at and m.created_at < m.match_date):
            continue  # a live line collected after the start is not a pre-match price
        line = main_line(lines.get("totalGames"))
        done = complete_sets((extra.get("score_stats") or {}).get("sets"))
        if not line or not done or done[0] == line["line"]:
            continue
        view = games_view(pa, pb, 5 if max(done[1], done[2]) >= 3 else 3)
        over, under = float(line["over"]), float(line["under"])
        p_market = (1.0 / over) / (1.0 / over + 1.0 / under)
        p_model = min(0.999, max(0.001, over_probability(view, float(line["line"]))))
        lm = lambda p: math.log(p / (1.0 - p))  # noqa: E731
        rows.append({
            "date": m.match_date.astimezone(BOGOTA_TZ).date().isoformat(),
            "pMarket": p_market, "won": 1 if done[0] > line["line"] else 0,
            "odds1": over, "odds2": under,
            "x": [trust * (lm(p_model) - lm(p_market))], "pModel": p_model, "trust": trust,
        })
    return {"pointsTotalGames": rows}


SLAMS = ("australian open", "roland garros", "french open", "wimbledon", "us open")


def upcoming_games(db: Any, matches: Any) -> Dict[Any, Dict[str, Any]]:
    """{match_id: public view} for tennis matches still to play. Information only."""
    from src.application.clv_service import main_line
    from src.application.point_model_service import upcoming_set_probabilities

    targets = [m for m in matches if m.status in ("SCHEDULED", "LIVE") and m.sport and m.sport.code == "tennis"]
    if not targets:
        return {}
    points = upcoming_set_probabilities(db)
    out: Dict[Any, Dict[str, Any]] = {}
    for m in targets:
        view = points.get(m.external_id)
        if not view or "pa" not in view:
            continue
        league = (m.league.name if m.league else "") or ""
        best_of = 5 if any(s in league.lower() for s in SLAMS) else 3
        line = main_line(((m.extra_data or {}).get("odds_lines") or {}).get("totalGames"))
        out[m.id] = public_view(games_view(view["pa"], view["pb"], best_of), line, view["trust"])
        out[m.id]["markets"] = point_markets(view["pa"], view["pb"], best_of)
    return out


def public_view(view: Dict[str, Any], line: Optional[Dict[str, Any]], trust: float) -> Dict[str, Any]:
    """What the API exposes for a match still to play."""
    out = {k: view[k] for k in ("bestOf", "expectedGames", "tiebreak", "decider")}
    out["trust"] = round(trust, 2)
    out["line"] = None
    if line:
        over, under = float(line["over"]), float(line["under"])
        fair = (1.0 / over) / (1.0 / over + 1.0 / under)
        out["line"] = {
            "line": float(line["line"]),
            "over": over,
            "under": under,
            "marketOver": _r(fair),
            "modelOver": _r(over_probability(view, float(line["line"]))),
        }
    return out
