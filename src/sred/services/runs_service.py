"""Runs use-case service. Owns ORM→DTO mapping; routers never see ORM objects."""
from __future__ import annotations
from sred.domain.exceptions import NotFoundError
from sred.infra.db.uow import UnitOfWork
from sred.infra.db.repositories.run_repository import RunRepository
from sred.api.schemas.runs import RunCreate, RunRead, RunList


class RunsService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def create_run(self, payload: RunCreate) -> RunRead:
        repo = RunRepository(self._uow.session)
        run = repo.create(name=payload.name)
        self._uow.commit()
        return RunRead.model_validate(run)

    def list_runs(self, limit: int = 100, offset: int = 0) -> RunList:
        repo = RunRepository(self._uow.session)
        runs = repo.list_all(limit=limit, offset=offset)
        total = repo.count()
        return RunList(items=[RunRead.model_validate(r) for r in runs], total=total)

    def get_run(self, run_id: int) -> RunRead:
        repo = RunRepository(self._uow.session)
        run = repo.get_by_id(run_id)
        if run is None:
            raise NotFoundError(f"Run {run_id} not found")
        return RunRead.model_validate(run)
