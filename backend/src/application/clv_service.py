"""Closing Line Value (CLV): capture odds right before kickoff and compare
them to the odds our prediction actually used.

Why this matters more than it sounds: beating the closing line is widely
considered the single best *early* signal of a real betting edge, because it
doesn't need the sample sizes win/loss does. A market's closing price has
already absorbed essentially all the information and money that was ever
going to move it, so if the odds we captured were consistently better than
where the market settled, we were right about something the market hadn't
priced in yet -- independent of whether any individual match went our way.
`bankroll_service`'s significance test needs ~30+ settled bets per market
before it can tell a real edge from noise; CLV is a real number on every
single bet with a captured closing price, not a win/loss coin flip, so it
needs far fewer of them to mean something.

Data flow:
  1. `capture_closing_odds()` runs on a schedule (an n8n node calling it
     roughly hourly, close to kickoff for matches starting soon) and stores a
     closing-odds snapshot per match in `matches.extra_data["odds_markets_closing"]`
     -- the same raw shape as the opening `odds_markets` snapshot already
     collected at fixture-ingestion time (`extract_odds_markets()` here is a
     straight port of the n8n `Extract Tennis Events` node's
     `extractOddsMarkets`/`pickOdd` helpers, so the two snapshots are
     comparable apples-to-apples).
  2. `closing_odds_for_prediction()` re-derives the per-market, per-selection
     closing price the same way `n8n/prediction_engine/tennis.py` derives the
     opening one, so a prediction's CLV can be computed without the caller
     needing to know market-specific odds-shape details.

A closing snapshot taken an hour before kickoff (this module's cadence) is
not the same as the true last-second closing line sharper trackers use --
it's accurate enough to be informative, not enough to be precise. The CLV
numbers should be read as a direction, not a decimal point.
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from src.domain.models import Match, Sport
from src.timezone import BOGOTA_TZ

logger = logging.getLogger(__name__)

# Same bookmaker preference order as n8n's `Extract Tennis Events` node
# (`BOOKIE_PRIORITY`) -- keep both in sync if either changes.
BOOKIE_PRIORITY = [
    "Pncl", "bet365", "Betfair", "WilliamHill", "Unibet", "Marathon",
    "1xBet", "10Bet", "Bwin", "bwin", "Betsson",
]


def _pick_odd(selection: Any) -> Optional[float]:
    if not isinstance(selection, dict):
        return None
    for bookie in BOOKIE_PRIORITY:
        if bookie in selection:
            try:
                v = float(selection[bookie])
            except (TypeError, ValueError):
                continue
            if v > 1.0:
                return v
    for raw in selection.values():
        try:
            v = float(raw)
        except (TypeError, ValueError):
            continue
        if v > 1.0:
            return v
    return None


def extract_odds_markets(markets: Any) -> Optional[Dict[str, Any]]:
    """Port of the n8n `extractOddsMarkets` JS helper -- same market keys,
    same bookmaker fallback, so an opening and a closing snapshot are
    directly comparable."""
    if not isinstance(markets, dict):
        return None
    out: Dict[str, Any] = {}

    ha = markets.get("Home/Away") or {}
    mp1, mp2 = _pick_odd(ha.get("Home")), _pick_odd(ha.get("Away"))
    if mp1 and mp2:
        out["matchWinner"] = {"p1": mp1, "p2": mp2}

    s1 = markets.get("Home/Away (1st Set)") or {}
    s1p1, s1p2 = _pick_odd(s1.get("Home")), _pick_odd(s1.get("Away"))
    if s1p1 and s1p2:
        out["set1Winner"] = {"p1": s1p1, "p2": s1p2}

    ns = markets.get("Number of sets") or {}
    ns_out = {}
    for k in ("2", "3", "4", "5"):
        v = _pick_odd(ns.get(k))
        if v:
            ns_out[k] = v
    if ns_out:
        out["numberOfSets"] = ns_out

    sb = markets.get("Set Betting") or {}
    sb_out = {}
    for k, v in sb.items():
        pv = _pick_odd(v)
        if pv:
            sb_out[k] = pv
    if sb_out:
        out["setBetting"] = sb_out

    return out or None


def _combine_odds(*decimals: Optional[float]) -> Optional[float]:
    """Fair combined decimal odd for "A or B", same as tennis.py's helper."""
    inv = sum(1.0 / float(o) for o in decimals if o and float(o) > 1.0)
    return round(1.0 / inv, 3) if inv > 0 else None


def closing_odds_for_prediction(
    closing_markets: Optional[Dict[str, Any]],
    market: Optional[str],
    predicted_outcome: Optional[str],
    home_name: Optional[str],
    away_name: Optional[str],
    reasoning_data: Optional[Dict[str, Any]],
) -> Optional[float]:
    """Re-derive the closing decimal odd for the exact selection a
    prediction picked, mirroring how `tennis.py` derived the opening one.

    `reasoning_data` supplies the per-prediction detail the market-level
    `closing_markets` snapshot alone can't: `bestOf` for Total Sets, and the
    exact `setBetting` key for Exact Set Score (both already stored at
    predict time), so this doesn't need to re-run tournament-name heuristics.
    """
    if not closing_markets or not market or not predicted_outcome:
        return None
    outcome = predicted_outcome.strip()
    reasoning_data = reasoning_data or {}

    if market in ("Match Winner", "Set 1 Winner"):
        key = "matchWinner" if market == "Match Winner" else "set1Winner"
        sides = closing_markets.get(key) or {}
        if home_name and outcome == home_name:
            return sides.get("p1")
        if away_name and outcome == away_name:
            return sides.get("p2")
        return None

    if market == "Total Sets":
        ns = closing_markets.get("numberOfSets") or {}
        best_of = reasoning_data.get("bestOf") or 3
        is_over = outcome.lower().startswith("over")
        if best_of >= 5:
            over_odd = _combine_odds(ns.get("4"), ns.get("5"))
            under_odd = ns.get("3")
        else:
            over_odd = ns.get("3")
            under_odd = ns.get("2")
        return over_odd if is_over else under_odd

    if market == "Exact Set Score":
        sb_key = (reasoning_data.get("oddsDecimal") or {}).get("key")
        if not sb_key:
            return None
        return (closing_markets.get("setBetting") or {}).get(sb_key)

    return None


def compute_clv(our_odds: Optional[float], closing_odds: Optional[float]) -> Optional[float]:
    """CLV as a fraction: positive means we got a better price than the
    closing line (e.g. 0.05 = our odds were 5% higher than closing)."""
    if not our_odds or not closing_odds or closing_odds <= 1.0:
        return None
    return round(our_odds / closing_odds - 1.0, 4)


def _fetch_odds_by_key(date_str: str) -> Dict[str, Any]:
    """Call api-tennis get_odds directly for one date (backend-side; the
    live n8n pipeline does the equivalent for "today" at collection time).
    Deliberately omits `event_type_key`: that parameter filters the odds
    feed down to a fraction of events (see the matching gotcha in AGENTS.md).
    """
    api_key = os.environ.get("TENNIS_API_KEY", "")
    if not api_key:
        logger.warning("[CLV] TENNIS_API_KEY not configured; skipping closing-odds fetch")
        return {}
    try:
        resp = requests.get(
            "https://api.api-tennis.com/tennis/",
            params={
                "APIkey": api_key,
                "method": "get_odds",
                "date_start": date_str,
                "date_stop": date_str,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            logger.warning(f"[CLV] get_odds returned {resp.status_code} for {date_str}: {resp.text[:200]}")
            return {}
        data = resp.json()
        result = data.get("result")
        return result if isinstance(result, dict) else {}
    except Exception as e:
        logger.warning(f"[CLV] get_odds request failed for {date_str}: {e}")
        return {}


def capture_closing_odds(db: Session, window_hours: int = 6) -> Dict[str, Any]:
    """Snapshot current odds for tennis matches starting soon.

    Meant to be called roughly hourly (an n8n node hitting the endpoint that
    wraps this). Each call overwrites the previous snapshot for a match, so
    the LAST snapshot captured before a match goes live is its de-facto
    closing line -- accurate to within one capture cycle, not to the second.
    """
    now = datetime.now(timezone.utc)
    tennis = db.query(Sport).filter(Sport.code == "tennis").first()
    if not tennis:
        return {"matches": 0, "updated": 0, "dates": []}

    matches = (
        db.query(Match)
        .filter(Match.sport_id == tennis.id)
        .filter(Match.status == "SCHEDULED")
        .filter(Match.match_date >= now - timedelta(hours=1))
        .filter(Match.match_date <= now + timedelta(hours=window_hours))
        .all()
    )
    if not matches:
        return {"matches": 0, "updated": 0, "dates": []}

    dates = sorted({m.match_date.astimezone(BOGOTA_TZ).date().isoformat() for m in matches})
    odds_by_key: Dict[str, Any] = {}
    for day in dates:
        odds_by_key.update(_fetch_odds_by_key(day))

    updated = 0
    for m in matches:
        event_key = (m.external_id or "").replace("TENNIS-", "")
        raw = odds_by_key.get(event_key)
        if not raw:
            continue
        parsed = extract_odds_markets(raw)
        if not parsed:
            continue
        existing = m.extra_data or {}
        m.extra_data = {**existing, "odds_markets_closing": parsed}
        updated += 1
    db.commit()

    return {"matches": len(matches), "updated": updated, "dates": dates}
