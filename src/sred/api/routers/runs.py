"""Runs router."""
from fastapi import APIRouter, Depends
from sred.api.deps import get_uow
from sred.api.schemas.runs import RunCreate, RunRead, RunList
from sred.infra.db.uow import UnitOfWork
from sred.services.runs_service import RunsService

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunRead, status_code=201)
def create_run(payload: RunCreate, uow: UnitOfWork = Depends(get_uow)) -> RunRead:
    return RunsService(uow).create_run(payload)


@router.get("", response_model=RunList)
def list_runs(
    limit: int = 100,
    offset: int = 0,
    uow: UnitOfWork = Depends(get_uow),
) -> RunList:
    return RunsService(uow).list_runs(limit=limit, offset=offset)


@router.get("/{run_id}", response_model=RunRead)
def get_run(run_id: int, uow: UnitOfWork = Depends(get_uow)) -> RunRead:
    return RunsService(uow).get_run(run_id)
