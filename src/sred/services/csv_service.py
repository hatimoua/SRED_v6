"""CSV tools use-case service."""
from __future__ import annotations
from sred.domain.exceptions import NotFoundError
from sred.infra.db.uow import UnitOfWork
from sred.infra.db.repositories.run_repository import RunRepository
from sred.infra.db.repositories.file_repository import FileRepository
from sred.infra.db.repositories.csv_repository import CSVRepository
from sred.api.schemas.csv import (
    CSVProfileResponse, CSVQueryResponse, MappingProposalRead, MappingProposalList,
)
from sred.config import settings


class CSVService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def _get_file_path(self, run_id: int, file_id: int) -> str:
        run_repo = RunRepository(self._uow.session)
        if run_repo.get_by_id(run_id) is None:
            raise NotFoundError(f"Run {run_id} not found")

        file_repo = FileRepository(self._uow.session)
        f = file_repo.get_by_id(file_id)
        if f is None or f.run_id != run_id:
            raise NotFoundError(f"File {file_id} not found in run {run_id}")
        return str(settings.data_dir / f.path)

    def profile(self, run_id: int, file_id: int) -> CSVProfileResponse:
        from sred.ingest.csv_intel import csv_profile
        file_path = self._get_file_path(run_id, file_id)
        result = csv_profile(file_path)
        return CSVProfileResponse(**result)

    def query(self, run_id: int, file_id: int, sql: str) -> CSVQueryResponse:
        from sred.ingest.csv_intel import csv_query
        file_path = self._get_file_path(run_id, file_id)
        rows = csv_query(file_path, sql)
        if rows and isinstance(rows[0], dict) and "error" in rows[0]:
            return CSVQueryResponse(rows=[], error=rows[0]["error"])
        return CSVQueryResponse(rows=rows)

    def list_proposals(self, run_id: int, file_id: int) -> MappingProposalList:
        # Validate file belongs to run
        self._get_file_path(run_id, file_id)
        repo = CSVRepository(self._uow.session)
        proposals = repo.list_proposals_by_file(file_id)
        return MappingProposalList(
            items=[MappingProposalRead.model_validate(p) for p in proposals],
            total=len(proposals),
        )

    def generate_proposals(self, run_id: int, file_id: int) -> MappingProposalList:
        from sred.ingest.csv_intel import propose_schema_mapping
        file_repo = FileRepository(self._uow.session)
        f = file_repo.get_by_id(file_id)
        if f is None or f.run_id != run_id:
            raise NotFoundError(f"File {file_id} not found in run {run_id}")
        propose_schema_mapping(self._uow.session, f)
        self._uow.commit()
        return self.list_proposals(run_id, file_id)
