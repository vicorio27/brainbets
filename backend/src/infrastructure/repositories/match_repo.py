"""Match repository implementation."""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session

from src.domain.models import Match, MatchCompetitor, Competitor, League, Sport
from src.infrastructure.repositories.base import Repository


class MatchRepository(Repository[Match]):
    def get(self, db: Session, id: str) -> Optional[Match]:
        return db.query(Match).filter(Match.id == UUID(id)).first()

    def get_by_external_id(
        self,
        db: Session,
        external_id: str,
        sport_id: Optional[UUID] = None,
    ) -> Optional[Match]:
        query = db.query(Match).filter(Match.external_id == external_id)
        if sport_id:
            query = query.filter(Match.sport_id == sport_id)
        return query.first()

    def list(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
        sport_code: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Match]:
        query = db.query(Match)
        if sport_code:
            query = query.join(Sport).filter(Sport.code == sport_code)
        if status:
            query = query.filter(Match.status == status)
        return query.order_by(desc(Match.match_date)).offset(skip).limit(limit).all()

    def get_latest(self, db: Session, sport_code: Optional[str] = None) -> Optional[Match]:
        query = db.query(Match)
        if sport_code:
            query = query.join(Sport).filter(Sport.code == sport_code)
        return query.order_by(desc(Match.created_at)).first()

    def create(self, db: Session, obj: Match) -> Match:
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def update(self, db: Session, obj: Match) -> Match:
        db.merge(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def upsert(self, db: Session, obj: Match) -> Match:
        """Create or update a match based on external_id + sport_id."""
        existing = self.get_by_external_id(
            db,
            obj.external_id,
            sport_id=obj.sport_id,
        )
        if existing:
            obj.id = existing.id
            return self.update(db, obj)
        return self.create(db, obj)

    def upsert_match_competitor(
        self,
        db: Session,
        match_id: UUID,
        competitor_id: UUID,
        side: str,
        **kwargs,
    ) -> MatchCompetitor:
        existing = (
            db.query(MatchCompetitor)
            .filter_by(match_id=match_id, side=side)
            .first()
        )
        if existing:
            for key, value in kwargs.items():
                setattr(existing, key, value)
            db.commit()
            db.refresh(existing)
            return existing

        link = MatchCompetitor(
            match_id=match_id,
            competitor_id=competitor_id,
            side=side,
            **kwargs,
        )
        db.add(link)
        db.commit()
        db.refresh(link)
        return link

    def upsert_score(
        self,
        db: Session,
        match_id: UUID,
        home_score: int,
        away_score: int,
        period: str = "FULL_TIME",
    ) -> None:
        from src.domain.models import MatchScore

        existing = (
            db.query(MatchScore)
            .filter_by(match_id=match_id, period=period)
            .first()
        )
        if existing:
            existing.home_score = home_score
            existing.away_score = away_score
        else:
            score = MatchScore(
                match_id=match_id,
                home_score=home_score,
                away_score=away_score,
                period=period,
            )
            db.add(score)
        db.commit()


match_repository = MatchRepository()
