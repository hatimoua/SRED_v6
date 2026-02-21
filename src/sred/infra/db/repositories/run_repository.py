"""Repository for Run records. No business logic; caller owns the transaction."""
from __future__ import annotations
from sqlmodel import Session, select
from sred.models.core import Run


class RunRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_id(self, run_id: int) -> Run | None:
        return self._s.get(Run, run_id)

    def list_all(self, limit: int = 100, offset: int = 0) -> list[Run]:
        return list(self._s.exec(select(Run).offset(offset).limit(limit)).all())

    def count(self) -> int:
        from sqlalchemy import func
        from sqlmodel import col
        result = self._s.exec(select(func.count()).select_from(Run)).one()
        return result

    def create(self, name: str) -> Run:
        run = Run(name=name)
        self._s.add(run)
        self._s.flush()  # get generated PK without committing
        return run
