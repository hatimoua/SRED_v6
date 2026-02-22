"""Tasks & Gates endpoints."""
from fastapi import APIRouter, Depends
from sred.api.deps import get_uow
from sred.api.schemas.tasks import (
    ContradictionList,
    ReviewTaskList,
    DecisionLockList,
    ReviewDecisionRead,
    DecisionLockRead,
    GateStatusResponse,
    ResolveTaskRequest,
    SupersedeRequest,
)
from sred.infra.db.uow import UnitOfWork
from sred.services.tasks_service import TasksService

router = APIRouter(prefix="/runs/{run_id}", tags=["tasks"])


@router.get("/gate", response_model=GateStatusResponse)
def get_gate_status(run_id: int, uow: UnitOfWork = Depends(get_uow)) -> GateStatusResponse:
    return TasksService(uow).get_gate_status(run_id)


@router.get("/contradictions", response_model=ContradictionList)
def list_contradictions(run_id: int, uow: UnitOfWork = Depends(get_uow)) -> ContradictionList:
    return TasksService(uow).list_contradictions(run_id)


@router.get("/tasks", response_model=ReviewTaskList)
def list_tasks(run_id: int, uow: UnitOfWork = Depends(get_uow)) -> ReviewTaskList:
    return TasksService(uow).list_tasks(run_id)


@router.post("/tasks/{task_id}/resolve", response_model=ReviewDecisionRead)
def resolve_task(
    run_id: int, task_id: int, payload: ResolveTaskRequest,
    uow: UnitOfWork = Depends(get_uow),
) -> ReviewDecisionRead:
    return TasksService(uow).resolve_task(run_id, task_id, payload)


@router.get("/locks", response_model=DecisionLockList)
def list_locks(run_id: int, uow: UnitOfWork = Depends(get_uow)) -> DecisionLockList:
    return TasksService(uow).list_locks(run_id)


@router.post("/locks/{lock_id}/supersede", response_model=DecisionLockRead)
def supersede_lock(
    run_id: int, lock_id: int, payload: SupersedeRequest,
    uow: UnitOfWork = Depends(get_uow),
) -> DecisionLockRead:
    return TasksService(uow).supersede_lock(run_id, lock_id, payload)
