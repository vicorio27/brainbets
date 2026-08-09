"""Competitor repository implementation."""
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from src.domain.models import Competitor, CompetitorStat
from src.infrastructure.repositories.base import Repository


class CompetitorRepository(Repository[Competitor]):
    def get(self, db: Session, id: str) -> Optional[Competitor]:
        return db.query(Competitor).filter(Competitor.id == UUID(id)).first()

    def get_by_external_id(
        self,
        db: Session,
        external_id: str,
        sport_id: UUID,
    ) -> Optional[Competitor]:
        return (
            db.query(Competitor)
            .filter(
                Competitor.external_id == external_id,
                Competitor.sport_id == sport_id,
            )
            .first()
        )

    def get_or_create(
        self,
        db: Session,
        sport_id: UUID,
        name: str,
        competitor_type: str,
        external_id: Optional[str] = None,
        country: Optional[str] = None,
    ) -> Competitor:
        if external_id:
            existing = self.get_by_external_id(db, external_id, sport_id)
            if existing:
                return existing

        # Try fuzzy match by name within same sport
        existing = (
            db.query(Competitor)
            .filter(
                Competitor.sport_id == sport_id,
                Competitor.name.ilike(name),
                Competitor.type == competitor_type,
            )
            .first()
        )
        if existing:
            return existing

        competitor = Competitor(
            sport_id=sport_id,
            name=name,
            type=competitor_type,
            external_id=external_id,
            country=country,
        )
        db.add(competitor)
        db.commit()
        db.refresh(competitor)
        return competitor

    def list(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
        sport_code: Optional[str] = None,
    ) -> List[Competitor]:
        query = db.query(Competitor)
        if sport_code:
            query = query.join(Competitor.sport).filter(
                Competitor.sport.has(code=sport_code)
            )
        return query.offset(skip).limit(limit).all()

    def create(self, db: Session, obj: Competitor) -> Competitor:
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def update(self, db: Session, obj: Competitor) -> Competitor:
        db.merge(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def upsert_stat(self, db: Session, stat: CompetitorStat) -> CompetitorStat:
        existing = (
            db.query(CompetitorStat)
            .filter_by(
                competitor_id=stat.competitor_id,
                league_id=stat.league_id,
                season=stat.season,
                surface=stat.surface,
            )
            .first()
        )
        if existing:
            stat.id = existing.id
            db.merge(stat)
            db.commit()
            db.refresh(stat)
            return stat
        db.add(stat)
        db.commit()
        db.refresh(stat)
        return stat


competitor_repository = CompetitorRepository()
