"""Dashboard use-case service."""
from __future__ import annotations
from sred.domain.exceptions import NotFoundError
from sred.infra.db.uow import UnitOfWork
from sred.infra.db.repositories.run_repository import RunRepository
from sred.infra.db.repositories.person_repository import PersonRepository
from sred.infra.db.repositories.file_repository import FileRepository
from sred.api.schemas.dashboard import DashboardSummary


class DashboardService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def get_summary(self, run_id: int) -> DashboardSummary:
        run_repo = RunRepository(self._uow.session)
        run = run_repo.get_by_id(run_id)
        if run is None:
            raise NotFoundError(f"Run {run_id} not found")

        person_repo = PersonRepository(self._uow.session)
        file_repo = FileRepository(self._uow.session)

        return DashboardSummary(
            run_status=run.status.value,
            person_count=person_repo.count_by_run(run_id),
            pending_rates=person_repo.count_pending_rates(run_id),
            file_count=len(file_repo.get_by_run(run_id)),
        )
