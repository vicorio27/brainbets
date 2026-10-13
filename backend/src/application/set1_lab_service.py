"""Lab: can serve/return/workload signals beat the bookmaker on Set 1 Winner?

This is a *shadow* model. It never touches a served probability. Its only
job is to answer, with data that keeps arriving, whether signals we already
store explain anything the market price leaves unexplained -- so that a
signal is promoted into the engine because it earned it, not because it
sounded right (which is how the inflated edge of 2026-10 happened).

Method
  * Walk every finished tennis match in date order keeping per-player running
    totals built ONLY from earlier matches (no look-ahead), shrunk towards the
    tour average so three matches do not look like a trait.
  * Target: player1 wins the first set.
  * Baseline: the market's no-margin probability from the Set 1 odds stored
    at collection, restricted to matches first collected before their start.
  * Model: logistic regression with the market's logit as a fixed OFFSET, so
    the features can only add to the price, never replace it.
  * Test: expanding walk-forward by day -- each day is predicted by a model
    fitted on strictly earlier days.

The specification below (features, shrinkage, regularisation) was chosen on
2026-10-10 looking at 123 matches, which means those matches are not a clean
test. `FROZEN_AT` marks that date: the verdict only counts matches played
AFTER it, which nobody looked at when choosing the spec. Do not tune the spec
against the post-freeze numbers; if it changes, move `FROZEN_AT` to that day.

First look (2026-10-10, n=123, 62 tested): hold%, first-serve points won and
recent workload correlated with the market's error (|z| 2.4-2.8); walk-forward
log-loss 0.6182 (market) -> 0.5951, improvement +0.023 with a 95% CI of
-0.029 to +0.074. Suggestive, not demonstrated. The same signals on Match
Winner made things significantly worse, so only Set 1 is tracked.
"""
import json
import logging
import math
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from sqlalchemy.orm import Session, joinedload

from src.domain.models import Match, MatchCompetitor, Sport
from src.timezone import BOGOTA_TZ

logger = logging.getLogger(__name__)

LAB_DIR = os.environ.get("CALIBRATION_MODEL_DIR", "/storage/models")
LAB_PATH = os.path.join(LAB_DIR, "set1_lab.json")

# ---- frozen specification (see module docstring before touching) ----------
FROZEN_AT = "2026-10-10"
FEATURES = ("hold", "brk", "fs", "aces", "s1", "tb", "rest", "fresh", "load")
FEATURE_LABELS = {
    "hold": "Juegos de saque ganados",
    "brk": "Juegos de resto ganados",
    "fs": "Puntos ganados con 1er saque",
    "aces": "Aces por partido",
    "s1": "Primeros sets ganados",
    "tb": "Tiebreaks ganados",
    "rest": "Días de descanso",
    "fresh": "Jugó ayer",
    "load": "Partidos en los últimos 10 días",
}
REGULARISATION_C = 0.05
SHRINK_MATCHES = 6.0
TOUR_PRIOR = {"hold": 0.80, "brk": 0.22, "fs": 0.73, "aces": 7.5}
MIN_TRAIN_ROWS = 60
BET_EDGE = 0.03
# Promotion bar: enough untouched matches AND an improvement whose 95% CI
# excludes zero. Until then the lab only reports.
MIN_POST_FREEZE = 300
HISTORY_START = "2026-07-20"  # serve statistics exist from late July 2026

# ---- other markets under the same test (added 2026-10-13) -----------------
# Same method, same promotion bar, their own freeze date: these specs were
# written WITHOUT looking at how they score, so everything after the freeze is
# a clean test. (An earlier informal look at Match Winner with the Set 1
# signals made things worse; it is tracked anyway so the answer is on record.)
# Total Sets is not about who wins but about how even the match is, so its
# signals are symmetric: gaps between the players and sums of both.
TOTAL_FEATURES = ("gapHold", "gapBrk", "gapFs", "sumHold", "sumAces", "sumLoad", "minRest")
TOTAL_FEATURE_LABELS = {
    "gapHold": "Diferencia de juegos de saque ganados",
    "gapBrk": "Diferencia de juegos de resto ganados",
    "gapFs": "Diferencia de puntos con 1er saque",
    "sumHold": "Saque de ambos (suma)",
    "sumAces": "Aces de ambos (suma)",
    "sumLoad": "Partidos recientes de ambos (suma)",
    "minRest": "Descanso del que menos descansó",
}
POINT_FEATURES = ("model",)
POINT_FEATURE_LABELS = {"model": "Distancia del modelo de puntos a la cuota"}
LABS = {
    "set1": {"market": "Set 1 Winner", "frozenAt": FROZEN_AT, "features": FEATURES, "labels": FEATURE_LABELS,
             "file": "set1_lab.json"},
    "matchWinner": {"market": "Match Winner", "frozenAt": "2026-10-13", "features": FEATURES, "labels": FEATURE_LABELS,
                    "file": "match_winner_lab.json"},
    "totalSets": {"market": "Total Sets", "frozenAt": "2026-10-13", "features": TOTAL_FEATURES,
                  "labels": TOTAL_FEATURE_LABELS, "file": "total_sets_lab.json"},
    # Serve/return point model (point_model_service): one signal, how far that
    # model sits from the price, scaled by how much history backs it.
    "pointsSet1": {"market": "Set 1 Winner", "frozenAt": "2026-10-13", "features": POINT_FEATURES,
                   "labels": POINT_FEATURE_LABELS, "file": "points_set1_lab.json"},
    "pointsMatch": {"market": "Match Winner", "frozenAt": "2026-10-13", "features": POINT_FEATURES,
                    "labels": POINT_FEATURE_LABELS, "file": "points_match_lab.json"},
    "pointsTotalSets": {"market": "Total Sets", "frozenAt": "2026-10-13", "features": POINT_FEATURES,
                        "labels": POINT_FEATURE_LABELS, "file": "points_total_sets_lab.json"},
}


class _Totals:
    """Running per-player totals from matches already played."""

    __slots__ = ("sg_w", "sg_t", "rg_w", "rg_t", "fs_w", "fs_t", "aces", "aces_n",
                 "s1_w", "s1_n", "tb_w", "tb_n", "last", "recent")

    def __init__(self) -> None:
        self.sg_w = self.sg_t = self.rg_w = self.rg_t = 0
        self.fs_w = self.fs_t = 0
        self.aces = 0.0
        self.aces_n = 0
        self.s1_w = self.s1_n = self.tb_w = self.tb_n = 0
        self.last: Optional[datetime] = None
        self.recent: List[datetime] = []


def _shrunk(won: float, total: float, prior: float, per_match: float) -> float:
    """Rate pulled towards `prior` by `SHRINK_MATCHES` average matches."""
    pseudo = SHRINK_MATCHES * per_match
    return (won + pseudo * prior) / (total + pseudo)


def player_features(t: _Totals, when: datetime) -> Dict[str, float]:
    rest = (when - t.last).total_seconds() / 86400.0 if t.last else 14.0
    return {
        "hold": _shrunk(t.sg_w, t.sg_t, TOUR_PRIOR["hold"], 10.0),
        "brk": _shrunk(t.rg_w, t.rg_t, TOUR_PRIOR["brk"], 10.0),
        "fs": _shrunk(t.fs_w, t.fs_t, TOUR_PRIOR["fs"], 40.0),
        "aces": (t.aces + SHRINK_MATCHES * TOUR_PRIOR["aces"]) / (t.aces_n + SHRINK_MATCHES),
        "s1": (t.s1_w + SHRINK_MATCHES * 0.5) / (t.s1_n + SHRINK_MATCHES),
        "tb": (t.tb_w + 1.5) / (t.tb_n + 3.0),
        "rest": min(rest, 21.0),
        "fresh": 1.0 if rest <= 1.5 else 0.0,
        "load": float(sum(1 for d in t.recent if (when - d).days <= 10)),
    }


def no_margin_probability(odds_1: Any, odds_2: Any) -> Optional[float]:
    try:
        o1, o2 = float(odds_1), float(odds_2)
    except (TypeError, ValueError):
        return None
    if o1 <= 1.0 or o2 <= 1.0:
        return None
    return (1.0 / o1) / (1.0 / o1 + 1.0 / o2)


def _set_games(row: Any) -> Optional[Tuple[int, int]]:
    try:
        return int(row.get("p1") or 0), int(row.get("p2") or 0)
    except (AttributeError, TypeError, ValueError):
        return None


def _total_features(f1: Dict[str, float], f2: Dict[str, float]) -> List[float]:
    return [
        abs(f1["hold"] - f2["hold"]),
        abs(f1["brk"] - f2["brk"]),
        abs(f1["fs"] - f2["fs"]),
        f1["hold"] + f2["hold"],
        f1["aces"] + f2["aces"],
        f1["load"] + f2["load"],
        min(f1["rest"], f2["rest"]),
    ]


def _total_sets_odds(number_of_sets: Dict[str, Any], best_of: int) -> Optional[Tuple[float, float]]:
    """(over, under) decimal odds for the deciding-sets line: 2.5 in best of 3, 3.5 in best of 5."""
    def price(key: str) -> Optional[float]:
        try:
            value = float(number_of_sets.get(key))
        except (TypeError, ValueError):
            return None
        return value if value > 1.0 else None

    if best_of >= 5:
        four, five, under = price("4"), price("5"), price("3")
        over = 1.0 / (1.0 / four + 1.0 / five) if four and five else None
    else:
        over, under = price("3"), price("2")
    return (over, under) if over and under and over > 1.0 else None


def build_rows(db: Session) -> List[Dict[str, Any]]:
    """One row per finished match with pre-match Set 1 odds and a first set."""
    return build_all_rows(db)["set1"]


def build_all_rows(db: Session) -> Dict[str, List[Dict[str, Any]]]:
    """Rows for every lab in `LABS`, from one pass over the finished matches."""
    all_rows: Dict[str, List[Dict[str, Any]]] = {key: [] for key in ("set1", "matchWinner", "totalSets")}
    tennis = db.query(Sport).filter(Sport.code == "tennis").first()
    if not tennis:
        return all_rows
    matches = (
        db.query(Match)
        .options(joinedload(Match.competitors))
        .filter(Match.sport_id == tennis.id, Match.status == "FINISHED")
        .filter(Match.match_date >= HISTORY_START)
        .order_by(Match.match_date.asc(), Match.id.asc())
        .all()
    )

    totals: Dict[Any, _Totals] = defaultdict(_Totals)
    rows = all_rows["set1"]
    for m in matches:
        sides = {
            ("p1" if mc.side in ("home", "player1") else "p2"): mc.competitor_id
            for mc in m.competitors
        }
        if len(sides) != 2:
            continue
        extra = m.extra_data or {}
        stats = extra.get("score_stats") or {}
        sets = stats.get("sets") or []
        t1, t2 = totals[sides["p1"]], totals[sides["p2"]]

        # Row first (features see only the past), totals after.
        odds = (extra.get("odds_markets") or {}).get("set1Winner") or {}
        p_market = no_margin_probability(odds.get("p1"), odds.get("p2"))
        first = _set_games(sets[0]) if sets else None
        collected_before_start = m.created_at is not None and m.created_at < m.match_date
        if p_market and first and first[0] != first[1] and collected_before_start:
            f1, f2 = player_features(t1, m.match_date), player_features(t2, m.match_date)
            rows.append(
                {
                    "date": m.match_date.astimezone(BOGOTA_TZ).date().isoformat(),
                    "pMarket": p_market,
                    "won": 1 if first[0] > first[1] else 0,
                    "odds1": float(odds["p1"]),
                    "odds2": float(odds["p2"]),
                    "x": [f1[k] - f2[k] for k in FEATURES],
                }
            )

        # Match-level labs need a completed match: a winner with 2 (or 3) sets.
        played = [g for g in (_set_games(s) for s in sets) if g and g[0] != g[1]]
        won1, won2 = sum(1 for g in played if g[0] > g[1]), sum(1 for g in played if g[1] > g[0])
        if collected_before_start and won1 != won2 and max(won1, won2) >= 2:
            day = m.match_date.astimezone(BOGOTA_TZ).date().isoformat()
            markets = extra.get("odds_markets") or {}
            f1, f2 = player_features(t1, m.match_date), player_features(t2, m.match_date)

            mw = markets.get("matchWinner") or {}
            p_match = no_margin_probability(mw.get("p1"), mw.get("p2"))
            if p_match:
                all_rows["matchWinner"].append({
                    "date": day, "pMarket": p_match, "won": 1 if won1 > won2 else 0,
                    "odds1": float(mw["p1"]), "odds2": float(mw["p2"]),
                    "x": [f1[k] - f2[k] for k in FEATURES],
                })

            best_of = 5 if max(won1, won2) >= 3 else 3
            ou = _total_sets_odds(markets.get("numberOfSets") or {}, best_of)
            if ou:
                all_rows["totalSets"].append({
                    "date": day, "pMarket": no_margin_probability(ou[0], ou[1]),
                    "won": 1 if min(won1, won2) >= (2 if best_of >= 5 else 1) else 0,  # "over" came in
                    "odds1": ou[0], "odds2": ou[1],
                    "x": _total_features(f1, f2),
                })

        serve = stats.get("serve") or {}
        for side, t, key in (("p1", t1, "home"), ("p2", t2, "away")):
            sv = serve.get(key) or {}
            try:
                if int(sv.get("serveGamesTotal") or 0):
                    t.sg_w += int(sv.get("serveGamesWon") or 0)
                    t.sg_t += int(sv.get("serveGamesTotal") or 0)
                    t.rg_w += int(sv.get("returnGamesWon") or 0)
                    t.rg_t += int(sv.get("returnGamesTotal") or 0)
                    t.fs_w += int(sv.get("firstServeWon") or 0)
                    t.fs_t += int(sv.get("firstServeTotal") or 0)
            except (TypeError, ValueError):
                pass
            aces = stats.get(f"{key}Aces")
            if aces is not None:
                try:
                    t.aces += float(aces)
                    t.aces_n += 1
                except (TypeError, ValueError):
                    pass
            for i, row in enumerate(sets):
                games = _set_games(row)
                if not games:
                    continue
                mine, theirs = games if side == "p1" else games[::-1]
                if i == 0 and mine != theirs:
                    t.s1_n += 1
                    t.s1_w += 1 if mine > theirs else 0
                if set(games) == {7, 6}:
                    t.tb_n += 1
                    t.tb_w += 1 if mine == 7 else 0
            t.last = m.match_date
            t.recent.append(m.match_date)
    return all_rows


def _logit(p: float) -> float:
    p = min(0.999, max(0.001, p))
    return math.log(p / (1.0 - p))


def fit_offset_logistic(x: np.ndarray, y: np.ndarray, offset: np.ndarray, c: float = REGULARISATION_C) -> np.ndarray:
    """L2 logistic regression where `offset` (the market logit) is fixed."""
    w = np.zeros(x.shape[1])
    n = len(y)
    for _ in range(3000):
        p = 1.0 / (1.0 + np.exp(-(offset + x @ w)))
        w -= 0.5 * (x.T @ (p - y) / n + w / (c * n))
    return w


def walk_forward(rows: Sequence[Dict[str, Any]]) -> List[Optional[float]]:
    """Model probability per row, each from a fit on strictly earlier days;
    None while there are fewer than `MIN_TRAIN_ROWS` earlier rows."""
    preds: List[Optional[float]] = [None] * len(rows)
    if not rows:
        return preds
    x = np.array([r["x"] for r in rows], dtype=float)
    y = np.array([r["won"] for r in rows], dtype=float)
    off = np.array([_logit(r["pMarket"]) for r in rows])
    i = 0
    while i < len(rows):
        j = i
        while j < len(rows) and rows[j]["date"] == rows[i]["date"]:
            j += 1
        if i >= MIN_TRAIN_ROWS:
            mu, sd = x[:i].mean(0), x[:i].std(0) + 1e-9
            w = fit_offset_logistic((x[:i] - mu) / sd, y[:i], off[:i])
            p = 1.0 / (1.0 + np.exp(-(off[i:j] + ((x[i:j] - mu) / sd) @ w)))
            for k in range(i, j):
                preds[k] = float(p[k - i])
        i = j
    return preds


def _per_row_loss(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-3, 1 - 1e-3)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def score(rows: Sequence[Dict[str, Any]], preds: Sequence[Optional[float]]) -> Dict[str, Any]:
    """Market vs model on the rows that have a walk-forward prediction."""
    idx = [i for i, p in enumerate(preds) if p is not None]
    out: Dict[str, Any] = {"matches": len(idx)}
    if not idx:
        return out
    y = np.array([rows[i]["won"] for i in idx], dtype=float)
    pm = np.array([rows[i]["pMarket"] for i in idx])
    pp = np.array([preds[i] for i in idx], dtype=float)
    gain = _per_row_loss(pm, y) - _per_row_loss(pp, y)  # >0: model beats market
    rng = np.random.default_rng(20261010)
    boots = [gain[rng.integers(0, len(gain), len(gain))].mean() for _ in range(2000)] if len(gain) > 1 else [0.0]
    lo, hi = np.percentile(boots, [2.5, 97.5])

    profits: List[float] = []
    for k, i in enumerate(idx):
        r = rows[i]
        for prob, odds, win in ((pp[k], r["odds1"], r["won"] == 1), (1 - pp[k], r["odds2"], r["won"] == 0)):
            if prob * odds - 1.0 > BET_EDGE:
                profits.append(odds - 1.0 if win else -1.0)
    bets: Dict[str, Any] = {"bets": len(profits), "yield": None, "yieldCiLow": None, "yieldCiHigh": None}
    if profits:
        pr = np.array(profits)
        se = float(pr.std(ddof=1) / math.sqrt(len(pr))) if len(pr) > 1 else 0.0
        bets.update(
            {
                "yield": round(float(pr.mean()) * 100, 1),
                "yieldCiLow": round((float(pr.mean()) - 1.96 * se) * 100, 1),
                "yieldCiHigh": round((float(pr.mean()) + 1.96 * se) * 100, 1),
            }
        )
    out.update(
        {
            "from": rows[idx[0]]["date"],
            "to": rows[idx[-1]]["date"],
            "logLossMarket": round(float(_per_row_loss(pm, y).mean()), 4),
            "logLossModel": round(float(_per_row_loss(pp, y).mean()), 4),
            "improvement": round(float(gain.mean()), 4),
            "improvementCiLow": round(float(lo), 4),
            "improvementCiHigh": round(float(hi), 4),
            **bets,
        }
    )
    return out


def verdict_for(post_freeze: Dict[str, Any]) -> Dict[str, Any]:
    n = post_freeze.get("matches", 0)
    if n < MIN_POST_FREEZE:
        return {"level": "juntando_muestra", "matches": n, "needed": MIN_POST_FREEZE}
    if post_freeze["improvementCiLow"] > 0:
        return {"level": "demostrado", "matches": n, "needed": MIN_POST_FREEZE}
    if post_freeze["improvementCiHigh"] < 0:
        return {"level": "descartado", "matches": n, "needed": MIN_POST_FREEZE}
    return {"level": "no_demostrado", "matches": n, "needed": MIN_POST_FREEZE}


def run_lab(db: Session) -> Dict[str, Any]:
    """Recompute every lab's report and store it (called by the daily
    training). Returns the Set 1 report; the others are read back with
    `get_lab_report(key)`."""
    from src.application.point_model_service import build_point_rows

    all_rows = {**build_all_rows(db), **build_point_rows(db)}
    reports = {key: _report(key, all_rows[key]) for key in LABS}
    return reports["set1"]


def _report(key: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    spec = LABS[key]
    preds = walk_forward(rows)
    post = [(r, p) for r, p in zip(rows, preds) if r["date"] > spec["frozenAt"]]
    report = {
        "version": 1,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "market": spec["market"],
        "frozenAt": spec["frozenAt"],
        "rows": len(rows),
        "allWalkForward": score(rows, preds),
        "postFreeze": score([r for r, _ in post], [p for _, p in post]),
        "weights": None,
    }
    report["verdict"] = verdict_for(report["postFreeze"])
    if len(rows) >= MIN_TRAIN_ROWS:
        x = np.array([r["x"] for r in rows], dtype=float)
        y = np.array([r["won"] for r in rows], dtype=float)
        off = np.array([_logit(r["pMarket"]) for r in rows])
        w = fit_offset_logistic((x - x.mean(0)) / (x.std(0) + 1e-9), y, off)
        # Per standard deviation of the player1-minus-player2 difference.
        report["weights"] = [
            {"feature": f, "label": spec["labels"][f], "weight": round(float(v), 3)}
            for f, v in sorted(zip(spec["features"], w), key=lambda kv: -abs(kv[1]))
        ]
    os.makedirs(LAB_DIR, exist_ok=True)
    with open(os.path.join(LAB_DIR, spec["file"]), "w") as f:
        json.dump(report, f, indent=2)
    return report


def get_lab_report(key: str = "set1") -> Optional[Dict[str, Any]]:
    try:
        with open(os.path.join(LAB_DIR, LABS[key]["file"])) as f:
            return json.load(f)
    except Exception:
        return None


def get_all_lab_reports() -> Dict[str, Optional[Dict[str, Any]]]:
    return {key: get_lab_report(key) for key in LABS}
