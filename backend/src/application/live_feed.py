"""Live feed: one get_livescore call brings every ATP match in play.

Called only from GET /live/matches, i.e. only while the En vivo page is open and one of our
matches is within its time window. Cached POLL_SECONDS; a daily cap (Bogota day) stops calls.
The previous reading of each match and its event log live in memory (they restart with the backend).
"""
import json
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, List, Optional

import requests

from src.application.live_service import general_read, parse_event, point_events
from src.timezone import today_bogota

POLL_SECONDS = int(os.environ.get("LIVE_POLL_SECONDS", "30"))
DAILY_CAP = int(os.environ.get("LIVE_DAILY_CAP", "1500"))
API = "https://api.api-tennis.com/tennis/"
COUNTER_FILE = os.environ.get("LIVE_COUNTER_FILE", "/storage/live_calls.json")
MAX_EVENTS = 40

_lock = threading.Lock()
_cache: Dict[str, Any] = {"at": 0.0, "events": None, "error": None}
_prev: Dict[str, Dict[str, Any]] = {}
_log: Dict[str, Deque[Dict[str, Any]]] = {}


def _counter() -> Dict[str, Any]:
    try:
        with open(COUNTER_FILE) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    today = today_bogota().isoformat()
    return data if data.get("day") == today else {"day": today, "calls": 0}


def _save_counter(data: Dict[str, Any]) -> None:
    try:
        with open(COUNTER_FILE, "w") as f:
            json.dump(data, f)
    except OSError as exc:
        logging.warning("[LIVE] counter not saved: %s", exc)


_ended: Dict[str, float] = {}


def was_shown(match_id: Optional[str]) -> bool:
    """The page showed it before (so it keeps it until a while after it ends)."""
    return bool(match_id) and match_id in _prev


def finished_long_ago(match_id: str, keep: timedelta) -> bool:
    """Remember when a shown match ended; True once that is more than `keep` ago."""
    at = _ended.setdefault(match_id, time.time())
    return time.time() - at > keep.total_seconds()


def calls_today() -> Dict[str, Any]:
    c = _counter()
    return {"today": c["calls"], "cap": DAILY_CAP, "pollSeconds": POLL_SECONDS}


def fetch() -> Dict[str, Any]:
    """{event_key: event} of the ATP singles live now, at most one call per POLL_SECONDS."""
    with _lock:
        if _cache["events"] is not None and time.time() - _cache["at"] < POLL_SECONDS:
            return {"events": _cache["events"], "cached": True, "error": _cache["error"]}
        c = _counter()
        if c["calls"] >= DAILY_CAP:
            return {"events": _cache["events"] or {}, "cached": True, "error": "tope_diario"}
        key = os.environ.get("TENNIS_API_KEY", "")
        error = None
        events: Dict[str, Any] = {}
        try:
            resp = requests.get(API, params={"method": "get_livescore", "APIkey": key, "event_type_key": 265}, timeout=20)
            body = resp.json()
            res = body.get("result")
            if isinstance(res, list):
                events = {str(e.get("event_key")): e for e in res}
            else:
                error = "sin_datos"
        except Exception as exc:  # network/JSON: show the last reading instead of failing the page
            logging.warning("[LIVE] get_livescore failed: %s", str(exc).replace(key, "<KEY>") if key else exc)
            error = "sin_conexion"
            events = _cache["events"] or {}
        c["calls"] += 1
        _save_counter(c)
        _cache.update(at=time.time(), events=events, error=error)
        return {"events": events, "cached": False, "error": error}


def follow_view(match_id: str, names: Dict[str, str], event: Optional[Dict[str, Any]],
                usual: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[str, Any]:
    """Current reading, what happened since the last one, and the overall read."""
    if not event:
        prev = _prev.get(match_id)
        return {"reading": prev, "events": list(_log.get(match_id) or []), "general": None}
    cur = parse_event(event)
    prev = _prev.get(match_id)
    texts = point_events(prev, cur, names)
    if texts:
        log = _log.setdefault(match_id, deque(maxlen=MAX_EVENTS))
        at = datetime.now(timezone.utc).isoformat()
        for t in texts:
            log.appendleft({"at": at, "text": t})
    _prev[match_id] = cur
    return {"reading": cur, "events": list(_log.get(match_id) or []), "general": general_read(cur, names, usual)}
