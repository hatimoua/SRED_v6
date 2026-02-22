"""Repository for finance entities (payroll, staging, ledger)."""
from __future__ import annotations
import json
from sqlalchemy import func
from sqlmodel import Session, select
from sred.models.finance import (
    PayrollExtract, StagingRow, StagingStatus, StagingRowType, LedgerLabourHour,
)
from sred.models.core import Person
from sred.models.alias import PersonAlias, AliasStatus


class FinanceRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    # --- PayrollExtract ---

    def list_payroll_extracts(self, run_id: int) -> list[PayrollExtract]:
        return list(self._s.exec(
            select(PayrollExtract).where(PayrollExtract.run_id == run_id)
        ).all())

    # --- StagingRow ---

    def list_staging_rows(
        self, run_id: int, *, row_type: StagingRowType | None = None, status: StagingStatus | None = None,
    ) -> list[StagingRow]:
        stmt = select(StagingRow).where(StagingRow.run_id == run_id)
        if row_type:
            stmt = stmt.where(StagingRow.row_type == row_type)
        if status:
            stmt = stmt.where(StagingRow.status == status)
        return list(self._s.exec(stmt).all())

    def count_staging(self, run_id: int) -> int:
        return self._s.exec(
            select(func.count()).select_from(StagingRow).where(StagingRow.run_id == run_id)
        ).one()

    def count_staging_by_status(self, run_id: int, status: StagingStatus) -> int:
        return self._s.exec(
            select(func.count()).select_from(StagingRow).where(
                StagingRow.run_id == run_id, StagingRow.status == status,
            )
        ).one()

    # --- LedgerLabourHour ---

    def list_ledger_rows(self, run_id: int) -> list[LedgerLabourHour]:
        return list(self._s.exec(
            select(LedgerLabourHour).where(LedgerLabourHour.run_id == run_id)
        ).all())

    # --- Person + Alias (read helpers for ledger) ---

    def list_persons(self, run_id: int) -> list[Person]:
        return list(self._s.exec(
            select(Person).where(Person.run_id == run_id)
        ).all())

    def list_confirmed_aliases(self, run_id: int) -> list[PersonAlias]:
        return list(self._s.exec(
            select(PersonAlias).where(
                PersonAlias.run_id == run_id,
                PersonAlias.status == AliasStatus.CONFIRMED,
            )
        ).all())
