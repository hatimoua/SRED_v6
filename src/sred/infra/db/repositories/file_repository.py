"""Repository for File records. No business logic; caller owns the transaction."""
from __future__ import annotations
from sqlmodel import Session, select
from sred.models.core import File


class FileRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_id(self, file_id: int) -> File | None:
        return self._s.get(File, file_id)

    def get_by_run(self, run_id: int) -> list[File]:
        return list(self._s.exec(select(File).where(File.run_id == run_id)).all())

    def get_by_hash_and_run(self, content_hash: str, run_id: int) -> File | None:
        return self._s.exec(
            select(File).where(File.content_hash == content_hash, File.run_id == run_id)
        ).first()

    def create(
        self,
        *,
        run_id: int,
        path: str,
        original_filename: str,
        mime_type: str,
        size_bytes: int,
        content_hash: str,
    ) -> File:
        file = File(
            run_id=run_id,
            path=path,
            original_filename=original_filename,
            file_type=mime_type,   # file_type mirrors mime_type (DB constraint)
            mime_type=mime_type,
            size_bytes=size_bytes,
            content_hash=content_hash,
        )
        self._s.add(file)
        self._s.flush()  # get generated PK without committing
        return file
