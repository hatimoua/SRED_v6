"""Payroll validation endpoints."""
from fastapi import APIRouter, Depends
from sred.api.deps import get_uow
from sred.api.schemas.payroll import PayrollValidationResponse
from sred.infra.db.uow import UnitOfWork
from sred.services.payroll_service import PayrollService

router = APIRouter(prefix="/runs/{run_id}", tags=["payroll"])


@router.get("/payroll-validation", response_model=PayrollValidationResponse)
def get_payroll_validation(
    run_id: int, uow: UnitOfWork = Depends(get_uow),
) -> PayrollValidationResponse:
    return PayrollService(uow).get_validation(run_id)
