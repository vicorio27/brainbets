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
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from src.application import point_model_service as point_model
from src.application.streak_service import streaks_for_matches
from src.domain.models import Match, MatchCompetitor, MatchScore, Prediction, Sport
from src.timezone import to_bogota

GOOD_EDGE = 0.02      # green from here
STALE_GAP = 0.06      # best price this far above the reference: confirm before betting
MARKETS = (("matchWinner", "Match Winner"), ("set1Winner", "Set 1 Winner"))
SLAMS = ("australian open", "roland garros", "french open", "wimbledon", "us open")
# Fair-probability bands for "how did bets like this one do", favourites only.
BANDS = ((0.50, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 0.90), (0.90, 1.01))
HISTORY_TTL = 3600
_history_cache: Dict[str, Any] = {"at": None, "data": None}


def band_of(fair: float) -> Optional[str]:
    for lo, hi in BANDS:
        if lo <= fair < hi:
            return f"{int(lo * 100)}-{int(min(hi, 1.0) * 100)}"
    return None


def band_summary(outcomes: List[Any]) -> Dict[str, Any]:
    """outcomes: (won, price, fair). Hit rate vs the fair one, and flat-stake yield with its 95% CI."""
    n = len(outcomes)
    profits = [(price - 1.0) if won else -1.0 for won, price, _ in outcomes]
    mean = sum(profits) / n
    sd = math.sqrt(sum((p - mean) ** 2 for p in profits) / max(1, n - 1))
    half = 1.96 * sd / math.sqrt(n)
    return {
        "n": n,
        "winRate": round(sum(1 for o in outcomes if o[0]) / n, 4),
        "expected": round(sum(o[2] for o in outcomes) / n, 4),
        "yield": round(mean, 4),
        "yieldLow": round(mean - half, 4),
        "yieldHigh": round(mean + half, 4),
    }


def _first_set_p1(sets: List[Any]) -> Optional[bool]:
    if not sets:
        return None
    s0 = sets[0]
    try:
        a, b = (s0.get("p1"), s0.get("p2")) if isinstance(s0, dict) else (s0[0], s0[1])
        a, b = float(a), float(b)
    except (TypeError, ValueError, KeyError, IndexError, AttributeError):
        return None
    return None if a == b else a > b


def band_history(db: Session) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """How favourites did at the reference price, by market and fair-probability band.

    Finished matches with a price taken before the start: the live collect's
    odds_markets when it was collected pre-start, otherwise the provider's
    historical snapshot (odds_markets_backfill). One price per match.
    """
    at = _history_cache["at"]
    if at and (datetime.now(timezone.utc) - at).total_seconds() < HISTORY_TTL:
        return _history_cache["data"]
    tennis = db.query(Sport).filter(Sport.code == "tennis").first()
    if not tennis:
        return {}
    rows = (
        db.query(Match.id, Match.extra_data, Match.created_at, Match.match_date)
        .filter(
            Match.sport_id == tennis.id,
            Match.status == "FINISHED",
            or_(Match.extra_data.op("?")("odds_markets"), Match.extra_data.op("?")("odds_markets_backfill")),
        )
        .all()
    )
    scores = {
        s.match_id: s
        for s in db.query(MatchScore).filter(
            MatchScore.match_id.in_([r.id for r in rows]), MatchScore.period == "FULL_TIME"
        )
    } if rows else {}
    buckets: Dict[str, Dict[str, List[Any]]] = {}
    for r in rows:
        sc = scores.get(r.id)
        if not sc or sc.home_score is None or sc.away_score is None or sc.home_score == sc.away_score:
            continue
        extra = r.extra_data or {}
        prices = extra.get("odds_markets") if r.created_at and r.created_at < r.match_date else None
        prices = prices or extra.get("odds_markets_backfill") or {}
        p1_match = sc.home_score > sc.away_score
        p1_set1 = _first_set_p1((extra.get("score_stats") or {}).get("sets") or [])
        if p1_set1 is None and min(sc.home_score, sc.away_score) == 0:
            p1_set1 = p1_match
        for key, market in MARKETS:
            p1_won = p1_match if key == "matchWinner" else p1_set1
            ref = prices.get(key)
            if p1_won is None or not isinstance(ref, dict):
                continue
            try:
                r1, r2 = float(ref["p1"]), float(ref["p2"])
            except (KeyError, TypeError, ValueError):
                continue
            if r1 <= 1.0 or r2 <= 1.0:
                continue
            for price, won in ((r1, p1_won), (r2, not p1_won)):
                fair = (1.0 / price) / (1.0 / r1 + 1.0 / r2)
                band = band_of(fair)
                if band:
                    buckets.setdefault(market, {}).setdefault(band, []).append((won, price, fair))
    data = {market: {band: band_summary(xs) for band, xs in bands.items()} for market, bands in buckets.items()}
    _history_cache.update(at=datetime.now(timezone.utc), data=data)
    return data


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
    history = band_history(db)
    streaks = streaks_for_matches(db, matches)
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
                    "pickStreak": (streaks.get(m.id) or {}).get(side),
                    "opponentStreak": (streaks.get(m.id) or {}).get("p2" if side == "p1" else "p1"),
                    "band": band_of(price["fairProbability"]),
                    "bandHistory": (history.get(market) or {}).get(band_of(price["fairProbability"]) or ""),
                    **price,
                })
    # Believable prices first, then best edge.
    bets.sort(key=lambda b: (b["level"] == "check", -b["edge"], -b["fairProbability"]))
    return {"bets": bets, "matches": len(with_odds), "goodEdge": GOOD_EDGE, "staleGap": STALE_GAP, "bandHistory": history}
