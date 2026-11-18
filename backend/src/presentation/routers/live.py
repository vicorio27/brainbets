"""Followed matches, live (api-tennis get_livescore through application.live_feed).

POST/DELETE follow write without a key, like /my-bets: the app runs on the user's machine.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from src.application.services import DataService
from src.presentation.dependencies import get_data_service
from src.timezone import to_bogota

DUE_BEFORE = timedelta(minutes=10)   # start polling a followed match this long before its time
KEEP_AFTER = timedelta(hours=6)      # a finished followed match stays on the page this long
MAX_LIVE = timedelta(hours=6)        # longest a match is polled after its scheduled time


def get_router() -> APIRouter:
    r = APIRouter(prefix="/live", tags=["live"])

    def _match(service: DataService, match_id: str):
        from src.domain.models import Match
        m = service.db.query(Match).filter(Match.external_id == match_id).first()
        if not m:
            raise HTTPException(status_code=404, detail="Partido no encontrado")
        return m

    @r.post("/follow/{match_id}")
    def follow(match_id: str, service: DataService = Depends(get_data_service)):
        m = _match(service, match_id)
        if m.status in ("FINISHED", "CANCELLED"):
            raise HTTPException(status_code=422, detail="El partido ya terminó")
        m.extra_data = {**(m.extra_data or {}), "live_follow": datetime.now(timezone.utc).isoformat()}  # new dict: gotcha #43
        service.db.commit()
        return {"matchId": match_id, "followed": True}

    @r.delete("/follow/{match_id}")
    def unfollow(match_id: str, service: DataService = Depends(get_data_service)):
        m = _match(service, match_id)
        extra = dict(m.extra_data or {})
        extra.pop("live_follow", None)
        m.extra_data = extra
        service.db.commit()
        return {"matchId": match_id, "followed": False}

    @r.get("/followed")
    def followed(service: DataService = Depends(get_data_service)):
        from src.application import live_feed
        from src.application.form_service import form_for_matches
        from src.domain.models import Match

        now = datetime.now(timezone.utc)
        rows = (service.db.query(Match).filter(Match.extra_data.op("?")("live_follow"))
                .order_by(Match.match_date.asc()).all())
        rows = [m for m in rows if m.status not in ("FINISHED", "CANCELLED")
                or (m.match_date and now - m.match_date <= KEEP_AFTER + timedelta(hours=4))]
        # due: about to start or within MAX_LIVE of its time (a stale "scheduled" match stops costing calls)
        due = [m for m in rows if m.status not in ("FINISHED", "CANCELLED") and m.match_date
               and m.match_date - DUE_BEFORE <= now <= m.match_date + MAX_LIVE]
        feed = live_feed.fetch() if due else {"events": {}, "cached": True, "error": None}
        usual_by = {}
        try:
            for mid, rep in form_for_matches(service.db, [m for m in rows if m.status != "FINISHED"]).items():
                usual_by[mid] = {s: {mt["key"]: mt["base"] for mt in (r or {}).get("metrics") or []}
                                 for s, r in rep.items()}
        except Exception:
            usual_by = {}
        out = []
        for m in rows:
            names = {("p1" if c.side in ("home", "player1") else "p2"): c.competitor.name for c in m.competitors}
            ek = (m.external_id or "").replace("TENNIS-", "")
            event = (feed.get("events") or {}).get(ek)
            view = live_feed.follow_view(m.external_id, names, event, usual_by.get(m.id))
            reading = view["reading"]
            if reading and reading.get("finished") or m.status == "FINISHED":
                state = "terminado"
            elif event:
                state = "en vivo"
            elif m.match_date and m.match_date > now:
                state = "por empezar"
            else:
                state = "esperando el feed"
            when = to_bogota(m.match_date) if m.match_date else None
            out.append({
                "matchId": m.external_id,
                "player1": names.get("p1"), "player2": names.get("p2"),
                "tournament": m.league.name if m.league else None,
                "date": when.strftime("%Y-%m-%d") if when else None,
                "time": when.strftime("%H:%M") if when else None,
                "state": state,
                **view,
            })
        return {"matches": out, "calls": live_feed.calls_today(), "feedError": feed.get("error"),
                "note": "Sin cuotas en vivo: el plan de api-tennis no las da. El feed dice quién ganó cada punto, "
                        "no cómo; el tipo de punto sale de comparar los contadores entre lecturas."}

    return r
