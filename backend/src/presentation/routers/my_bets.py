"""The user's own bets (combo calculator). The only public endpoints that write.

Every other public endpoint is read-only and writes go through /internal with
its key; these let the dashboard register and remove the user's bets. The app
runs on the user's machine, so they are not authenticated.
"""
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.application import user_bets_service
from src.infrastructure.database import get_db


class LegIn(BaseModel):
    matchId: str
    kind: str
    selector: Dict[str, str]
    label: str
    odds: float
    probability: Optional[float] = None
    bestOdds: Optional[float] = None


class BetIn(BaseModel):
    amount: float
    legs: List[LegIn]


def get_router() -> APIRouter:
    r = APIRouter(prefix="/my-bets", tags=["my-bets"])

    @r.get("")
    def list_bets(db: Session = Depends(get_db)) -> Dict[str, Any]:
        """Every registered bet, settled against results first, with a summary."""
        return user_bets_service.list_bets(db)

    @r.post("")
    def create_bet(payload: BetIn, db: Session = Depends(get_db)) -> Dict[str, Any]:
        try:
            bet = user_bets_service.create_bet(db, payload.model_dump())
        except user_bets_service.BetError as e:
            raise HTTPException(status_code=422, detail=str(e))
        return {"id": str(bet.id), "status": bet.status}

    @r.delete("/{bet_id}")
    def delete_bet(bet_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
        try:
            uuid.UUID(bet_id)
            found = user_bets_service.delete_bet(db, bet_id)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e) if isinstance(e, user_bets_service.BetError) else "id inválido")
        if not found:
            raise HTTPException(status_code=404, detail="No existe esa apuesta.")
        return {"deleted": True}

    return r
