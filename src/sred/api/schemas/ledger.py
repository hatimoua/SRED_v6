"""Ledger DTOs — pure Pydantic, zero ORM imports."""
from __future__ import annotations
from datetime import date
from pydantic import BaseModel


class LedgerLabourHourRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    run_id: int
    person_id: int | None = None
    date: date
    hours: float
    description: str | None = None
    bucket: str
    inclusion_fraction: float
    confidence: float | None = None


class LedgerLabourHourList(BaseModel):
    items: list[LedgerLabourHourRead]
    total: int


class PersonBreakdown(BaseModel):
    person_name: str
    role: str
    total_hours: float
    sred_hours: float
    inclusion_pct: float
    avg_confidence: float
    buckets: list[str]
    date_range: str


class StagingSummary(BaseModel):
    total: int
    promoted: int
    pending: int


class UnmatchedRow(BaseModel):
    staging_id: int
    name: str
    row_type: str
    has_alias: bool
    status: str


class LedgerSummaryResponse(BaseModel):
    ledger_rows: list[LedgerLabourHourRead]
    total_hours: float
    sred_hours: float
    person_count: int
    avg_confidence: float
    staging: StagingSummary
    person_breakdowns: list[PersonBreakdown]
    unmatched_rows: list[UnmatchedRow]
