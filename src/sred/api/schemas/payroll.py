"""Payroll DTOs — pure Pydantic, zero ORM imports."""
from __future__ import annotations
from datetime import date
from pydantic import BaseModel
from sred.api.schemas.tasks import ContradictionRead


class PayrollExtractRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    run_id: int
    file_id: int
    period_start: date
    period_end: date
    total_hours: float | None = None
    total_wages: float | None = None
    currency: str
    employee_count: int | None = None
    confidence: float


class PayrollExtractList(BaseModel):
    items: list[PayrollExtractRead]
    total: int


class MismatchRow(BaseModel):
    period: str
    payroll_hours: str
    timesheet_hours: str
    mismatch_pct: str
    status: str


class PayrollValidationResponse(BaseModel):
    extracts: list[PayrollExtractRead]
    mismatches: list[MismatchRow]
    payroll_total: float
    timesheet_total: float
    overall_mismatch_pct: float
    threshold_pct: float
    contradictions: list[ContradictionRead]
