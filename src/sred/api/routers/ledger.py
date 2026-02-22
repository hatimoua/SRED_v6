"""Ledger endpoints."""
from fastapi import APIRouter, Depends
from sred.api.deps import get_uow
from sred.api.schemas.ledger import LedgerSummaryResponse
from sred.infra.db.uow import UnitOfWork
from sred.services.ledger_service import LedgerService

router = APIRouter(prefix="/runs/{run_id}", tags=["ledger"])


@router.get("/ledger", response_model=LedgerSummaryResponse)
def get_ledger_summary(
    run_id: int, uow: UnitOfWork = Depends(get_uow),
) -> LedgerSummaryResponse:
    return LedgerService(uow).get_summary(run_id)
