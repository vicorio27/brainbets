"""Every ATP match of ours that is being played now (api-tennis get_livescore via application.live_feed).

No "follow": one call brings every live match, so the page shows them all. The feed is read only
while the En vivo page is open AND one of our matches is within its time window, so an idle day
costs nothing.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from src.application.services import DataService
from src.presentation.dependencies import get_data_service
from src.timezone import BOGOTA_TZ, to_bogota

DUE_BEFORE = timedelta(minutes=10)   # start reading this long before a match's time
MAX_LIVE = timedelta(hours=6)        # and stop this long after it (a stale "scheduled" match stops costing calls)
SHOW_FINISHED = timedelta(hours=3)   # a match that ended stays on the page this long


def get_router() -> APIRouter:
    r = APIRouter(prefix="/live", tags=["live"])

    @r.get("/matches")
    def live_matches(service: DataService = Depends(get_data_service)):
        from src.application import live_feed
        from src.application.form_service import form_for_matches
        from src.domain.models import Match, Sport

        now = datetime.now(timezone.utc)
        tennis = (service.db.query(Match).join(Sport, Sport.id == Match.sport_id)
                  .filter(Sport.code == "tennis", Match.match_date >= now - MAX_LIVE - SHOW_FINISHED,
                          Match.match_date <= now + timedelta(days=1))
                  .order_by(Match.match_date.asc()).all())
        in_window = [m for m in tennis if m.status not in ("FINISHED", "CANCELLED")
                     and m.match_date - DUE_BEFORE <= now <= m.match_date + MAX_LIVE]
        feed = live_feed.fetch() if in_window else {"events": {}, "cached": True, "error": None}
        events = feed.get("events") or {}

        # on the page: ours that are in the feed, plus the ones the page already showed (to report the end)
        shown = [m for m in tennis if (m.external_id or "").replace("TENNIS-", "") in events
                 or live_feed.was_shown(m.external_id)]
        usual_by = {}
        try:
            for mid, rep in form_for_matches(service.db, shown).items():
                usual_by[mid] = {s: {mt["key"]: mt["base"] for mt in (x or {}).get("metrics") or []}
                                 for s, x in rep.items()}
        except Exception:
            usual_by = {}
        out = []
        for m in shown:
            names = {("p1" if c.side in ("home", "player1") else "p2"): c.competitor.name for c in m.competitors}
            event = events.get((m.external_id or "").replace("TENNIS-", ""))
            view = live_feed.follow_view(m.external_id, names, event, usual_by.get(m.id))
            reading = view["reading"]
            finished = bool(reading and reading.get("finished")) or m.status == "FINISHED"
            if finished and live_feed.finished_long_ago(m.external_id, SHOW_FINISHED):
                continue
            when = to_bogota(m.match_date) if m.match_date else None
            out.append({
                "matchId": m.external_id,
                "player1": names.get("p1"), "player2": names.get("p2"),
                "tournament": m.league.name if m.league else None,
                "date": when.strftime("%Y-%m-%d") if when else None,
                "time": when.strftime("%H:%M") if when else None,
                "state": "terminado" if finished else "en vivo" if event else "esperando el feed",
                **view,
            })
        today = datetime.now(BOGOTA_TZ).date()
        upcoming = []
        for m in tennis:
            when = to_bogota(m.match_date) if m.match_date else None
            if (m.status == "SCHEDULED" and when and when.date() == today and m.match_date > now
                    and not any(o["matchId"] == m.external_id for o in out)):
                names = {("p1" if c.side in ("home", "player1") else "p2"): c.competitor.name for c in m.competitors}
                upcoming.append({"matchId": m.external_id, "player1": names.get("p1"), "player2": names.get("p2"),
                                 "tournament": m.league.name if m.league else None, "time": when.strftime("%H:%M")})
        return {"matches": out, "upcoming": upcoming, "reading": bool(in_window),
                "calls": live_feed.calls_today(), "feedError": feed.get("error"),
                "note": "Sin cuotas en vivo: el plan de api-tennis no las da. El feed dice quién ganó cada punto, "
                        "no cómo; el tipo de punto sale de comparar los contadores entre lecturas."}

    return r
