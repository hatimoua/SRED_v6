"""CSV DTOs — pure Pydantic, zero ORM imports."""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel


class CSVProfileResponse(BaseModel):
    columns: list[dict[str, Any]]
    row_count: int
    sample_rows: list[dict[str, Any]]


class CSVQueryRequest(BaseModel):
    sql: str


class CSVQueryResponse(BaseModel):
    rows: list[dict[str, Any]]
    error: str | None = None


class MappingProposalRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    hypothesis_id: int
    file_id: int
    mapping_json: str
    confidence: float
    reasoning: str


class MappingProposalList(BaseModel):
    items: list[MappingProposalRead]
    total: int
