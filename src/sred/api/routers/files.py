"""Files router."""
from fastapi import APIRouter, Depends, UploadFile
from sred.api.deps import get_uow
from sred.api.schemas.files import FileRead, FileList
from sred.infra.db.uow import UnitOfWork
from sred.services.files_service import FilesService

router = APIRouter(prefix="/runs/{run_id}/files", tags=["files"])


@router.post("/upload", response_model=FileRead, status_code=201)
async def upload_file(
    run_id: int,
    file: UploadFile,
    uow: UnitOfWork = Depends(get_uow),
) -> FileRead:
    content = await file.read()
    return await FilesService(uow).upload_file(
        run_id=run_id,
        content=content,
        original_filename=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
    )


@router.get("", response_model=FileList)
def list_files(run_id: int, uow: UnitOfWork = Depends(get_uow)) -> FileList:
    return FilesService(uow).list_files(run_id)
