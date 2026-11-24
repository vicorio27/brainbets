"""Football total-corners laboratory: does a corners model add anything to the price?

Same method and bar as the Over/Under 2.5 lab (`football_lab_service`) and kept apart
from the tennis labs. The base is the bookmaker's probability of Over on its most
balanced corners line (no margin, `extra_data['odds_extra']['corners']`, the first
price we saw, never overwritten); the model may only MOVE it:

    logit(p) = logit(p_market) + w * (logit(p_model) - logit(p_market))

The model is the one measured on past data (negative binomial on total corners):
corners for/against per team against the league mean, window WINDOW matches,
exponential decay DECAY and shrinkage K to the league mean, dispersion R. Each
prediction uses ONLY matches before it (one chronological pass), so it is what we
could have said before kick-off. The constants come from the 2026-11-23 evaluation
on 4,280 past matches and are FROZEN on FROZEN_AT; if they change, move the date.

Rows: finished La Liga / Premier League matches with a stored corners price and
match statistics. No price history exists before 2026-11-24, so the sample grows
from there (~10-20 matches a week); the verdict needs MIN_POST_FREEZE matches after
the freeze and an improvement interval that excludes zero. Reports only.
"""
import json
import math
import os
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.stats import nbinom
from sqlalchemy.orm import Session

from src.application import set1_lab_service as lab
from src.domain.models import Match
from src.timezone import to_bogota

FROZEN_AT = "2026-11-24"
LEAGUES = ("La Liga", "Premier League")
WINDOW, DECAY, K, R = 60, 0.99, 40.0, 40.8     # frozen from the 2026-11-23 evaluation
MIN_TEAM_MATCHES = 3
MIN_LEAGUE_MATCHES = 50
FEATURES = ("model",)
LABELS = {"model": "Distancia del modelo de córners a la cuota"}
MIN_TRAIN_ROWS = 60
MIN_POST_FREEZE = 300
FILE = "football_corners_lab.json"


def fair_over(over: Any, under: Any) -> Optional[float]:
    try:
        o, u = float(over), float(under)
    except (TypeError, ValueError):
        return None
    if o <= 1 or u <= 1:
        return None
    return (1 / o) / (1 / o + 1 / u)


def main_line(lines: Dict[str, Any]) -> Optional[Tuple[float, float, float, float]]:
    """The most balanced x.5 line: (line, over odds, under odds, fair over)."""
    best = None
    for key, px in (lines or {}).items():
        try:
            line = float(key)
        except (TypeError, ValueError):
            continue
        if abs(line - math.floor(line) - 0.5) > 1e-9:
            continue
        p = fair_over((px or {}).get("over"), (px or {}).get("under"))
        if p is None:
            continue
        cand = (abs(p - 0.5), line, float(px["over"]), float(px["under"]), p)
        if best is None or cand < best:
            best = cand
    return None if best is None else best[1:]


def corners_split(hist_h, hist_a, lg_h: float, lg_a: float) -> Optional[Tuple[float, float]]:
    """Expected corners (home, away) from both teams' recent (for, against) pairs, newest last."""
    m = (lg_h + lg_a) / 2

    def rating(hist):
        num_f = num_a = den = 0.0
        n = 0
        for age, (f, a) in enumerate(reversed(hist)):
            w = DECAY ** age
            num_f += w * f
            num_a += w * a
            den += w
            n += 1
        if n < MIN_TEAM_MATCHES:
            return None
        return (num_f + K * m) / (den + K), (num_a + K * m) / (den + K)

    rh, ra = rating(hist_h), rating(hist_a)
    if rh is None or ra is None:
        return None
    return lg_h * (rh[0] / m) * (ra[1] / m), lg_a * (ra[0] / m) * (rh[1] / m)


def expected_corners(hist_h, hist_a, lg_h: float, lg_a: float) -> Optional[float]:
    """Expected total corners of a match."""
    split = corners_split(hist_h, hist_a, lg_h, lg_a)
    return None if split is None else split[0] + split[1]


def p_over(mean: float, line: float) -> float:
    return float(nbinom.sf(int(line), R, R / (R + mean)))


def _corners(stats: Dict[str, Any]) -> Optional[float]:
    v = (stats or {}).get("corner_kicks")
    return None if v is None else float(v)


def build_rows(db: Session) -> List[Dict[str, Any]]:
    q = (db.query(Match).filter(Match.extra_data["team_stats"].isnot(None), Match.status == "FINISHED")
         .order_by(Match.match_date))
    hist: Dict[str, deque] = defaultdict(lambda: deque(maxlen=WINDOW))
    lg_sum: Dict[str, List[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])    # home corners, away corners, matches
    rows: List[Dict[str, Any]] = []
    for m in q.yield_per(500):
        extra = m.extra_data or {}
        ts = extra.get("team_stats") or {}
        ch, ca = _corners(ts.get("home")), _corners(ts.get("away"))
        if ch is None or ca is None or not m.league or not m.match_date:
            continue
        sides = {mc.side: mc.competitor.name for mc in m.competitors}
        h, a = sides.get("home"), sides.get("away")
        if not h or not a:
            continue
        lg = m.league.name
        S = lg_sum[lg]
        if m.league.name in LEAGUES and S[2] >= MIN_LEAGUE_MATCHES:
            line = main_line(((extra.get("odds_extra") or {}).get("corners")))
            if line:
                mean = expected_corners(list(hist[h]), list(hist[a]), S[0] / S[2], S[1] / S[2])
                if mean is not None:
                    ln, o_over, o_under, p_mkt = line
                    p_mod = min(max(p_over(mean, ln), 1e-4), 1 - 1e-4)
                    rows.append({
                        "date": to_bogota(m.match_date).strftime("%Y-%m-%d"),
                        "x": [lab._logit(p_mod) - lab._logit(p_mkt)],
                        "won": 1 if ch + ca > ln else 0,
                        "pMarket": p_mkt, "pModel": p_mod, "line": ln, "expected": round(mean, 2),
                        "odds1": o_over, "odds2": o_under,
                    })
        S[0] += ch
        S[1] += ca
        S[2] += 1
        hist[h].append((ch, ca))
        hist[a].append((ca, ch))
    rows.sort(key=lambda r: r["date"])
    return rows


def market_check(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {"matches": 0}
    n = len(rows)
    return {"matches": n,
            "marketOver": round(sum(r["pMarket"] for r in rows) / n, 3),
            "modelOver": round(sum(r["pModel"] for r in rows) / n, 3),
            "actualOver": round(sum(r["won"] for r in rows) / n, 3)}


def build_report(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    preds = lab.walk_forward(rows)
    post = [(r, p) for r, p in zip(rows, preds) if r["date"] > FROZEN_AT]
    report: Dict[str, Any] = {
        "version": 1, "trained_at": datetime.now(timezone.utc).isoformat(), "market": "Córners totales",
        "frozenAt": FROZEN_AT, "rows": len(rows), "marketCheck": market_check(rows),
        "allWalkForward": lab.score(rows, preds),
        "postFreeze": lab.score([r for r, _ in post], [p for _, p in post]), "weights": None,
    }
    n = report["postFreeze"].get("matches", 0)
    if n < MIN_POST_FREEZE:
        report["verdict"] = {"level": "juntando_muestra", "matches": n, "needed": MIN_POST_FREEZE}
    else:
        report["verdict"] = {**lab.verdict_for({**report["postFreeze"]}), "needed": MIN_POST_FREEZE}
    if len(rows) >= MIN_TRAIN_ROWS:
        x = np.array([r["x"] for r in rows], dtype=float)
        y = np.array([r["won"] for r in rows], dtype=float)
        off = np.array([lab._logit(r["pMarket"]) for r in rows])
        w = lab.fit_offset_logistic((x - x.mean(0)) / (x.std(0) + 1e-9), y, off)
        report["weights"] = [{"feature": f, "label": LABELS[f], "weight": round(float(v), 3)}
                             for f, v in zip(FEATURES, w)]
    return report


def run_lab(db: Session) -> Dict[str, Any]:
    report = build_report(build_rows(db))
    os.makedirs(lab.LAB_DIR, exist_ok=True)
    with open(os.path.join(lab.LAB_DIR, FILE), "w") as f:
        json.dump(report, f, indent=2)
    return report


def get_report() -> Optional[Dict[str, Any]]:
    try:
        with open(os.path.join(lab.LAB_DIR, FILE)) as f:
            return json.load(f)
    except Exception:
        return None
