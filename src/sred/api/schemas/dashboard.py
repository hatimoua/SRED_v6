"""Dashboard DTOs — pure Pydantic, zero ORM imports."""
from __future__ import annotations
from pydantic import BaseModel


class DashboardSummary(BaseModel):
    run_status: str
    person_count: int
    pending_rates: int
    file_count: int
