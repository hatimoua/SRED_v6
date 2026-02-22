"""People endpoints."""
from fastapi import APIRouter, Depends
from sred.api.deps import get_uow
from sred.api.schemas.people import PersonCreate, PersonRead, PersonList, PersonUpdate
from sred.infra.db.uow import UnitOfWork
from sred.services.people_service import PeopleService

router = APIRouter(prefix="/runs/{run_id}/people", tags=["people"])


@router.get("", response_model=PersonList)
def list_people(run_id: int, uow: UnitOfWork = Depends(get_uow)) -> PersonList:
    return PeopleService(uow).list_people(run_id)


@router.post("", response_model=PersonRead, status_code=201)
def create_person(
    run_id: int, payload: PersonCreate, uow: UnitOfWork = Depends(get_uow),
) -> PersonRead:
    return PeopleService(uow).create_person(run_id, payload)


@router.patch("/{person_id}", response_model=PersonRead)
def update_person(
    run_id: int, person_id: int, payload: PersonUpdate, uow: UnitOfWork = Depends(get_uow),
) -> PersonRead:
    return PeopleService(uow).update_person(run_id, person_id, payload)
