"""Football Over/Under 2.5 laboratory: does our Poisson model add anything to the price?

Same method and bar as the tennis labs, kept apart from them (it does not touch
`set1_lab_service.LABS`): the base is the bookmaker's own probability of Over 2.5
(no margin), the model may only MOVE that price, with one parameter fitted
walk-forward on strictly earlier days:

    logit(p) = logit(p_market) + w * (logit(p_model) - logit(p_market))

Rows are finished La Liga / Premier League matches that have BOTH a pre-match
price we collected (`odds_markets.overUnder["2.5"]`, never overwritten once the
match starts) AND an Over/Under prediction created before kick-off. There is no
price history before 2026-11-23, so the sample only grows from there.

The specification is frozen on FROZEN_AT, written before looking at any result.
Verdict rule as in tennis: MIN_POST_FREEZE matches after the freeze and a
confidence interval of the log-loss improvement that excludes zero.
Reports only: nothing here changes a prediction.
"""
import json
import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
from sqlalchemy.orm import Session

from src.application import set1_lab_service as lab
from src.domain.models import Match, MatchScore, Prediction, Sport
from src.timezone import to_bogota

MARKET = "Over/Under 2.5 Goals"
FROZEN_AT = "2026-11-23"
FEATURES = ("model",)
LABELS = {"model": "Distancia del modelo de Poisson a la cuota"}
MIN_TRAIN_ROWS = 60      # equals set1_lab_service.MIN_TRAIN_ROWS, which walk_forward uses
MIN_POST_FREEZE = 300
FILE = "football_ou25_lab.json"


def fair_over(over: Any, under: Any) -> Optional[float]:
    """The book's probability of Over, with its margin taken out."""
    try:
        o, u = float(over), float(under)
    except (TypeError, ValueError):
        return None
    if o <= 1 or u <= 1:
        return None
    return (1 / o) / (1 / o + 1 / u)


def build_rows(db: Session) -> List[Dict[str, Any]]:
    sport = db.query(Sport).filter(Sport.code == "football").first()
    if not sport:
        return []
    matches = (db.query(Match).filter(Match.sport_id == sport.id, Match.status == "FINISHED",
                                      Match.external_id.like("FOOTBALL-AF-%")).order_by(Match.match_date).all())
    rows: List[Dict[str, Any]] = []
    for m in matches:
        if not m.league or m.league.name not in ("La Liga", "Premier League"):
            continue                    # the lab was frozen for the two domestic leagues; cups stay out of it
        ou = (((m.extra_data or {}).get("odds_markets") or {}).get("overUnder") or {}).get("2.5") or {}
        p_market = fair_over(ou.get("over"), ou.get("under"))
        if p_market is None or not m.match_date:
            continue
        score = (db.query(MatchScore).filter(MatchScore.match_id == m.id, MatchScore.period == "FULL_TIME").first())
        if not score or score.home_score is None or score.away_score is None:
            continue
        pred = (db.query(Prediction).filter(Prediction.match_id == m.id, Prediction.market == MARKET,
                                            Prediction.created_at < m.match_date)
                .order_by(Prediction.created_at.desc()).first())
        p_model = ((pred.probabilities or {}).get("over") if pred is not None else None)
        if p_model is None:
            continue
        p_model = float(p_model)
        rows.append({
            "date": to_bogota(m.match_date).strftime("%Y-%m-%d"),
            "x": [lab._logit(p_model) - lab._logit(p_market)],
            "won": 1 if score.home_score + score.away_score >= 3 else 0,
            "pMarket": p_market, "pModel": p_model,
            "odds1": float(ou["over"]), "odds2": float(ou["under"]),
        })
    rows.sort(key=lambda r: r["date"])
    return rows


def market_check(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Is the price itself calibrated on our sample, and how often does the model say Over?"""
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
        "version": 1, "trained_at": datetime.now(timezone.utc).isoformat(), "market": "Más/Menos 2.5 goles",
        "frozenAt": FROZEN_AT, "rows": len(rows), "marketCheck": market_check(rows),
        "allWalkForward": lab.score(rows, preds),
        "postFreeze": lab.score([r for r, _ in post], [p for _, p in post]), "weights": None,
    }
    n = report["postFreeze"].get("matches", 0)
    if n < MIN_POST_FREEZE:
        report["verdict"] = {"level": "juntando_muestra", "matches": n, "needed": MIN_POST_FREEZE}
    else:
        v = lab.verdict_for({**report["postFreeze"]})
        report["verdict"] = {**v, "needed": MIN_POST_FREEZE}
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
