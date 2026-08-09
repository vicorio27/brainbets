"""Prediction repository implementation."""
from datetime import datetime, time, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session

from src.domain.models import Match, Prediction, PredictionResult, Sport
from src.infrastructure.repositories.base import Repository


class PredictionRepository(Repository[Prediction]):
    def get(self, db: Session, id: str) -> Optional[Prediction]:
        return db.query(Prediction).filter(Prediction.id == id).first()

    def get_by_match_and_market(
        self,
        db: Session,
        match_id: UUID,
        market: str,
        predicted_outcome: str,
    ) -> Optional[Prediction]:
        return (
            db.query(Prediction)
            .filter(
                Prediction.match_id == match_id,
                Prediction.market == market,
                Prediction.predicted_outcome == predicted_outcome,
            )
            .order_by(desc(Prediction.created_at))
            .first()
        )

    def list(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
        sport_code: Optional[str] = None,
        status: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> List[Prediction]:
        query = db.query(Prediction)
        if sport_code:
            query = query.join(Prediction.match).join(Match.sport).filter(
                Sport.code == sport_code
            )
        if status:
            query = query.filter(Prediction.status == status)
        if date_from or date_to:
            query = query.join(Prediction.match)
        if date_from:
            query = query.filter(Match.match_date >= date_from)
        if date_to:
            query = query.filter(Match.match_date <= date_to)
        return query.order_by(desc(Prediction.created_at)).offset(skip).limit(limit).all()

    def get_latest(self, db: Session, sport_code: Optional[str] = None) -> Optional[Prediction]:
        query = db.query(Prediction)
        if sport_code:
            query = query.join(Prediction.match).join(Match.sport).filter(
                Sport.code == sport_code
            )
        return query.order_by(desc(Prediction.created_at)).first()

    def create(self, db: Session, obj: Prediction) -> Prediction:
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def update(self, db: Session, obj: Prediction) -> Prediction:
        db.merge(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def upsert(self, db: Session, obj: Prediction) -> Prediction:
        """Create or update a prediction based on match + market + outcome."""
        existing = self.get_by_match_and_market(
            db,
            obj.match_id,
            obj.market,
            obj.predicted_outcome,
        )
        if existing:
            obj.id = existing.id
            return self.update(db, obj)
        return self.create(db, obj)

    def upsert_result(
        self,
        db: Session,
        prediction_id: UUID,
        **kwargs,
    ) -> PredictionResult:
        existing = (
            db.query(PredictionResult)
            .filter(PredictionResult.prediction_id == prediction_id)
            .first()
        )
        if existing:
            for key, value in kwargs.items():
                setattr(existing, key, value)
            db.commit()
            db.refresh(existing)
            return existing

        result = PredictionResult(prediction_id=prediction_id, **kwargs)
        db.add(result)
        db.commit()
        db.refresh(result)
        return result


prediction_repository = PredictionRepository()
