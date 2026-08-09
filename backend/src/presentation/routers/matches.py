from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from src.presentation.schemas import MatchesResponse
from src.application.services import DataService
from src.presentation.dependencies import get_data_service
from src.timezone import today_bogota

router = APIRouter(prefix="/matches", tags=["matches"])


def get_router() -> APIRouter:
    r = APIRouter(prefix="/matches", tags=["matches"])

    @r.get("/latest", response_model=MatchesResponse)
    async def get_latest_matches(service: DataService = Depends(get_data_service)):
        data = service.get_latest_matches()
        if not data:
            raise HTTPException(status_code=404, detail="No matches data available")
        return data

    @r.get("/{match_id}/surface-stats")
    async def get_match_surface_stats(match_id: str, service: DataService = Depends(get_data_service)):
        """Career per-surface stats (hard/clay/grass W-L, win rate, Elo) for both
        competitors of a tennis match, by external match id (e.g. TENNIS-123)."""
        data = service.get_match_surface_stats(match_id)
        if not data:
            raise HTTPException(status_code=404, detail="Match not found")
        return data

    @r.get("/{match_id}/tournament-load")
    async def get_match_tournament_load(match_id: str, service: DataService = Depends(get_data_service)):
        """Tournament-to-date physical load (matches played, sets W-L, games W-L)
        for both players of a tennis match, by external match id (e.g. TENNIS-123)."""
        data = service.get_match_tournament_load(match_id)
        if not data:
            raise HTTPException(status_code=404, detail="Match not found")
        return data

    @r.get("/{match_id}/surface-load")
    async def get_match_surface_load(match_id: str, service: DataService = Depends(get_data_service)):
        """Recent effort per surface (matches and games played, last 30 days) and
        rest days since the last match, for both players of a tennis match,
        by external match id (e.g. TENNIS-123)."""
        data = service.get_match_surface_load(match_id)
        if not data:
            raise HTTPException(status_code=404, detail="Match not found")
        return data

    @r.get("/player-set-stats")
    async def get_player_set_stats(
        date_str: Optional[str] = Query(None, alias="date"),
        service: DataService = Depends(get_data_service),
    ):
        """Average games per set by surface for every tennis player with a match
        on the given date (defaults to today, America/Bogota)."""
        target = _parse_date(date_str) or today_bogota()
        return service.get_player_set_stats(target)

    @r.get("/{match_id}/serve-stats")
    async def get_match_serve_stats(match_id: str, service: DataService = Depends(get_data_service)):
        """Serve/return profile (hold/break %, first-serve %, tiebreak record)
        for both players of a tennis match, by external match id (e.g. TENNIS-123)."""
        data = service.get_match_serve_stats(match_id)
        if not data:
            raise HTTPException(status_code=404, detail="Match not found")
        return data

    def _parse_date(value: Optional[str]) -> Optional[date]:
        if not value or not value.strip():
            return None
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            try:
                return datetime.fromisoformat(value.strip()).date()
            except ValueError:
                return None

    @r.get("/by-date", response_model=MatchesResponse)
    async def get_matches_by_date(
        from_str: Optional[str] = Query(None, alias="from"),
        to_str: Optional[str] = Query(None, alias="to"),
        sport: Optional[str] = Query(None, description="Filter by sport code (football, tennis)"),
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
        sort: str = Query("desc", regex="^(asc|desc)$"),
        service: DataService = Depends(get_data_service),
    ):
        """Get matches within a date range (inclusive).

        If from is omitted or empty, defaults to today.
        If to is omitted or empty, defaults to from.
        If sport is provided, only returns matches for that sport.
        """
        date_from = _parse_date(from_str)
        date_to = _parse_date(to_str)
        sport = sport.strip() if sport else None
        if not date_from and not date_to:
            date_from = today_bogota()
        if not date_from:
            date_from = date_to
        if not date_to:
            date_to = date_from
        data = service.get_matches_by_date(date_from, date_to, sport=sport, skip=skip, limit=limit, sort=sort)
        # Always return 200 with empty arrays when no matches are found so n8n
        # workflows that consume this endpoint don't treat "no data" as a fatal error.
        if not data:
            return MatchesResponse(
                generatedAt=datetime.now(timezone.utc).isoformat(),
                tennis=[],
                football=[],
                total=0,
                skip=skip,
                limit=limit,
            )
        return data

    return r
