"""Files use-case service. Owns ORM→DTO mapping; routers never see ORM objects."""
from __future__ import annotations
from sred.domain.exceptions import NotFoundError
from sred.infra.db.uow import UnitOfWork
from sred.infra.db.repositories.run_repository import RunRepository
from sred.infra.db.repositories.file_repository import FileRepository
from sred.api.schemas.files import FileRead, FileList
from sred.storage.files import compute_sha256, sanitize_filename
from sred.db import DATA_DIR
from pathlib import Path


class FilesService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def upload_file(
        self,
        run_id: int,
        content: bytes,
        original_filename: str,
        content_type: str,
    ) -> FileRead:
        # Validate run exists
        run_repo = RunRepository(self._uow.session)
        if run_repo.get_by_id(run_id) is None:
            raise NotFoundError(f"Run {run_id} not found")

        sha256 = compute_sha256(content)
        size_bytes = len(content)
        mime_type = content_type

        # Deduplication: return existing record if same content in same run
        file_repo = FileRepository(self._uow.session)
        existing = file_repo.get_by_hash_and_run(sha256, run_id)
        if existing is not None:
            return FileRead.model_validate(existing)

        # Write bytes to disk (same convention as save_upload)
        run_dir = DATA_DIR / "runs" / str(run_id) / "uploads"
        run_dir.mkdir(parents=True, exist_ok=True)
        safe_name = sanitize_filename(original_filename)
        stored_filename = f"{sha256}_{safe_name}"
        stored_path_abs = run_dir / stored_filename
        stored_path_abs.write_bytes(content)
        stored_path_rel = str(stored_path_abs.relative_to(DATA_DIR))

        # Persist DB record
        file = file_repo.create(
            run_id=run_id,
            path=stored_path_rel,
            original_filename=original_filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            content_hash=sha256,
        )
        self._uow.commit()
        return FileRead.model_validate(file)

    def list_files(self, run_id: int) -> FileList:
        # Validate run exists
        run_repo = RunRepository(self._uow.session)
        if run_repo.get_by_id(run_id) is None:
            raise NotFoundError(f"Run {run_id} not found")

        file_repo = FileRepository(self._uow.session)
        files = file_repo.get_by_run(run_id)
        return FileList(items=[FileRead.model_validate(f) for f in files], total=len(files))
