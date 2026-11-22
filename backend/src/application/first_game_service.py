"""First game of the first set: who served it and who won it.

api-tennis publishes the point by point of every finished match, but until
now we did not keep it. This stores, for each finished ATP match, just the
opening game of set 1 in `matches.extra_data['score_stats']['firstGame']`:

    {"server": "p1" | "p2", "winner": "p1" | "p2"}

with p1 / p2 being OUR match sides (player1 / home = p1), so it can be read
without caring how the feed ordered the players.

Used by the context items ("1er game") shown with each match to play.
"""
import logging
import os
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from sqlalchemy.orm import Session

from src.domain.models import Match, MatchCompetitor

logger = logging.getLogger(__name__)

MIN_SERVED = 10      # serving-first games needed before the item is shown
FEED_URL = "https://api.api-tennis.com/tennis/"


# ---------- pure parts ----------

def first_game(ev: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    """(server, winner) of game 1 of set 1, each 1 = first player, 2 = second."""
    for g in ev.get("pointbypoint") or []:
        if str(g.get("set_number")) in ("Set 1", "1") and str(g.get("number_game")) == "1":
            served, won = str(g.get("player_served") or ""), str(g.get("serve_winner") or "")
            if not served or not won:
                return None
            return (1 if "First" in served else 2, 1 if "First" in won else 2)
    return None


def _tokens(name: str) -> frozenset:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    return frozenset(t for t in re.split(r"[\s\-\.]+", s) if len(t) > 2)


def same_player(api_name: str, db_name: str) -> bool:
    """'C. Alcaraz' == 'Carlos Alcaraz' == 'Alcaraz C.'; 'A. Zverev' vs 'Zverev M.' is
    told apart by the initial when both names carry one."""
    a, b = _tokens(api_name), _tokens(db_name)
    if not a or not b or not (a <= b or b <= a):
        return False

    def initial(name: str) -> Optional[str]:
        parts = [p for p in re.split(r"[\s]+", unicodedata.normalize("NFKD", name or "")
                                     .encode("ascii", "ignore").decode().lower()) if p]
        short = [p.strip(".") for p in parts if len(p.strip(".")) == 1 or (len(p) == 2 and p.endswith("."))]
        if short:
            return short[0][0]
        return parts[0][0] if len(parts) > 1 else None

    ia, ib = initial(api_name), initial(db_name)
    return not (ia and ib and ia != ib)


def first_game_item(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """rows: {"served": bool (he served first), "won": bool (he won game 1),
    "date": datetime, "rival": str, "tournament": str}"""
    served = [r for r in rows if r["served"]]
    if len(served) < MIN_SERVED:
        return None
    held = [r for r in served if r["won"]]
    ret = [r for r in rows if not r["served"]]
    rwon = [r for r in ret if r["won"]]
    pct = round(100 * len(held) / len(served))
    text = f"Sacando primero defendió {len(held)} de {len(served)} ({pct}%)"
    short = f"{len(held)}/{len(served)} ({pct}%)"
    if ret:
        text += f"; restando primero ganó {len(rwon)} de {len(ret)} ({round(100 * len(rwon) / len(ret))}%)"
    lost = [r for r in served if not r["won"]]
    detail = "Perdió su primer game al sacar primero: " + (
        "; ".join(f"{r['date']:%Y-%m-%d} {r.get('tournament') or ''} vs {r.get('rival') or '?'}" for r in lost[-6:])
        if lost else "nunca") + f". {len(rows)} partidos con punto a punto."
    return {"key": "firstgame", "label": "1er game", "tone": "neutral",
            "short": short, "text": text, "detail": detail}


# ---------- storage ----------

def _sides(m: Match) -> Dict[str, MatchCompetitor]:
    return {("p1" if mc.side in ("player1", "home") else "p2"): mc for mc in m.competitors}


def _store(m: Match, server: str, winner: str) -> bool:
    ex = dict(m.extra_data or {})
    stats = dict(ex.get("score_stats") or {})
    new = {"server": server, "winner": winner}
    if stats.get("firstGame") == new:
        return False
    stats["firstGame"] = new
    ex["score_stats"] = stats
    m.extra_data = ex          # a NEW dict: SQLAlchemy does not see in-place JSON changes
    return True


def apply_events(db: Session, events: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    """Write the first game of every finished event we can pair with a match of ours."""
    evs = [e for e in events
           if e.get("event_status") == "Finished" and e.get("event_qualification") != "True"]
    out = {"events": len(evs), "stored": 0, "unmatched": 0, "nodata": 0}
    if not evs:
        return out
    days = [date.fromisoformat(e["event_date"]) for e in evs if e.get("event_date")]
    lo = datetime.combine(min(days) - timedelta(days=2), datetime.min.time(), tzinfo=timezone.utc)
    hi = datetime.combine(max(days) + timedelta(days=3), datetime.min.time(), tzinfo=timezone.utc)
    pool = (db.query(Match).filter(Match.external_id.like("TENNIS-%"),
                                   Match.match_date >= lo, Match.match_date < hi).all())
    by_key = {m.external_id: m for m in pool}
    for ev in evs:
        fg = first_game(ev)
        if not fg:
            out["nodata"] += 1
            continue
        p1, p2 = ev.get("event_first_player", ""), ev.get("event_second_player", "")
        m = by_key.get("TENNIS-%s" % ev.get("event_key"))
        if m is None:
            day = date.fromisoformat(ev["event_date"])
            for c in pool:
                if abs((c.match_date.date() - day).days) > 2:
                    continue
                s = _sides(c)
                if len(s) == 2 and (
                    (same_player(p1, s["p1"].competitor.name) and same_player(p2, s["p2"].competitor.name))
                    or (same_player(p1, s["p2"].competitor.name) and same_player(p2, s["p1"].competitor.name))):
                    m = c
                    break
        if m is None:
            out["unmatched"] += 1
            continue
        s = _sides(m)
        if len(s) != 2:
            out["unmatched"] += 1
            continue
        # which of OUR sides is the feed's first player?
        n1, n2 = s["p1"].competitor.name, s["p2"].competitor.name
        a1, a2 = same_player(p1, n1), same_player(p1, n2)
        if a1 and not a2:
            first_is_p1 = True
        elif a2 and not a1:
            first_is_p1 = False
        elif a1 and a2:
            first_is_p1 = same_player(p2, n2)
        else:
            out["unmatched"] += 1
            continue
        to_ours = {1: "p1", 2: "p2"} if first_is_p1 else {1: "p2", 2: "p1"}
        if _store(m, to_ours[fg[0]], to_ours[fg[1]]):
            out["stored"] += 1
    db.commit()
    return out


# ---------- feed ----------

def fetch(start: date, stop: date) -> List[Dict[str, Any]]:
    key = os.environ.get("TENNIS_API_KEY", "")
    if not key:
        logger.warning("[FIRSTGAME] TENNIS_API_KEY not configured")
        return []
    try:
        r = requests.get(FEED_URL, params={"APIkey": key, "method": "get_fixtures", "date_start": str(start),
                                           "date_stop": str(stop), "event_type_key": 265,
                                           "timezone": "America/Bogota"}, timeout=60)
        if r.status_code != 200:
            logger.warning("[FIRSTGAME] get_fixtures %s", r.status_code)
            return []
        return r.json().get("result") or []
    except Exception as e:
        logger.warning("[FIRSTGAME] get_fixtures failed: %s", type(e).__name__)
        return []


def refresh_recent(db: Session, days: int = 3) -> Dict[str, int]:
    """One call: the last `days` days of finished matches (runs with every validation)."""
    today = datetime.now(timezone(timedelta(hours=-5))).date()
    return apply_events(db, fetch(today - timedelta(days=days), today))


def backfill(db: Session, start: date, stop: date) -> Dict[str, int]:
    """Weekly calls over a range; safe to repeat."""
    total = {"events": 0, "stored": 0, "unmatched": 0, "nodata": 0, "calls": 0}
    d = start
    while d <= stop:
        e = min(d + timedelta(days=6), stop)
        res = apply_events(db, fetch(d, e))
        total["calls"] += 1
        for k in ("events", "stored", "unmatched", "nodata"):
            total[k] += res[k]
        d = e + timedelta(days=1)
    return total
