from fastapi import APIRouter, Depends, HTTPException
from src.presentation.schemas import ResultsResponse
from src.application.services import DataService
from src.presentation.dependencies import get_data_service


def get_router() -> APIRouter:
    r = APIRouter(prefix="/results", tags=["results"])

    @r.get("/latest", response_model=ResultsResponse)
    async def get_latest_results(service: DataService = Depends(get_data_service)):
        data = service.get_latest_results()
        if not data:
            raise HTTPException(status_code=404, detail="No results data available")
        return data

    return r
