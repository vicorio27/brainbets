"""FastAPI dependencies for BrainBets backend."""
from fastapi import Depends, HTTPException, Header, status
from sqlalchemy.orm import Session

from src.application.services import DataService
from src.infrastructure.database import get_db
import os

INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")


def get_data_service(db: Session = Depends(get_db)) -> DataService:
    return DataService(db=db)


def verify_internal_api_key(x_internal_api_key: str = Header(...)) -> None:
    if x_internal_api_key != INTERNAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal API key",
        )
