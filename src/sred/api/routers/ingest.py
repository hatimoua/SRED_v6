"""Ingest router — two-phase pattern to avoid SQLite lock contention."""
from fastapi import APIRouter
from sred.logging import logger
from sred.api.schemas.ingest import IngestResponse, IngestStatus
from sred.infra.db.uow import UnitOfWork
from sred.services.ingest_service import IngestService

router = APIRouter(prefix="/runs/{run_id}/files", tags=["ingest"])


@router.post("/{file_id}/process", response_model=IngestResponse)
def process_file(run_id: int, file_id: int) -> IngestResponse:
    """Two-phase ingest:

    Phase 1 — validate inside an explicit UoW that exits cleanly.
    Phase 2 — call process_source_file (opens its own Session) once the UoW is closed.
    """
    # Phase 1: validate; UoW auto-closes on exit
    with UnitOfWork() as uow:
        svc = IngestService(uow)
        _file_id_validated, already_processed = svc.validate(run_id, file_id)

    if already_processed:
        return IngestResponse(
            file_id=file_id,
            status=IngestStatus.COMPLETED,
            message="already processed",
        )

    # Phase 2: UoW is closed; process_source_file opens its own Session
    from sred.ingest.process import process_source_file  # deferred import
    try:
        process_source_file(file_id=file_id)
    except Exception as exc:
        logger.exception(exc)
        return IngestResponse(
            file_id=file_id,
            status=IngestStatus.FAILED,
            message=str(exc),
        )

    return IngestResponse(
        file_id=file_id,
        status=IngestStatus.COMPLETED,
        message="processed successfully",
    )
