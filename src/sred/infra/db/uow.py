"""Unit of Work: one session per logical operation."""
from __future__ import annotations
from sqlmodel import Session
from sred.infra.db.engine import engine


class UnitOfWork:
    """Context manager wrapping a single DB session.

    Commits on clean exit, rolls back on exception, always closes.
    """

    def __init__(self) -> None:
        self._session: Session | None = None

    def __enter__(self) -> "UnitOfWork":
        self._session = Session(engine)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is None:
                self._session.commit()
            else:
                self._session.rollback()
        finally:
            self._session.close()
            self._session = None

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError("UnitOfWork is not active — use as a context manager.")
        return self._session

    def commit(self) -> None:
        """Explicit mid-operation commit (e.g. to get a generated PK)."""
        if self._session is None:
            raise RuntimeError("UnitOfWork is not active — use as a context manager.")
        self._session.commit()

    def rollback(self) -> None:
        if self._session is None:
            raise RuntimeError("UnitOfWork is not active — use as a context manager.")
        self._session.rollback()
