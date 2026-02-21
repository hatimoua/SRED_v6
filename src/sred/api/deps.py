"""FastAPI dependencies."""
from __future__ import annotations
from typing import Generator
from sred.infra.db.uow import UnitOfWork


def get_uow() -> Generator[UnitOfWork, None, None]:
    """Yield one UnitOfWork per request; commit/rollback in __exit__."""
    with UnitOfWork() as uow:
        yield uow
