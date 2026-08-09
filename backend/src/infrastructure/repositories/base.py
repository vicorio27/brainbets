"""Base repository protocol and common utilities."""
from abc import ABC, abstractmethod
from typing import Generic, List, Optional, TypeVar

from sqlalchemy.orm import Session

T = TypeVar("T")


class Repository(ABC, Generic[T]):
    """Generic repository interface."""

    @abstractmethod
    def get(self, db: Session, id: str) -> Optional[T]:
        raise NotImplementedError

    @abstractmethod
    def list(self, db: Session, *, skip: int = 0, limit: int = 100) -> List[T]:
        raise NotImplementedError

    @abstractmethod
    def create(self, db: Session, obj: T) -> T:
        raise NotImplementedError

    @abstractmethod
    def update(self, db: Session, obj: T) -> T:
        raise NotImplementedError
