"""Ingest service — validation only; actual processing happens outside the UoW."""
from __future__ import annotations
from sred.domain.exceptions import NotFoundError, ConflictError
from sred.infra.db.uow import UnitOfWork
from sred.infra.db.repositories.run_repository import RunRepository
from sred.infra.db.repositories.file_repository import FileRepository
from sred.models.core import FileStatus


class IngestService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def validate(self, run_id: int, file_id: int) -> tuple[int, bool]:
        """Validate that file_id belongs to run_id.

        Returns:
            (file_id, already_processed) — caller decides what to do if already processed.

        Raises:
            NotFoundError if run or file is not found.
            ConflictError if file does not belong to run.
        """
        run_repo = RunRepository(self._uow.session)
        if run_repo.get_by_id(run_id) is None:
            raise NotFoundError(f"Run {run_id} not found")

        file_repo = FileRepository(self._uow.session)
        file = file_repo.get_by_id(file_id)
        if file is None:
            raise NotFoundError(f"File {file_id} not found")
        if file.run_id != run_id:
            raise ConflictError("File does not belong to this run")

        already_processed = file.status == FileStatus.PROCESSED
        return file.id, already_processed
