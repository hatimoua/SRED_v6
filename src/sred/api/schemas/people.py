"""People DTOs — pure Pydantic, zero ORM imports."""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, field_validator


class RateStatusDTO(str, Enum):
    PENDING = "PENDING"
    SET = "SET"


class PersonCreate(BaseModel):
    name: str
    role: str
    hourly_rate: float | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty")
        return v

    @field_validator("role")
    @classmethod
    def role_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("role must not be empty")
        return v


class PersonUpdate(BaseModel):
    hourly_rate: float | None = None


class PersonRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    run_id: int
    name: str
    role: str
    email: str | None = None
    hourly_rate: float | None = None
    rate_status: RateStatusDTO
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PersonList(BaseModel):
    items: list[PersonRead]
    total: int
