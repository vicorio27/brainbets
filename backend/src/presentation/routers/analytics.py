from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.application import bankroll_service
from src.infrastructure.database import get_db
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

    @r.get("/lab")
    def get_lab():
        """Shadow models under test against the bookmaker (read from the
        artifact the daily training writes; nothing is computed here)."""
        from src.application.set1_lab_service import get_all_lab_reports

        return get_all_lab_reports()

    # Plain `def` on purpose: the per-market Monte Carlo takes a few seconds
    # of CPU, and a sync endpoint runs in the threadpool instead of freezing
    # the event loop for every other request (see gotcha #47).
    @r.get("/bankroll")
    def get_bankroll(
        initial: float = Query(100.0, gt=0, le=1_000_000_000),
        strategy: str = Query("percent", pattern="^(percent|flat|kelly)$"),
        stake_pct: float = Query(2.0, ge=0.1, le=50.0, alias="stakePct"),
        kelly_multiplier: float = Query(0.5, ge=0.05, le=1.0, alias="kellyMultiplier"),
        max_stake_pct: float = Query(10.0, ge=0.1, le=50.0, alias="maxStakePct"),
        target: float = Query(2.0, ge=1.01, le=100.0),
        days: int = Query(180, ge=1, le=1825),
        sport: Optional[str] = Query(None),
        market: Optional[str] = Query(None),
        min_confidence: int = Query(0, ge=0, le=100, alias="minConfidence"),
        min_ev: Optional[float] = Query(None, alias="minEv"),
        min_edge: Optional[float] = Query(
            None, ge=-100.0, le=100.0, alias="minEdge",
            description="Minimum edge in percent (p*odds-1, calibrated p)",
        ),
        use_calibrated: bool = Query(True, alias="useCalibrated"),
        sims: int = Query(400, ge=50, le=2000),
        horizon_days: int = Query(365, ge=30, le=1095, alias="horizonDays"),
        db: Session = Depends(get_db),
    ):
        """Bankroll ("caja") backtest: how the money would have evolved and
        how long it would take to multiply it by `target`."""
        return bankroll_service.simulate(
            db,
            initial=initial,
            strategy=strategy,
            stake_pct=stake_pct,
            kelly_multiplier=kelly_multiplier,
            max_stake_pct=max_stake_pct,
            target_multiple=target,
            days=days,
            sport=sport,
            market=market,
            min_confidence=min_confidence,
            min_ev=min_ev,
            use_calibrated=use_calibrated,
            sims=sims,
            horizon_days=horizon_days,
            min_edge=min_edge / 100.0 if min_edge is not None else None,
        )

    return r
