"""Goal minutes (and red cards) of every finished football match we hold.

`fixtures?id=` returns the events of a match together with the team ids and the half-time score,
so one call per match gives: who scored when, and the score at the break. Stored in
`matches.extra_data`:

    goals: [{m: minute, x: stoppage minutes, s: home|away (the side that SCORED), k: g|p|o}]   g goal, p penalty, o own goal
    reds:  [{m, s}]                       s = side of the player sent off
    halftime: {home, away}                only when missing
    events_done: true                     looked up (even when there was nothing), never asked twice

Matches come from the football-data files (no API id) or from API-Football; only those that carry an
API fixture id (`af_fixture`, or an `FOOTBALL-AF-<id>` external id) can be looked up.
"""
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.application.football_collect_service import Provider
from src.domain.models import Match, Sport


def parse_events(fixture: Dict[str, Any]) -> Dict[str, Any]:
    """One `fixtures?id=` item -> {goals, reds, halftime}. An own goal counts for the side that benefits."""
    teams = fixture.get("teams") or {}
    home_id, away_id = (teams.get("home") or {}).get("id"), (teams.get("away") or {}).get("id")
    goals: List[Dict[str, Any]] = []
    reds: List[Dict[str, Any]] = []
    for ev in fixture.get("events") or []:
        tid = (ev.get("team") or {}).get("id")
        side = "home" if tid == home_id else "away" if tid == away_id else None
        if side is None:
            continue
        t = ev.get("time") or {}
        minute, extra = t.get("elapsed"), t.get("extra") or 0
        if minute is None:
            continue
        kind, detail = ev.get("type"), (ev.get("detail") or "")
        if kind == "Goal":
            if detail == "Missed Penalty":
                continue
            # The API already puts an own goal under the team that benefits (checked against final scores).
            goals.append({"m": minute, "x": extra, "s": side, "k": "o" if detail == "Own Goal" else "p" if detail == "Penalty" else "g"})
        elif kind == "Card" and detail in ("Red Card", "Second Yellow card"):
            reds.append({"m": minute, "s": side})
    ht = (fixture.get("score") or {}).get("halftime") or {}
    halftime = {"home": int(ht["home"]), "away": int(ht["away"])} if ht.get("home") is not None and ht.get("away") is not None else None
    return {"goals": goals, "reds": reds, "halftime": halftime}


def fixture_id(match: Match) -> Optional[int]:
    extra = match.extra_data or {}
    if extra.get("af_fixture"):
        return int(extra["af_fixture"])
    ext = match.external_id or ""
    if ext.startswith("FOOTBALL-AF-"):
        try:
            return int(ext.split("-")[-1])
        except ValueError:
            return None
    return None


def run(db: Session, storage: str, max_calls: int = 5000) -> Dict[str, Any]:
    key = __import__("os").environ.get("API_FOOTBALL_KEY", "")
    if not key:
        return {"error": "no API_FOOTBALL_KEY"}
    prov = Provider(key, storage)
    sport = db.query(Sport).filter(Sport.code == "football").first()
    if not sport:
        return {"error": "no football"}
    matches = (db.query(Match).filter(Match.sport_id == sport.id, Match.status == "FINISHED")
               .order_by(Match.match_date.desc()).all())
    done = skipped = unmatched = empty = 0
    for m in matches:
        extra = m.extra_data or {}
        if extra.get("events_done"):
            skipped += 1
            continue
        fid = fixture_id(m)
        if not fid:
            unmatched += 1
            continue
        if prov.used >= max_calls:
            break
        d = prov.get("fixtures", {"id": fid})
        if d is None:
            break                                   # cap or a hard error: the next run resumes
        resp = (d.get("response") or [])
        if not resp:
            empty += 1
            m.extra_data = {**extra, "events_done": True}
            db.commit()
            continue
        ev = parse_events(resp[0])
        new = {**extra, "af_fixture": fid, "events_done": True, "goals": ev["goals"], "reds": ev["reds"]}
        if ev["halftime"] and "halftime" not in extra:
            new["halftime"] = ev["halftime"]
        m.extra_data = new                          # new dict (gotcha #43)
        done += 1
        if done % 100 == 0:
            db.commit()
            logging.warning("[FOOTBALL-EVENTS] %d downloaded", done)
    db.commit()
    return {"downloaded": done, "alreadyHad": skipped, "unmatched": unmatched, "empty": empty, "calls": prov.used}
