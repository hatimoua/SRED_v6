"""Repository for world-model entities (contradictions, tasks, decisions, locks)."""
from __future__ import annotations
from sqlmodel import Session, select, desc
from sred.models.world import (
    Contradiction, ContradictionStatus, ContradictionSeverity,
    ContradictionType,
    ReviewTask, ReviewTaskStatus,
    ReviewDecision,
    DecisionLock,
)


class WorldRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    # --- Contradictions ---

    def list_contradictions(self, run_id: int) -> list[Contradiction]:
        return list(self._s.exec(
            select(Contradiction)
            .where(Contradiction.run_id == run_id)
            .order_by(desc(Contradiction.created_at))
        ).all())

    def list_contradictions_by_type(
        self, run_id: int, contradiction_type: ContradictionType,
    ) -> list[Contradiction]:
        return list(self._s.exec(
            select(Contradiction).where(
                Contradiction.run_id == run_id,
                Contradiction.contradiction_type == contradiction_type,
            )
        ).all())

    def get_contradiction(self, contradiction_id: int) -> Contradiction | None:
        return self._s.get(Contradiction, contradiction_id)

    # --- Review Tasks ---

    def list_tasks(self, run_id: int) -> list[ReviewTask]:
        return list(self._s.exec(
            select(ReviewTask)
            .where(ReviewTask.run_id == run_id)
            .order_by(desc(ReviewTask.created_at))
        ).all())

    def get_task(self, task_id: int) -> ReviewTask | None:
        return self._s.get(ReviewTask, task_id)

    def find_task_by_issue_key(
        self, run_id: int, issue_key: str, status: ReviewTaskStatus,
    ) -> ReviewTask | None:
        return self._s.exec(
            select(ReviewTask).where(
                ReviewTask.run_id == run_id,
                ReviewTask.issue_key == issue_key,
                ReviewTask.status == status,
            )
        ).first()

    # --- Decisions ---

    def create_decision(
        self, *, run_id: int, task_id: int, decision: str, decided_by: str = "HUMAN",
    ) -> ReviewDecision:
        obj = ReviewDecision(
            run_id=run_id, task_id=task_id, decision=decision, decided_by=decided_by,
        )
        self._s.add(obj)
        self._s.flush()
        return obj

    # --- Locks ---

    def list_locks(self, run_id: int) -> list[DecisionLock]:
        return list(self._s.exec(
            select(DecisionLock)
            .where(DecisionLock.run_id == run_id)
            .order_by(desc(DecisionLock.created_at))
        ).all())

    def get_lock(self, lock_id: int) -> DecisionLock | None:
        return self._s.get(DecisionLock, lock_id)

    def create_lock(
        self, *, run_id: int, issue_key: str, decision_id: int, reason: str,
    ) -> DecisionLock:
        lock = DecisionLock(
            run_id=run_id, issue_key=issue_key,
            decision_id=decision_id, reason=reason, active=True,
        )
        self._s.add(lock)
        self._s.flush()
        return lock
