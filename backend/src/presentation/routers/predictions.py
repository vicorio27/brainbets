from datetime import date, datetime, time, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from src.presentation.schemas import (
    PredictionsResponse,
    PredictionWithResult,
    Prediction,
    PredictionProgressResponse,
)
from src.application.services import DataService
from src.presentation.dependencies import get_data_service

router = APIRouter(prefix="/predictions", tags=["predictions"])


def get_router() -> APIRouter:
    r = APIRouter(prefix="/predictions", tags=["predictions"])

    @r.get("/latest", response_model=PredictionsResponse)
    async def get_latest_predictions(service: DataService = Depends(get_data_service)):
        data = service.get_latest_predictions()
        if not data:
            raise HTTPException(status_code=404, detail="No predictions data available")
        return data

    @r.get("/history", response_model=PredictionsResponse)
    async def get_predictions_history(
        sport: Optional[str] = None,
        date_from: Optional[date] = Query(None, alias="from"),
        date_to: Optional[date] = Query(None, alias="to"),
        status: Optional[str] = Query(None, description="Prediction status filter"),
        match_id: Optional[str] = Query(None, alias="matchId", description="External match ID filter (e.g. TENNIS-123)"),
        q: Optional[str] = Query(None, description="Search by player/team name (case-insensitive substring)"),
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
        service: DataService = Depends(get_data_service),
    ):
        dt_from = None
        dt_to = None
        if date_from:
            dt_from = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        if date_to:
            dt_to = datetime.combine(date_to, time.max, tzinfo=timezone.utc)
        return service.get_predictions_history(
            sport=sport, date_from=dt_from, date_to=dt_to, status=status, match_id=match_id, name_query=q, skip=skip, limit=limit
        )

    @r.get("/{prediction_id}/result", response_model=PredictionWithResult)
    async def get_prediction_result(
        prediction_id: str,
        service: DataService = Depends(get_data_service),
    ):
        data = service.get_prediction_result(prediction_id)
        if not data:
            raise HTTPException(status_code=404, detail="Prediction not found")
        return data

    @r.get("/{prediction_id}/progress", response_model=PredictionProgressResponse)
    async def get_prediction_progress(
        prediction_id: str,
        service: DataService = Depends(get_data_service),
    ):
        """Return the live progress timeline for a prediction."""
        data = service.get_prediction_progress(prediction_id)
        if not data:
            raise HTTPException(status_code=404, detail="Prediction not found")
        return data

    return r
