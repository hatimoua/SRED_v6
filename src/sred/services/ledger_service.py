"""Ledger use-case service."""
from __future__ import annotations
import json
from sred.domain.exceptions import NotFoundError
from sred.infra.db.uow import UnitOfWork
from sred.infra.db.repositories.run_repository import RunRepository
from sred.infra.db.repositories.finance_repository import FinanceRepository
from sred.api.schemas.ledger import (
    LedgerLabourHourRead, LedgerSummaryResponse,
    PersonBreakdown, StagingSummary, UnmatchedRow,
)
from sred.models.finance import StagingStatus


class LedgerService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def _ensure_run(self, run_id: int) -> None:
        if RunRepository(self._uow.session).get_by_id(run_id) is None:
            raise NotFoundError(f"Run {run_id} not found")

    def get_summary(self, run_id: int) -> LedgerSummaryResponse:
        self._ensure_run(run_id)
        fin = FinanceRepository(self._uow.session)

        ledger_rows = fin.list_ledger_rows(run_id)
        staging_total = fin.count_staging(run_id)
        staging_promoted = fin.count_staging_by_status(run_id, StagingStatus.PROMOTED)
        staging_pending = fin.count_staging_by_status(run_id, StagingStatus.PENDING)

        # Aggregate stats
        total_hours = sum(r.hours for r in ledger_rows) if ledger_rows else 0.0
        sred_rows = [r for r in ledger_rows if r.bucket == "SR&ED"]
        sred_hours = sum(r.hours * r.inclusion_fraction for r in sred_rows) if sred_rows else 0.0
        person_ids = set(r.person_id for r in ledger_rows if r.person_id)
        confidences = [r.confidence for r in ledger_rows if r.confidence is not None]
        avg_confidence = sum(confidences) / max(len(confidences), 1) if confidences else 0.0

        # Person breakdown
        persons = fin.list_persons(run_id)
        person_map = {p.id: p for p in persons}

        by_person: dict[int, list] = {}
        for r in ledger_rows:
            pid = r.person_id or 0
            by_person.setdefault(pid, []).append(r)

        breakdowns: list[PersonBreakdown] = []
        for pid, rows in sorted(by_person.items(), key=lambda x: x[0]):
            person = person_map.get(pid)
            p_hours = sum(r.hours for r in rows)
            p_sred = sum(r.hours * r.inclusion_fraction for r in rows if r.bucket == "SR&ED")
            p_incl = p_sred / p_hours if p_hours > 0 else 0.0
            p_confs = [r.confidence for r in rows if r.confidence]
            p_conf = sum(p_confs) / max(len(p_confs), 1) if p_confs else 0.0
            dates = sorted(set(str(r.date) for r in rows))
            date_range = f"{dates[0]} \u2192 {dates[-1]}" if len(dates) > 1 else dates[0] if dates else "\u2014"
            buckets = sorted(set(r.bucket for r in rows))

            breakdowns.append(PersonBreakdown(
                person_name=person.name if person else f"Unknown (ID {pid})",
                role=person.role if person else "\u2014",
                total_hours=p_hours,
                sred_hours=p_sred,
                inclusion_pct=p_incl,
                avg_confidence=p_conf,
                buckets=buckets,
                date_range=date_range,
            ))

        # Unmatched staging rows
        pending_rows = fin.list_staging_rows(run_id, status=StagingStatus.PENDING)
        confirmed_aliases = fin.list_confirmed_aliases(run_id)
        confirmed_names = {a.alias.strip().lower() for a in confirmed_aliases}

        unmatched: list[UnmatchedRow] = []
        for sr in pending_rows:
            try:
                row = json.loads(sr.raw_data)
            except json.JSONDecodeError:
                row = {}
            name = None
            for col in ["Employee", "employee", "Name", "name", "Full Name"]:
                if col in row:
                    name = str(row[col]).strip()
                    break
            has_alias = name.lower() in confirmed_names if name else False
            unmatched.append(UnmatchedRow(
                staging_id=sr.id,
                name=name or "\u2014",
                row_type=sr.row_type.value,
                has_alias=has_alias,
                status=sr.status.value,
            ))

        return LedgerSummaryResponse(
            ledger_rows=[LedgerLabourHourRead.model_validate(r) for r in ledger_rows],
            total_hours=total_hours,
            sred_hours=sred_hours,
            person_count=len(person_ids),
            avg_confidence=avg_confidence,
            staging=StagingSummary(total=staging_total, promoted=staging_promoted, pending=staging_pending),
            person_breakdowns=breakdowns,
            unmatched_rows=unmatched,
        )
