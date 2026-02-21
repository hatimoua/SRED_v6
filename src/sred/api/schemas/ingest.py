"""Ingest DTOs — pure Pydantic, zero ORM imports."""
from __future__ import annotations
from enum import Enum
from pydantic import BaseModel


class IngestStatus(str, Enum):
    QUEUED = "QUEUED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class IngestResponse(BaseModel):
    file_id: int
    status: IngestStatus
    message: str
