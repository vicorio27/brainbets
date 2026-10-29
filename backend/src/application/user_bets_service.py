"""The user's own bets, registered from the combo calculator and settled on results.

A bet is one leg (a single) or several (a combo), each one of the "Lo más
probable" picks (likely_picks_service) with the price the user took. Legs are
settled from the match's final set score, like the predictions' validation:
  * partido: the side wins the match; set1: the side wins the first set;
  * unSet: the side wins at least one set; sinCeder: the side wins without
    dropping one; sets: "corridos" (someone wins in straight sets) or "largo".
A cancelled match (retirement, walkover) voids its leg, priced 1.0, which is
how bookmakers usually settle it. A combo is lost as soon as one leg is lost
and won when every leg is won or void.
"""
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session, joinedload

from src.domain.models import Match, MatchScore, UserBet, UserBetLeg

KINDS = {"partido", "set1", "unSet", "sinCeder", "sets"}
MAX_LEGS = 10


class BetError(ValueError):
    """A bet that cannot be registered; the message is shown to the user."""


def valid_selector(kind: str, selector: Any) -> bool:
    if not isinstance(selector, dict):
        return False
    if kind == "sets":
        return selector.get("sets") in ("corridos", "largo")
    return kind in KINDS and selector.get("side") in ("p1", "p2")


def settle_leg(kind: str, selector: Dict[str, str], status: Optional[str], home: Optional[int],
               away: Optional[int], first_set_p1: Optional[bool]) -> Optional[str]:
    """WON / LOST / VOID, or None while it cannot be decided yet."""
    if status == "CANCELLED":
        return "VOID"
    if status != "FINISHED" or home is None or away is None or home == away:
        return None
    side = selector.get("side")
    mine, theirs = (home, away) if side == "p1" else (away, home)
    if kind == "partido":
        won = mine > theirs
    elif kind == "unSet":
        won = mine >= 1
    elif kind == "sinCeder":
        won = mine > theirs and theirs == 0
    elif kind == "sets":
        straight = min(home, away) == 0
        won = straight if selector.get("sets") == "corridos" else not straight
    elif kind == "set1":
        if first_set_p1 is None and min(home, away) == 0:
            first_set_p1 = home > away  # a straight-sets winner took the first set too
        if first_set_p1 is None:
            return None
        won = first_set_p1 == (side == "p1")
    else:
        return None
    return "WON" if won else "LOST"


def settle_live_leg(kind: str, selector: Dict[str, str], live_home: Optional[int],
                    live_away: Optional[int]) -> Optional[str]:
    """Settle a leg mid-match only when no later set can change it, from the sets won so far.

    At least one set is won once the side has a set; winning without dropping a
    set is lost once the side drops one; straight sets is decided once both have
    a set; the first set is known while exactly one set has been played.
    """
    if live_home is None or live_away is None:
        return None
    side = selector.get("side")
    mine, theirs = (live_home, live_away) if side == "p1" else (live_away, live_home)
    if kind == "unSet" and mine >= 1:
        return "WON"
    if kind == "sinCeder" and theirs >= 1:
        return "LOST"
    if kind == "sets" and min(live_home, live_away) >= 1:
        return "LOST" if selector.get("sets") == "corridos" else "WON"
    if kind == "set1" and live_home + live_away == 1:
        return "WON" if mine == 1 else "LOST"
    return None


def bet_outcome(legs: List[Tuple[Optional[str], float]]) -> Tuple[str, Optional[float]]:
    """(status, price paid) of a bet from its legs' (status, price)."""
    statuses = [s for s, _ in legs]
    if "LOST" in statuses:
        return "LOST", 0.0
    if any(s in (None, "PENDING") for s in statuses):
        return "PENDING", None
    if all(s == "VOID" for s in statuses):
        return "VOID", 1.0
    return "WON", math.prod(o for s, o in legs if s == "WON")  # unrounded: 1.16 x 1.07 pays 1.2412, not 1.241


def profit_of(status: str, amount: float, payout_odds: Optional[float]) -> Optional[float]:
    if status == "WON":
        return round(amount * (payout_odds - 1), 2)
    if status == "LOST":
        return -round(amount, 2)
    if status == "VOID":
        return 0.0
    return None


def summarize(bets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """How the user's bets went: hit rate against the bookmaker's own odds of them, and money."""
    settled = [b for b in bets if b["status"] in ("WON", "LOST")]
    staked = sum(b["amount"] for b in settled)
    profit = sum(b["profit"] for b in settled)
    probs = [b["probability"] for b in settled if b["probability"] is not None]
    return {
        "bets": len(bets),
        "pending": sum(1 for b in bets if b["status"] == "PENDING"),
        "won": sum(1 for b in settled if b["status"] == "WON"),
        "lost": sum(1 for b in settled if b["status"] == "LOST"),
        "void": sum(1 for b in bets if b["status"] == "VOID"),
        "staked": round(staked, 2),
        "profit": round(profit, 2),
        "yield": round(profit / staked, 4) if staked else None,
        "winRate": round(sum(1 for b in settled if b["status"] == "WON") / len(settled), 4) if settled else None,
        "expectedWinRate": round(sum(probs) / len(probs), 4) if probs else None,
        "pendingStaked": round(sum(b["amount"] for b in bets if b["status"] == "PENDING"), 2),
    }


# --- database side -------------------------------------------------------

def _first_set_p1(match: Match) -> Optional[bool]:
    rows = ((match.extra_data or {}).get("score_stats") or {}).get("sets") or []
    try:
        a, b = int(rows[0].get("p1")), int(rows[0].get("p2"))
    except (IndexError, AttributeError, TypeError, ValueError):
        return None
    return None if a == b else a > b


def create_bet(db: Session, payload: Dict[str, Any]) -> UserBet:
    try:
        amount = float(payload.get("amount"))
    except (TypeError, ValueError):
        raise BetError("El monto no es un número.")
    if amount <= 0:
        raise BetError("El monto tiene que ser mayor que cero.")
    legs_in = payload.get("legs") or []
    if not 1 <= len(legs_in) <= MAX_LEGS:
        raise BetError(f"Una apuesta lleva entre 1 y {MAX_LEGS} selecciones.")
    externals = [str(l.get("matchId") or "") for l in legs_in]
    if len(set(externals)) != len(externals):
        raise BetError("Hay dos selecciones del mismo partido: dependen una de la otra.")
    matches = {m.external_id: m for m in db.query(Match).filter(Match.external_id.in_(externals)).all()}
    now = datetime.now(timezone.utc)
    legs: List[UserBetLeg] = []
    for i, raw in enumerate(legs_in):
        m = matches.get(str(raw.get("matchId")))
        if not m:
            raise BetError("No encuentro uno de los partidos.")
        if m.status != "SCHEDULED" or (m.match_date and m.match_date <= now):
            raise BetError(f"«{raw.get('label')}»: el partido ya empezó, no se puede registrar.")
        kind, selector = raw.get("kind"), raw.get("selector")
        if not valid_selector(kind, selector):
            raise BetError(f"«{raw.get('label')}» no es una apuesta que se pueda liquidar.")
        try:
            odds = float(raw.get("odds"))
        except (TypeError, ValueError):
            raise BetError(f"«{raw.get('label')}»: la cuota no es un número.")
        if odds <= 1:
            raise BetError(f"«{raw.get('label')}»: la cuota tiene que ser mayor que 1.")
        prob = raw.get("probability")
        legs.append(UserBetLeg(
            position=i, match_id=m.id, kind=kind, selector=dict(selector), label=str(raw.get("label"))[:200],
            probability=float(prob) if prob is not None else None, odds=odds,
            best_odds=float(raw["bestOdds"]) if raw.get("bestOdds") else None,
        ))
    probs = [float(l.probability) for l in legs if l.probability is not None]
    bet = UserBet(
        amount=amount,
        odds=round(math.prod(float(l.odds) for l in legs), 3),
        probability=round(math.prod(probs), 4) if len(probs) == len(legs) else None,
        legs=legs,
    )
    db.add(bet)
    db.commit()
    db.refresh(bet)
    return bet


def settle_pending(db: Session) -> Dict[str, int]:
    """Settle every pending leg whose match has a result, then the bets they belong to."""
    bets = (
        db.query(UserBet)
        .options(joinedload(UserBet.legs).joinedload(UserBetLeg.match))
        .filter(UserBet.status == "PENDING")
        .all()
    )
    if not bets:
        return {"settled": 0, "pending": 0}
    match_ids = {l.match_id for b in bets for l in b.legs}
    scores = {
        s.match_id: s
        for s in db.query(MatchScore).filter(MatchScore.match_id.in_(match_ids), MatchScore.period == "FULL_TIME")
    }
    # Sets won so far in matches being played: the latest live snapshot.
    live_ids = [mid for mid in match_ids if mid not in scores]
    live: Dict[Any, Tuple[int, int]] = {}
    if live_ids:
        from src.domain.models import PredictionProgress
        for p in (db.query(PredictionProgress)
                  .filter(PredictionProgress.match_id.in_(live_ids))
                  .order_by(PredictionProgress.snapshot_at.asc())):
            live[p.match_id] = (p.home_score, p.away_score)
    now = datetime.now(timezone.utc)
    settled = 0
    for bet in bets:
        for leg in bet.legs:
            if leg.status != "PENDING":
                continue
            sc = scores.get(leg.match_id)
            result = settle_leg(leg.kind, leg.selector or {}, leg.match.status,
                                sc.home_score if sc else None, sc.away_score if sc else None,
                                _first_set_p1(leg.match))
            # A live snapshot means it started: the tennis live update writes the
            # score but can leave the match status at SCHEDULED until it ends.
            if result is None and leg.match.status in ("LIVE", "SCHEDULED") and leg.match_id in live:
                result = settle_live_leg(leg.kind, leg.selector or {}, *live[leg.match_id])
            if result:
                leg.status, leg.settled_at = result, now
        status, paid = bet_outcome([(l.status, float(l.odds)) for l in bet.legs])
        if status != "PENDING":
            bet.status, bet.payout_odds, bet.settled_at = status, paid, now
            bet.profit = profit_of(status, float(bet.amount), paid)
            settled += 1
    db.commit()
    return {"settled": settled, "pending": len(bets) - settled}


def _bet_view(bet: UserBet) -> Dict[str, Any]:
    return {
        "id": str(bet.id),
        "createdAt": bet.created_at.isoformat() if bet.created_at else None,
        "amount": float(bet.amount),
        "odds": float(bet.odds),
        "probability": float(bet.probability) if bet.probability is not None else None,
        "status": bet.status,
        "payoutOdds": float(bet.payout_odds) if bet.payout_odds is not None else None,
        "profit": float(bet.profit) if bet.profit is not None else None,
        "settledAt": bet.settled_at.isoformat() if bet.settled_at else None,
        "type": "sola" if len(bet.legs) == 1 else "combinada",
        "legs": [{
            "label": l.label,
            "kind": l.kind,
            "odds": float(l.odds),
            "bestOdds": float(l.best_odds) if l.best_odds is not None else None,
            "probability": float(l.probability) if l.probability is not None else None,
            "status": l.status,
            "matchId": l.match.external_id if l.match else None,
            "match": " vs ".join(mc.competitor.name for mc in sorted(l.match.competitors, key=lambda c: c.side)
                                 if mc.competitor) if l.match else None,
            "matchDate": l.match.match_date.isoformat() if l.match and l.match.match_date else None,
        } for l in bet.legs],
    }


def list_bets(db: Session) -> Dict[str, Any]:
    from src.domain.models import MatchCompetitor
    settle_pending(db)
    bets = (
        db.query(UserBet)
        .options(joinedload(UserBet.legs).joinedload(UserBetLeg.match)
                 .joinedload(Match.competitors).joinedload(MatchCompetitor.competitor))
        .order_by(UserBet.created_at.desc())
        .all()
    )
    views = [_bet_view(b) for b in bets]
    return {
        "bets": views,
        "summary": {
            "all": summarize(views),
            "sola": summarize([v for v in views if v["type"] == "sola"]),
            "combinada": summarize([v for v in views if v["type"] == "combinada"]),
        },
    }


def delete_bet(db: Session, bet_id: str) -> bool:
    """Removes a bet registered by mistake; only while it is pending."""
    bet = db.query(UserBet).filter(UserBet.id == bet_id).first()
    if not bet:
        return False
    if bet.status != "PENDING":
        raise BetError("Solo se puede borrar una apuesta pendiente.")
    db.delete(bet)
    db.commit()
    return True
