"""Tasks & Gates use-case service."""
from __future__ import annotations
from sred.domain.exceptions import NotFoundError
from sred.infra.db.uow import UnitOfWork
from sred.infra.db.repositories.run_repository import RunRepository
from sred.infra.db.repositories.world_repository import WorldRepository
from sred.api.schemas.tasks import (
    ContradictionRead, ContradictionList,
    ReviewTaskRead, ReviewTaskList,
    DecisionLockRead, DecisionLockList,
    ReviewDecisionRead,
    GateStatusResponse,
    ResolveTaskRequest,
    SupersedeRequest,
)
from sred.models.world import (
    ContradictionStatus, ReviewTaskStatus,
)
from sred.gates import update_run_gate_status, get_blocking_contradictions, get_open_blocking_tasks


class TasksService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def _ensure_run(self, run_id: int) -> None:
        if RunRepository(self._uow.session).get_by_id(run_id) is None:
            raise NotFoundError(f"Run {run_id} not found")

    # --- Gate ---

    def get_gate_status(self, run_id: int) -> GateStatusResponse:
        self._ensure_run(run_id)
        status = update_run_gate_status(self._uow.session, run_id)
        blockers = get_blocking_contradictions(self._uow.session, run_id)
        blocking_tasks = get_open_blocking_tasks(self._uow.session, run_id)
        return GateStatusResponse(
            run_status=status.value,
            blocking_contradictions=len(blockers),
            blocking_tasks=len(blocking_tasks),
        )

    # --- Contradictions ---

    def list_contradictions(self, run_id: int) -> ContradictionList:
        self._ensure_run(run_id)
        repo = WorldRepository(self._uow.session)
        items = repo.list_contradictions(run_id)
        return ContradictionList(
            items=[ContradictionRead.model_validate(c) for c in items],
            total=len(items),
        )

    # --- Tasks ---

    def list_tasks(self, run_id: int) -> ReviewTaskList:
        self._ensure_run(run_id)
        repo = WorldRepository(self._uow.session)
        items = repo.list_tasks(run_id)
        return ReviewTaskList(
            items=[ReviewTaskRead.model_validate(t) for t in items],
            total=len(items),
        )

    def resolve_task(self, run_id: int, task_id: int, payload: ResolveTaskRequest) -> ReviewDecisionRead:
        self._ensure_run(run_id)
        repo = WorldRepository(self._uow.session)
        task = repo.get_task(task_id)
        if task is None or task.run_id != run_id:
            raise NotFoundError(f"Task {task_id} not found in run {run_id}")

        # 1. Create decision
        decision = repo.create_decision(
            run_id=run_id, task_id=task_id, decision=payload.decision,
        )

        # 2. Create lock
        repo.create_lock(
            run_id=run_id, issue_key=task.issue_key,
            decision_id=decision.id, reason=payload.decision,
        )

        # 3. Mark task resolved
        task.status = ReviewTaskStatus.RESOLVED
        self._uow.session.add(task)

        # 4. Resolve linked contradiction
        if task.contradiction_id:
            contradiction = repo.get_contradiction(task.contradiction_id)
            if contradiction:
                contradiction.status = ContradictionStatus.RESOLVED
                self._uow.session.add(contradiction)

        self._uow.commit()

        # 5. Re-evaluate gate
        update_run_gate_status(self._uow.session, run_id)

        return ReviewDecisionRead.model_validate(decision)

    # --- Locks ---

    def list_locks(self, run_id: int) -> DecisionLockList:
        self._ensure_run(run_id)
        repo = WorldRepository(self._uow.session)
        items = repo.list_locks(run_id)
        return DecisionLockList(
            items=[DecisionLockRead.model_validate(lk) for lk in items],
            total=len(items),
        )

    def supersede_lock(self, run_id: int, lock_id: int, payload: SupersedeRequest) -> DecisionLockRead:
        self._ensure_run(run_id)
        repo = WorldRepository(self._uow.session)
        old_lock = repo.get_lock(lock_id)
        if old_lock is None or old_lock.run_id != run_id:
            raise NotFoundError(f"Lock {lock_id} not found in run {run_id}")

        # 1. Deactivate old lock
        old_lock.active = False
        self._uow.session.add(old_lock)

        # 2. Find original task
        orig_task = repo.find_task_by_issue_key(
            run_id, old_lock.issue_key, ReviewTaskStatus.RESOLVED,
        )
        task_id = orig_task.id if orig_task else old_lock.decision_id

        # 3. New decision
        new_decision = repo.create_decision(
            run_id=run_id, task_id=task_id,
            decision=f"[SUPERSEDE] {payload.reason}",
        )

        # 4. New lock
        new_lock = repo.create_lock(
            run_id=run_id, issue_key=old_lock.issue_key,
            decision_id=new_decision.id, reason=payload.reason,
        )

        self._uow.commit()

        # 5. Re-evaluate gate
        update_run_gate_status(self._uow.session, run_id)

        return DecisionLockRead.model_validate(new_lock)
