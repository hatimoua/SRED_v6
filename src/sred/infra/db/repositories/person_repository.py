"""Repository for Person records. No business logic; caller owns the transaction."""
from __future__ import annotations
from sqlalchemy import func
from sqlmodel import Session, select
from sred.models.core import Person, RateStatus


class PersonRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_id(self, person_id: int) -> Person | None:
        return self._s.get(Person, person_id)

    def list_by_run(self, run_id: int) -> list[Person]:
        return list(self._s.exec(select(Person).where(Person.run_id == run_id)).all())

    def count_by_run(self, run_id: int) -> int:
        return self._s.exec(
            select(func.count()).select_from(Person).where(Person.run_id == run_id)
        ).one()

    def count_pending_rates(self, run_id: int) -> int:
        return self._s.exec(
            select(func.count()).select_from(Person).where(
                Person.run_id == run_id, Person.rate_status == RateStatus.PENDING
            )
        ).one()

    def create(self, *, run_id: int, name: str, role: str, hourly_rate: float | None = None) -> Person:
        rate_status = RateStatus.SET if hourly_rate and hourly_rate > 0 else RateStatus.PENDING
        person = Person(
            run_id=run_id,
            name=name,
            role=role,
            hourly_rate=hourly_rate if hourly_rate and hourly_rate > 0 else None,
            rate_status=rate_status,
        )
        self._s.add(person)
        self._s.flush()
        return person
