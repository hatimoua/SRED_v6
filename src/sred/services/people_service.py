"""People use-case service."""
from __future__ import annotations
from sred.domain.exceptions import NotFoundError
from sred.infra.db.uow import UnitOfWork
from sred.infra.db.repositories.run_repository import RunRepository
from sred.infra.db.repositories.person_repository import PersonRepository
from sred.api.schemas.people import PersonCreate, PersonRead, PersonList, PersonUpdate


class PeopleService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def _ensure_run(self, run_id: int) -> None:
        if RunRepository(self._uow.session).get_by_id(run_id) is None:
            raise NotFoundError(f"Run {run_id} not found")

    def list_people(self, run_id: int) -> PersonList:
        self._ensure_run(run_id)
        repo = PersonRepository(self._uow.session)
        people = repo.list_by_run(run_id)
        return PersonList(
            items=[PersonRead.model_validate(p) for p in people],
            total=len(people),
        )

    def create_person(self, run_id: int, payload: PersonCreate) -> PersonRead:
        self._ensure_run(run_id)
        repo = PersonRepository(self._uow.session)
        person = repo.create(
            run_id=run_id,
            name=payload.name,
            role=payload.role,
            hourly_rate=payload.hourly_rate,
        )
        self._uow.commit()
        return PersonRead.model_validate(person)

    def update_person(self, run_id: int, person_id: int, payload: PersonUpdate) -> PersonRead:
        self._ensure_run(run_id)
        repo = PersonRepository(self._uow.session)
        person = repo.get_by_id(person_id)
        if person is None or person.run_id != run_id:
            raise NotFoundError(f"Person {person_id} not found in run {run_id}")

        if payload.hourly_rate is not None and payload.hourly_rate > 0:
            from sred.models.core import RateStatus
            person.hourly_rate = payload.hourly_rate
            person.rate_status = RateStatus.SET
            self._uow.session.add(person)
            self._uow.commit()

        return PersonRead.model_validate(person)
