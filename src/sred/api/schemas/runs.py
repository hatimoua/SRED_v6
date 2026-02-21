"""Run DTOs — pure Pydantic, zero ORM imports."""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, field_validator


class RunStatusDTO(str, Enum):
    INITIALIZING = "INITIALIZING"
    PROCESSING = "PROCESSING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RunCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty")
        return v


class RunRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    status: RunStatusDTO
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RunList(BaseModel):
    items: list[RunRead]
    total: int
