"""Every bettable side of every tennis match still to play, ranked.

For Match Winner and Set 1 Winner, each player's side gets:
  * the fair probability: the reference bookmaker's price without its margin,
  * the best price across the bookmakers collected, and where,
  * the edge at that price (fair probability x best price - 1),
  * two second opinions: the engine's probability and the serve/return point
    model's.

Neither model has beaten the price in testing (see AGENTS.md, 2026-10-13), so
the ranking is by price value, and the models ride along as information.

A best price far above the reference one is flagged: on finished matches,
bets whose promised edge exceeded 5% lost money, which points to stale or
wrong quotes rather than value.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from src.application import point_model_service as point_model
from src.domain.models import Match, MatchCompetitor, Prediction, Sport
from src.timezone import to_bogota

GOOD_EDGE = 0.02      # green from here
STALE_GAP = 0.06      # best price this far above the reference: confirm before betting
MARKETS = (("matchWinner", "Match Winner"), ("set1Winner", "Set 1 Winner"))
SLAMS = ("australian open", "roland garros", "french open", "wimbledon", "us open")


def level_for(edge: float, price_gap: float) -> str:
    if edge < 0:
        return "poor"
    if price_gap > STALE_GAP:
        return "check"
    return "good" if edge >= GOOD_EDGE else "fair"


def price_view(reference: Dict[str, Any], books: Dict[str, Dict[str, Any]], side: str) -> Optional[Dict[str, Any]]:
    """Fair probability, best price and edge for one side of a two-way market."""
    try:
        ref1, ref2 = float(reference["p1"]), float(reference["p2"])
    except (KeyError, TypeError, ValueError):
        return None
    if ref1 <= 1.0 or ref2 <= 1.0:
        return None
    prices = sorted(
        ((float(v[side]), book) for book, v in (books or {}).items() if isinstance(v, dict) and v.get(side)),
        reverse=True,
    )
    ref = ref1 if side == "p1" else ref2
    best, book = prices[0] if prices else (ref, None)
    fair = (1.0 / ref) / (1.0 / ref1 + 1.0 / ref2)
    edge = fair * best - 1.0
    gap = best / ref - 1.0
    b = best - 1.0
    return {
        "fairProbability": round(fair, 4),
        "referenceOdds": ref,
        "bestOdds": best,
        "bestBook": book,
        "secondBestOdds": prices[1][0] if len(prices) > 1 else None,
        "books": len(prices),
        "edge": round(edge, 4),
        "priceGap": round(gap, 4),
        "kelly": round(max(0.0, (b * fair - (1.0 - fair)) / b), 4) if b > 0 else 0.0,
        "level": level_for(edge, gap),
    }


def list_best_bets(db: Session) -> Dict[str, Any]:
    tennis = db.query(Sport).filter(Sport.code == "tennis").first()
    if not tennis:
        return {"bets": [], "matches": 0}
    now = datetime.now(timezone.utc)
    matches = (
        db.query(Match)
        .options(joinedload(Match.competitors).joinedload(MatchCompetitor.competitor), joinedload(Match.league))
        .filter(Match.sport_id == tennis.id, Match.status == "SCHEDULED", Match.match_date > now)
        .order_by(Match.match_date.asc())
        .all()
    )
    if not matches:
        return {"bets": [], "matches": 0}
    points = point_model.upcoming_set_probabilities(db)
    predictions: Dict[Any, Dict[str, Prediction]] = {}
    for p in db.query(Prediction).filter(Prediction.match_id.in_([m.id for m in matches])).all():
        predictions.setdefault(p.match_id, {})[p.market] = p

    bets: List[Dict[str, Any]] = []
    with_odds = set()
    for m in matches:
        names = {
            ("p1" if mc.side in ("home", "player1") else "p2"): (mc.competitor.name if mc.competitor else None)
            for mc in m.competitors
        }
        if not names.get("p1") or not names.get("p2"):
            continue
        extra = m.extra_data or {}
        all_books = (extra.get("odds_lines") or {}).get("books") or {}
        league = m.league.name if m.league else None
        best_of = 5 if any(k in (league or "").lower() for k in SLAMS) else 3
        view = points.get(m.external_id)
        when = to_bogota(m.match_date)
        for key, market in MARKETS:
            reference = (extra.get("odds_markets") or {}).get(key)
            if not reference:
                continue
            pred = predictions.get(m.id, {}).get(market)
            for side in ("p1", "p2"):
                price = price_view(reference, all_books.get(key) or {}, side)
                if not price:
                    continue
                with_odds.add(m.id)
                engine = None
                if pred and pred.probabilities:
                    engine = pred.probabilities.get("player1" if side == "p1" else "player2")
                point = trust = None
                if view:
                    s = view["set"] if side == "p1" else 1.0 - view["set"]
                    point = point_model.match_prob(s, best_of) if key == "matchWinner" else s
                    trust = view["trust"]
                bets.append({
                    "matchId": m.external_id,
                    "date": when.strftime("%Y-%m-%d"),
                    "time": when.strftime("%H:%M"),
                    "tournament": league,
                    "home": names["p1"],
                    "away": names["p2"],
                    "market": market,
                    "pick": names[side],
                    "predictionId": str(pred.id) if pred and pred.predicted_outcome == names[side] else None,
                    "engineProbability": round(float(engine), 4) if engine is not None else None,
                    "pointProbability": round(point, 4) if point is not None else None,
                    "pointTrust": round(trust, 2) if trust is not None else None,
                    **price,
                })
    # Believable prices first, then best edge.
    bets.sort(key=lambda b: (b["level"] == "check", -b["edge"], -b["fairProbability"]))
    return {"bets": bets, "matches": len(with_odds), "goodEdge": GOOD_EDGE, "staleGap": STALE_GAP}
