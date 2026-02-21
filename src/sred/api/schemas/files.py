"""File DTOs — pure Pydantic, zero ORM imports."""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from pydantic import BaseModel


class FileStatusDTO(str, Enum):
    UPLOADED = "UPLOADED"
    PROCESSED = "PROCESSED"
    ERROR = "ERROR"


class FileRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    run_id: int
    path: str
    original_filename: str
    mime_type: str
    size_bytes: int
    status: FileStatusDTO
    content_hash: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FileList(BaseModel):
    items: list[FileRead]
    total: int
