from fastapi import APIRouter, Depends, Query
from src.presentation.schemas import AccuracyMetrics, DashboardSummary
from src.application.services import DataService
from src.presentation.dependencies import get_data_service


def get_router() -> APIRouter:
    r = APIRouter(prefix="/analytics", tags=["analytics"])

    @r.get("/accuracy", response_model=AccuracyMetrics)
    async def get_accuracy(service: DataService = Depends(get_data_service)):
        return service.get_accuracy()

    @r.get("/accuracy-by-day")
    async def get_accuracy_by_day(
        days: int = Query(30, ge=1, le=365),
        service: DataService = Depends(get_data_service),
    ):
        """Validated-prediction accuracy per day (by match date, Bogota)."""
        return service.get_accuracy_by_day(days=days)

    @r.get("/dashboard", response_model=DashboardSummary)
    async def get_dashboard(service: DataService = Depends(get_data_service)):
        return service.get_dashboard_summary()

    return r
