"""Payroll validation use-case service."""
from __future__ import annotations
import json
from datetime import date as date_type
from sred.domain.exceptions import NotFoundError
from sred.infra.db.uow import UnitOfWork
from sred.infra.db.repositories.run_repository import RunRepository
from sred.infra.db.repositories.finance_repository import FinanceRepository
from sred.infra.db.repositories.world_repository import WorldRepository
from sred.api.schemas.payroll import (
    PayrollExtractRead, PayrollExtractList, MismatchRow, PayrollValidationResponse,
)
from sred.api.schemas.tasks import ContradictionRead
from sred.models.finance import StagingRowType
from sred.models.world import ContradictionType
from sred.config import settings


class PayrollService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def _ensure_run(self, run_id: int) -> None:
        if RunRepository(self._uow.session).get_by_id(run_id) is None:
            raise NotFoundError(f"Run {run_id} not found")

    def get_validation(self, run_id: int) -> PayrollValidationResponse:
        self._ensure_run(run_id)
        fin = FinanceRepository(self._uow.session)
        world = WorldRepository(self._uow.session)

        extracts = fin.list_payroll_extracts(run_id)
        ts_rows = fin.list_staging_rows(run_id, row_type=StagingRowType.TIMESHEET)
        threshold = settings.PAYROLL_MISMATCH_THRESHOLD

        # Sum timesheet hours by date
        ts_hours_by_date: dict[str, float] = {}
        ts_total = 0.0
        for sr in ts_rows:
            try:
                row_dict = json.loads(sr.raw_data)
            except json.JSONDecodeError:
                continue
            h = row_dict.get("hours")
            d = row_dict.get("date")
            if h is not None:
                try:
                    hours_val = float(h)
                except (ValueError, TypeError):
                    continue
                ts_total += hours_val
                if d:
                    ts_hours_by_date[str(d)] = ts_hours_by_date.get(str(d), 0.0) + hours_val

        # Build mismatch rows
        mismatches: list[MismatchRow] = []
        payroll_total = 0.0

        for pe in extracts:
            if pe.total_hours is None:
                mismatches.append(MismatchRow(
                    period=f"{pe.period_start} \u2192 {pe.period_end}",
                    payroll_hours="N/A", timesheet_hours="N/A",
                    mismatch_pct="N/A", status="No hours data",
                ))
                continue

            payroll_total += pe.total_hours
            period_ts = 0.0
            for date_str, hrs in ts_hours_by_date.items():
                try:
                    d = date_type.fromisoformat(date_str)
                except ValueError:
                    continue
                if pe.period_start <= d <= pe.period_end:
                    period_ts += hrs

            if pe.total_hours == 0 and period_ts == 0:
                mismatch = 0.0
            elif pe.total_hours == 0:
                mismatch = 1.0
            else:
                mismatch = abs(pe.total_hours - period_ts) / pe.total_hours

            is_blocking = mismatch > threshold
            mismatches.append(MismatchRow(
                period=f"{pe.period_start} \u2192 {pe.period_end}",
                payroll_hours=f"{pe.total_hours:.1f}",
                timesheet_hours=f"{period_ts:.1f}",
                mismatch_pct=f"{mismatch * 100:.1f}%",
                status="BLOCKING" if is_blocking else "OK",
            ))

        # Overall mismatch
        if payroll_total == 0 and ts_total == 0:
            overall = 0.0
        elif payroll_total == 0:
            overall = 1.0
        else:
            overall = abs(payroll_total - ts_total) / payroll_total

        # Contradictions
        contradictions = world.list_contradictions_by_type(run_id, ContradictionType.PAYROLL_MISMATCH)

        return PayrollValidationResponse(
            extracts=[PayrollExtractRead.model_validate(e) for e in extracts],
            mismatches=mismatches,
            payroll_total=payroll_total,
            timesheet_total=ts_total,
            overall_mismatch_pct=overall * 100,
            threshold_pct=threshold * 100,
            contradictions=[
                ContradictionRead.model_validate(c).model_dump() for c in contradictions
            ],
        )
