"""Football collection from API-Football (api-sports.io): La Liga and Premier League.

Self-contained, like the tennis closing-odds capture: it asks the provider for
the fixtures of yesterday / today / tomorrow, keeps the two leagues we follow,
prices the ones that have not started and hands everything to the same
`_insert_match` the rest of the collection uses.

The free plan allows 100 calls a day and ~10 a minute, and only serves a
3-day window for the current season, so every call is counted, paced and
capped (`DAILY_CAP`), and the work is split in two:
  * once a day (first run after 03:00 Bogota): fixtures of the window + the
    pre-match price of each fixture still to play (1 call each);
  * on every later run: today's fixtures only when a match is in progress or
    just ended (results), and the closing price of the matches about to start.

Prices: not measured against the bookmaker yet. This only stores them.
"""
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

import requests

from src.timezone import BOGOTA_TZ

BASE = "https://v3.football.api-sports.io"
LEAGUES = {39: "Premier League", 140: "La Liga"}
DAILY_CAP = 90                 # of the 100 the free plan allows
MIN_GAP = 6.5                  # seconds between calls (10 a minute)
CLOSING_MINUTES = 100          # price a match this close to its start as its "closing" price
BOOK_PRIORITY = ["Pinnacle", "Bet365", "Marathonbet", "1xBet", "BetVictor", "William Hill", "Betfair", "SBO"]
OU_LINES = ("1.5", "2.5", "3.5")

# API-Football name -> the name already stored from the historical files
ALIASES = {
    "Manchester City": "Man City", "Manchester United": "Man United", "Nottingham Forest": "Nott'm Forest",
    "Sheffield Utd": "Sheffield United", "Sheffield United": "Sheffield United", "Leeds": "Leeds",
    "Atletico Madrid": "Ath Madrid", "Athletic Club": "Ath Bilbao", "Athletic Bilbao": "Ath Bilbao",
    "Real Betis": "Betis", "Celta Vigo": "Celta", "Espanyol": "Espanol", "Rayo Vallecano": "Vallecano",
    "Real Sociedad": "Sociedad", "Real Valladolid": "Valladolid", "Real Oviedo": "Oviedo",
    "Alavés": "Alaves", "Deportivo Alaves": "Alaves", "Leganés": "Leganes", "Almería": "Almeria", "Cádiz": "Cadiz",
    "Wolverhampton Wanderers": "Wolves", "Tottenham Hotspur": "Tottenham", "West Ham United": "West Ham",
    "Newcastle United": "Newcastle", "Brighton & Hove Albion": "Brighton", "Leicester City": "Leicester",
    "Ipswich Town": "Ipswich", "Luton Town": "Luton", "AFC Bournemouth": "Bournemouth",
}

LIVE = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"}
DONE = {"FT", "AET", "PEN"}
CALLED_OFF = {"PST", "CANC", "ABD", "AWD", "WO", "SUSP"}


def team_name(name: str) -> str:
    return ALIASES.get(name, name)


def season_code(year: int) -> str:
    """API season 2026 (= 2026-27) -> '2627', the code the historical files use."""
    return f"{year % 100:02d}{(year + 1) % 100:02d}"


def status_of(short: str) -> str:
    s = (short or "").upper()
    if s in DONE:
        return "FINISHED"
    if s in LIVE:
        return "LIVE"
    if s in CALLED_OFF:
        return "CANCELLED"
    return "SCHEDULED"


# ---------- prices ----------

def _f(v: Any) -> Optional[float]:
    try:
        x = float(v)
        return x if x > 1 else None
    except (TypeError, ValueError):
        return None


def book_prices(odds_item: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """{book: {matchWinner: {home, draw, away}, btts: {yes, no}, overUnder: {line: {over, under}}}}."""
    out: Dict[str, Dict[str, Any]] = {}
    for bk in (odds_item or {}).get("bookmakers") or []:
        row: Dict[str, Any] = {}
        for bet in bk.get("bets") or []:
            name, vals = bet.get("name"), bet.get("values") or []
            if name == "Match Winner":
                m = {v.get("value", "").lower(): _f(v.get("odd")) for v in vals}
                if m.get("home") and m.get("draw") and m.get("away"):
                    row["matchWinner"] = {"home": m["home"], "draw": m["draw"], "away": m["away"]}
            elif name == "Both Teams Score":
                m = {v.get("value", "").lower(): _f(v.get("odd")) for v in vals}
                if m.get("yes") and m.get("no"):
                    row["btts"] = {"yes": m["yes"], "no": m["no"]}
            elif name == "Goals Over/Under":
                lines: Dict[str, Dict[str, float]] = {}
                for v in vals:
                    parts = str(v.get("value", "")).split()
                    if len(parts) == 2 and parts[1] in OU_LINES and parts[0] in ("Over", "Under"):
                        p = _f(v.get("odd"))
                        if p:
                            lines.setdefault(parts[1], {})["over" if parts[0] == "Over" else "under"] = p
                lines = {k: v for k, v in lines.items() if "over" in v and "under" in v}
                if lines:
                    row["overUnder"] = lines
        if row and bk.get("name"):
            out[bk["name"]] = row
    return out


def pick_markets(books: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """One reference price per market: the first book (in BOOK_PRIORITY) that has it.
    `books` keeps every book for the markets we care about (kept apart from the engine payload)."""
    if not books:
        return None
    order = [b for b in BOOK_PRIORITY if b in books] + [b for b in books if b not in BOOK_PRIORITY]
    out: Dict[str, Any] = {"source": "api-football"}
    for market in ("matchWinner", "btts", "overUnder"):
        for b in order:
            if market in books[b]:
                out[market] = books[b][market]
                out.setdefault("book", {})[market] = b
                break
    if len(out) <= 1:
        return None
    out["books"] = {
        "overUnder25": {b: books[b]["overUnder"]["2.5"] for b in order if "2.5" in (books[b].get("overUnder") or {})},
        "matchWinner": {b: books[b]["matchWinner"] for b in order if "matchWinner" in books[b]},
    }
    return out


# ---------- fixtures ----------

def to_raw(fx: Dict[str, Any], markets: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """The dict `_insert_match` expects, from one API-Football fixture."""
    try:
        league_id = fx["league"]["id"]
        if league_id not in LEAGUES:
            return None
        when = datetime.fromisoformat(fx["fixture"]["date"]).astimezone(BOGOTA_TZ)
        status = status_of(fx["fixture"]["status"]["short"])
        goals = fx.get("goals") or {}
        mw = (markets or {}).get("matchWinner") or {}
        raw = {
            "matchId": f"FOOTBALL-AF-{fx['fixture']['id']}",
            "eventId": str(fx["fixture"]["id"]),
            "homeTeam": team_name(fx["teams"]["home"]["name"]),
            "awayTeam": team_name(fx["teams"]["away"]["name"]),
            "league": LEAGUES[league_id],
            "eventDate": when.strftime("%Y-%m-%d"),
            "eventTime": when.strftime("%H:%M"),
            "status": status,
            "round": (fx["league"].get("round") or None),
            "homeOdds": mw.get("home"), "drawOdds": mw.get("draw"), "awayOdds": mw.get("away"),
            "oddsMarkets": markets,
            "statsDataQuality": "fallback",
        }
        if status == "FINISHED" and goals.get("home") is not None and goals.get("away") is not None:
            raw["homeScore"], raw["awayScore"] = int(goals["home"]), int(goals["away"])
        return raw
    except (KeyError, TypeError, ValueError):
        return None


# ---------- provider (counted and paced) ----------

class Provider:
    def __init__(self, key: str, storage: str):
        self.key = key
        self.path = os.path.join(storage, "football_calls.json")
        self._last = 0.0
        self.used = 0

    def _today(self) -> str:
        return datetime.now(BOGOTA_TZ).strftime("%Y-%m-%d")

    def calls_today(self) -> int:
        try:
            with open(self.path) as f:
                d = json.load(f)
            return int(d.get("n", 0)) if d.get("day") == self._today() else 0
        except (OSError, ValueError):
            return 0

    def _count(self) -> None:
        n = self.calls_today() + 1       # read BEFORE open(..., "w") truncates the file
        try:
            with open(self.path, "w") as f:
                json.dump({"day": self._today(), "n": n}, f)
        except OSError:
            pass

    def get(self, path: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for attempt in range(3):
            if self.calls_today() >= DAILY_CAP:
                logging.warning("[FOOTBALL] daily call cap reached")
                return None
            wait = MIN_GAP - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            self._count()
            self.used += 1
            try:
                r = requests.get(f"{BASE}/{path}", params=params, headers={"x-apisports-key": self.key}, timeout=30)
                data = r.json()
            except Exception as e:
                logging.warning(f"[FOOTBALL] {path} failed: {e}")
                return None
            err = data.get("errors")
            if err and "rateLimit" in (err if isinstance(err, dict) else {}):
                time.sleep(20)
                continue
            if err:
                logging.warning(f"[FOOTBALL] {path} {params}: {err}")
                return None
            return data
        return None

    def fixtures(self, day: str) -> List[Dict[str, Any]]:
        d = self.get("fixtures", {"date": day})
        return [x for x in (d or {}).get("response", []) if (x.get("league") or {}).get("id") in LEAGUES]

    def odds(self, fixture_id: int) -> Optional[Dict[str, Any]]:
        d = self.get("odds", {"fixture": fixture_id})
        r = (d or {}).get("response") or []
        return r[0] if r else None


# ---------- state ----------

def _load(path: str) -> Dict[str, Any]:
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(path: str, data: Dict[str, Any]) -> None:
    try:
        with open(path, "w") as f:
            json.dump(data, f)
    except OSError:
        pass


def plan(now: datetime, state: Dict[str, Any], in_progress: bool) -> Dict[str, Any]:
    """What this run should do. Pure: `now` Bogota-aware, `state` the saved state,
    `in_progress` = some match of ours is under way or ended within the last 4 hours."""
    today = now.strftime("%Y-%m-%d")
    full = state.get("full_day") != today and now.hour >= 3
    days = [(now + timedelta(days=d)).strftime("%Y-%m-%d") for d in (-1, 0, 1)] if full else (
        [today] if in_progress else [])
    return {"full": full, "days": days, "today": today}


def run(db, insert_fn: Callable[..., Optional[str]], storage: str, now: Optional[datetime] = None) -> Dict[str, Any]:
    from src.domain.models import Match, Sport

    key = os.environ.get("API_FOOTBALL_KEY", "")
    if not key:
        return {"status": "no_key"}
    now = (now or datetime.now(BOGOTA_TZ)).astimezone(BOGOTA_TZ)
    state_path = os.path.join(storage, "football_state.json")
    state = _load(state_path)
    sport = db.query(Sport).filter(Sport.code == "football").first()
    since = (now - timedelta(hours=4)).astimezone(timezone.utc)
    until = (now + timedelta(minutes=30)).astimezone(timezone.utc)
    in_progress = bool(sport and db.query(Match.id).filter(
        Match.sport_id == sport.id, Match.status.in_(["SCHEDULED", "LIVE"]),
        Match.match_date >= since, Match.match_date <= until).first())
    p = plan(now, state, in_progress)
    prov = Provider(key, storage)

    fixtures: List[Dict[str, Any]] = []
    for d in p["days"]:
        fixtures += prov.fixtures(d)

    closing = set(state.get("closing", []))
    priced: Dict[int, Optional[Dict[str, Any]]] = {}
    closing_ids: List[int] = []
    for fx in fixtures:
        fid = fx["fixture"]["id"]
        if status_of(fx["fixture"]["status"]["short"]) != "SCHEDULED":
            continue
        kick = datetime.fromisoformat(fx["fixture"]["date"])
        minutes = (kick - now).total_seconds() / 60
        if minutes <= 0:
            continue
        near = minutes <= CLOSING_MINUTES and fid not in closing
        if p["full"] or near:
            item = prov.odds(fid)
            priced[fid] = pick_markets(book_prices(item)) if item else None
            if near:
                closing_ids.append(fid)

    stored = errors = 0
    for fx in fixtures:
        fid = fx["fixture"]["id"]
        raw = to_raw(fx, priced.get(fid))
        if not raw:
            continue
        before = db.query(Match).filter(Match.external_id == raw["matchId"]).first()
        prev_draw = ((before.extra_data or {}).get("draw_odds") if before is not None else None)
        if raw.get("drawOdds") is None and prev_draw is not None:
            raw["drawOdds"] = prev_draw        # a results-only run must not wipe the stored 1X2 price
        mid = insert_fn(db, sport_code="football", sport_name="Football", competitor_type="team", raw=raw,
                        side_mapping={"homeTeam": "home", "awayTeam": "away"},
                        generated_at=datetime.now(timezone.utc), source_api="api-football")
        if not mid:
            errors += 1
            continue
        stored += 1
        match = db.query(Match).filter(Match.external_id == raw["matchId"]).first()
        if match is not None:
            extra = dict(match.extra_data or {})
            extra["season_api"] = fx["league"].get("season")
            if fid in closing_ids and priced.get(fid):
                extra["odds_markets_closing"] = priced[fid]
                extra["odds_markets_closing_at"] = datetime.now(timezone.utc).isoformat()
            match.extra_data = extra
            if fx["league"].get("season"):
                match.season = season_code(int(fx["league"]["season"]))
            db.commit()

    if p["full"]:
        state["full_day"] = p["today"]
    state["closing"] = (list(closing) + closing_ids)[-200:]
    _save(state_path, state)
    return {"status": "ok", "full": p["full"], "days": p["days"], "fixtures": len(fixtures),
            "stored": stored, "errors": errors, "priced": len([v for v in priced.values() if v]),
            "closing": len(closing_ids), "calls": prov.used, "callsToday": prov.calls_today()}
