"""Serve/return point model for tennis, tested as a shadow model against the price.

The engine's signals (Elo, ranking, form) are what the bookmaker already
prices. This is the other standard way to model tennis: estimate how often
each player wins a point on serve against THIS opponent, and derive games,
sets and the match from that with the scoring rules (a Markov chain).

    serve point prob of A vs B = tour average
                                 + (A's serve points won   - tour average)
                                 - (B's return points won  - tour average)

Each player's rates come only from matches played before the one being
scored, weighted by recency and surface, and shrunk towards the tour average
so a handful of matches does not look like a trait.

It serves no probability. `build_point_rows` produces rows for three labs in
`set1_lab_service.LABS` (first set, match, total sets) whose single signal is
how far this model sits from the market, scaled by how much history backs it:
the lab then measures, walk-forward, whether moving the price towards the
model helps. Specification frozen 2026-10-13, written before looking at any
score; do not tune it against the post-freeze numbers.
"""
import math
from collections import defaultdict
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session, joinedload

from src.domain.models import Match, Sport
from src.timezone import BOGOTA_TZ

# ---- frozen specification ---------------------------------------------------
HISTORY_START = "2025-01-01"
HALF_LIFE_DAYS = 240.0        # a match this old counts half
OTHER_SURFACE_WEIGHT = 0.5    # matches on another surface count half
PRIOR_POINTS = 300.0          # pseudo serve points at the tour average
RELIABLE_POINTS = 600.0       # weighted serve points (~10 matches) for full trust
DEFAULT_SERVE_WON = 0.64      # tour average until the data provides its own
MIN_TOUR_POINTS = 20000.0


# ---- scoring rules ----------------------------------------------------------
def game_prob(p: float) -> float:
    """Probability the server wins a game when they win each point with `p`."""
    q = 1.0 - p
    deuce = p * p / (p * p + q * q)
    return p ** 4 * (1 + 4 * q + 10 * q * q) + 20 * p ** 3 * q ** 3 * deuce


def tiebreak_prob(pa: float, pb: float) -> float:
    """A wins a first-to-7 tiebreak; A serves the first point, then two each."""
    win_pair = pa * (1.0 - pb)       # A wins both points of a serve pair
    lose_pair = (1.0 - pa) * pb
    from_six_all = win_pair / (win_pair + lose_pair) if win_pair + lose_pair > 0 else 0.5

    @lru_cache(maxsize=None)
    def go(a: int, b: int) -> float:
        if a == 6 and b == 6:
            return from_six_all
        if a == 7:
            return 1.0
        if b == 7:
            return 0.0
        played = a + b
        a_serves = played == 0 or ((played - 1) // 2) % 2 == 1
        p = pa if a_serves else 1.0 - pb
        return p * go(a + 1, b) + (1.0 - p) * go(a, b + 1)

    return go(0, 0)


def set_prob(pa: float, pb: float) -> float:
    """A wins a tiebreak set. Averaged over who serves first (unknown pre-match)."""
    return 0.5 * (_set_prob_serving_first(pa, pb) + 1.0 - _set_prob_serving_first(pb, pa))


def _set_prob_serving_first(pa: float, pb: float) -> float:
    hold_a, hold_b = game_prob(pa), game_prob(pb)
    tiebreak = tiebreak_prob(pa, pb)

    @lru_cache(maxsize=None)
    def go(a: int, b: int) -> float:
        if a == 6 and b == 6:
            return tiebreak
        if a >= 6 and a - b >= 2 or a == 7:
            return 1.0
        if b >= 6 and b - a >= 2 or b == 7:
            return 0.0
        p = hold_a if (a + b) % 2 == 0 else 1.0 - hold_b
        return p * go(a + 1, b) + (1.0 - p) * go(a, b + 1)

    return go(0, 0)


def match_prob(s: float, best_of: int) -> float:
    """A wins the match when they win each set with `s` (sets independent)."""
    if best_of >= 5:
        return s ** 3 * (10 - 15 * s + 6 * s * s)
    return s * s * (3 - 2 * s)


def deciding_sets_prob(s: float, best_of: int) -> float:
    """The match goes past the minimum: 3 sets in best of 3, 4 or 5 in best of 5."""
    if best_of >= 5:
        return 1.0 - (s ** 3 + (1.0 - s) ** 3)
    return 2.0 * s * (1.0 - s)


# ---- player rates -----------------------------------------------------------
class PlayerLog:
    """Serve and return point counts of a player's past matches."""

    __slots__ = ("rows",)

    def __init__(self) -> None:
        self.rows: List[Tuple[Any, str, float, float, float, float]] = []

    def add(self, when: Any, surface: str, serve_won: float, serve_total: float,
            return_won: float, return_total: float) -> None:
        self.rows.append((when, surface, serve_won, serve_total, return_won, return_total))

    def rates(self, when: Any, surface: str, tour_serve: float) -> Tuple[float, float, float]:
        """(serve points won, return points won, weighted serve points behind them)."""
        sw = st = rw = rt = 0.0
        for date, surf, a, b, c, d in self.rows:
            age = (when - date).total_seconds() / 86400.0
            w = 0.5 ** (age / HALF_LIFE_DAYS) * (1.0 if surf == surface else OTHER_SURFACE_WEIGHT)
            sw += w * a
            st += w * b
            rw += w * c
            rt += w * d
        serve = (sw + PRIOR_POINTS * tour_serve) / (st + PRIOR_POINTS)
        ret = (rw + PRIOR_POINTS * (1.0 - tour_serve)) / (rt + PRIOR_POINTS)
        return serve, ret, st


def serve_point_probs(a: Tuple[float, float, float], b: Tuple[float, float, float], tour_serve: float) -> Tuple[float, float]:
    """(A's point probability on serve vs B, B's vs A), each player's serve
    measured against the other's return."""
    tour_return = 1.0 - tour_serve
    pa = tour_serve + (a[0] - tour_serve) - (b[1] - tour_return)
    pb = tour_serve + (b[0] - tour_serve) - (a[1] - tour_return)
    return min(0.85, max(0.45, pa)), min(0.85, max(0.45, pb))


def _logit(p: float) -> float:
    p = min(0.999, max(0.001, p))
    return math.log(p / (1.0 - p))


def _surface(extra: Dict[str, Any]) -> str:
    s = str(extra.get("surface") or "").lower()
    if "clay" in s:
        return "clay"
    if "grass" in s:
        return "grass"
    return "hard"


def _counts(side: Dict[str, Any], other: Dict[str, Any]) -> Optional[Tuple[float, float, float, float]]:
    try:
        won, total = float(side["servePtsWon"]), float(side["servePtsTotal"])
        opp_won, opp_total = float(other["servePtsWon"]), float(other["servePtsTotal"])
    except (KeyError, TypeError, ValueError):
        return None
    if total <= 0 or opp_total <= 0 or won > total or opp_won > opp_total:
        return None
    return won, total, opp_total - opp_won, opp_total


def build_point_rows(db: Session, include_backfill: bool = False) -> Dict[str, List[Dict[str, Any]]]:
    """Rows for the three point-model labs, from one chronological pass.

    `include_backfill` also scores matches whose prices were fetched afterwards
    from the provider's historical feed (`odds_markets_backfill`). The daily
    labs leave it off: their verdict only counts prices we collected ourselves
    before the match. It exists to test the frozen model on a large sample of
    past matches at once.
    """
    from src.application.set1_lab_service import _set_games, _total_sets_odds, no_margin_probability

    out: Dict[str, List[Dict[str, Any]]] = {"pointsSet1": [], "pointsMatch": [], "pointsTotalSets": []}
    tennis = db.query(Sport).filter(Sport.code == "tennis").first()
    if not tennis:
        return out
    matches = (
        db.query(Match)
        .options(joinedload(Match.competitors))
        .filter(Match.sport_id == tennis.id, Match.status == "FINISHED")
        .filter(Match.match_date >= HISTORY_START)
        .order_by(Match.match_date.asc(), Match.id.asc())
        .all()
    )
    logs: Dict[Any, PlayerLog] = defaultdict(PlayerLog)
    tour = defaultdict(lambda: [0.0, 0.0])  # surface -> [serve points won, played]

    for m in matches:
        sides = {("p1" if mc.side in ("home", "player1") else "p2"): mc.competitor_id for mc in m.competitors}
        if len(sides) != 2:
            continue
        extra = m.extra_data or {}
        stats = extra.get("score_stats") or {}
        sets = stats.get("sets") or []
        surface = _surface(extra)
        won_t, played_t = tour[surface]
        tour_serve = won_t / played_t if played_t >= MIN_TOUR_POINTS else DEFAULT_SERVE_WON

        markets = extra.get("odds_markets") or {}
        if not (markets and m.created_at is not None and m.created_at < m.match_date):
            markets = (extra.get("odds_markets_backfill") or {}) if include_backfill else {}
        played = [g for g in (_set_games(s) for s in sets) if g and g[0] != g[1]]
        won1, won2 = sum(1 for g in played if g[0] > g[1]), sum(1 for g in played if g[1] > g[0])
        if markets and played:
            a = logs[sides["p1"]].rates(m.match_date, surface, tour_serve)
            b = logs[sides["p2"]].rates(m.match_date, surface, tour_serve)
            pa, pb = serve_point_probs(a, b, tour_serve)
            s = set_prob(pa, pb)
            trust = min(1.0, min(a[2], b[2]) / RELIABLE_POINTS)
            day = m.match_date.astimezone(BOGOTA_TZ).date().isoformat()

            def row(p_model: float, p_market: Optional[float], won: int, o1: float, o2: float) -> Optional[Dict[str, Any]]:
                if not p_market:
                    return None
                return {"date": day, "pMarket": p_market, "won": won, "odds1": float(o1), "odds2": float(o2),
                        "x": [trust * (_logit(p_model) - _logit(p_market))], "pModel": p_model, "trust": trust}

            s1 = markets.get("set1Winner") or {}
            r = row(s, no_margin_probability(s1.get("p1"), s1.get("p2")), 1 if played[0][0] > played[0][1] else 0,
                    s1.get("p1") or 0, s1.get("p2") or 0)
            if r:
                out["pointsSet1"].append(r)

            if won1 != won2 and max(won1, won2) >= 2:
                best_of = 5 if max(won1, won2) >= 3 else 3
                mw = markets.get("matchWinner") or {}
                r = row(match_prob(s, best_of), no_margin_probability(mw.get("p1"), mw.get("p2")),
                        1 if won1 > won2 else 0, mw.get("p1") or 0, mw.get("p2") or 0)
                if r:
                    out["pointsMatch"].append(r)
                ou = _total_sets_odds(markets.get("numberOfSets") or {}, best_of)
                if ou:
                    r = row(deciding_sets_prob(s, best_of), no_margin_probability(ou[0], ou[1]),
                            1 if min(won1, won2) >= 1 else 0, ou[0], ou[1])
                    if r:
                        out["pointsTotalSets"].append(r)

        serve = stats.get("serve") or {}
        home, away = _counts(serve.get("home") or {}, serve.get("away") or {}), _counts(serve.get("away") or {}, serve.get("home") or {})
        if home and away:
            logs[sides["p1"]].add(m.match_date, surface, *home)
            logs[sides["p2"]].add(m.match_date, surface, *away)
            tour[surface][0] += home[0] + away[0]
            tour[surface][1] += home[1] + away[1]
    return out
