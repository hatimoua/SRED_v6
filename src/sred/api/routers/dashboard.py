"""Dashboard endpoints."""
from fastapi import APIRouter, Depends
from sred.api.deps import get_uow
from sred.api.schemas.dashboard import DashboardSummary
from sred.infra.db.uow import UnitOfWork
from sred.services.dashboard_service import DashboardService

router = APIRouter(prefix="/runs/{run_id}", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def get_summary(run_id: int, uow: UnitOfWork = Depends(get_uow)) -> DashboardSummary:
    return DashboardService(uow).get_summary(run_id)
