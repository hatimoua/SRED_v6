"""CSV tools endpoints."""
from fastapi import APIRouter, Depends
from sred.api.deps import get_uow
from sred.api.schemas.csv import (
    CSVProfileResponse, CSVQueryRequest, CSVQueryResponse,
    MappingProposalList,
)
from sred.infra.db.uow import UnitOfWork
from sred.services.csv_service import CSVService

router = APIRouter(prefix="/runs/{run_id}/files/{file_id}/csv", tags=["csv"])


@router.get("/profile", response_model=CSVProfileResponse)
def profile(
    run_id: int, file_id: int, uow: UnitOfWork = Depends(get_uow),
) -> CSVProfileResponse:
    return CSVService(uow).profile(run_id, file_id)


@router.post("/query", response_model=CSVQueryResponse)
def query(
    run_id: int, file_id: int, payload: CSVQueryRequest, uow: UnitOfWork = Depends(get_uow),
) -> CSVQueryResponse:
    return CSVService(uow).query(run_id, file_id, payload.sql)


@router.get("/proposals", response_model=MappingProposalList)
def list_proposals(
    run_id: int, file_id: int, uow: UnitOfWork = Depends(get_uow),
) -> MappingProposalList:
    return CSVService(uow).list_proposals(run_id, file_id)


@router.post("/proposals/generate", response_model=MappingProposalList)
def generate_proposals(
    run_id: int, file_id: int, uow: UnitOfWork = Depends(get_uow),
) -> MappingProposalList:
    return CSVService(uow).generate_proposals(run_id, file_id)
