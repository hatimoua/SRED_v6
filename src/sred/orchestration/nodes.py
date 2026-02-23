"""Deterministic context-lane nodes for LangGraph orchestration.

Each node follows the LangGraph convention: receives GraphState, returns a
partial state dict.  All five nodes are pure DB reads — no LLM calls.

Use ``make_nodes(session)`` to get a dict of node functions closed over a
SQLAlchemy Session, keeping nodes testable without FastAPI.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import func, text
from sqlmodel import Session, select

from sred.infra.db.repositories.run_repository import RunRepository
from sred.infra.db.repositories.file_repository import FileRepository
from sred.infra.db.repositories.person_repository import PersonRepository
from sred.infra.db.repositories.world_repository import WorldRepository
from sred.infra.db.repositories.finance_repository import FinanceRepository
from sred.infra.db.repositories.log_repository import LogRepository
from sred.models.alias import PersonAlias
from sred.models.core import FileStatus, Segment, File
from sred.models.finance import StagingStatus, StagingRowType
from sred.models.memory import MemoryDoc
from sred.models.world import ContradictionStatus, ReviewTaskStatus
from sred.orchestration.state import (
    ContextPacket,
    EvidenceItem,
    EvidencePack,
    GraphState,
    MemoryEntry,
    MemorySummaries,
    PeopleTimeAnchor,
    PersonAnchor,
    TokenBudget,
    ToolOutcome,
    WorldSnapshot,
)


def make_nodes(session: Session) -> dict[str, Callable]:
    """Return a dict of node functions closed over *session*.

    Each value is a ``def node(state: GraphState) -> dict`` callable
    suitable for use as a LangGraph node.
    """

    # ------------------------------------------------------------------
    # Node 1 — load_world_snapshot
    # ------------------------------------------------------------------
    def load_world_snapshot(state: GraphState) -> dict:
        run_id: int = state["run_id"]
        run_repo = RunRepository(session)
        file_repo = FileRepository(session)
        person_repo = PersonRepository(session)
        world_repo = WorldRepository(session)
        finance_repo = FinanceRepository(session)
        log_repo = LogRepository(session)

        run = run_repo.get_by_id(run_id)
        if run is None:
            # Missing run — return empty default snapshot
            packet = _current_packet(state)
            packet.world_snapshot = WorldSnapshot(run_id=run_id, run_status="UNKNOWN")
            return {"context_packet": packet.model_dump()}

        files = file_repo.get_by_run(run_id)
        files_processed = sum(1 for f in files if f.status == FileStatus.PROCESSED)

        contradictions = world_repo.list_contradictions(run_id)
        open_contradictions = sum(
            1 for c in contradictions if c.status == ContradictionStatus.OPEN
        )

        tasks = world_repo.list_tasks(run_id)
        open_tasks = sum(1 for t in tasks if t.status == ReviewTaskStatus.OPEN)

        locks = world_repo.list_locks(run_id)
        active_locks = sum(1 for lk in locks if lk.active)

        # Last 5 tool outcomes
        tool_logs = log_repo.list_tool_calls(run_id, limit=5)
        last_outcomes = [
            ToolOutcome(
                name=tl.tool_name,
                success=tl.success,
                summary=tl.result_json[:120] if tl.result_json else "",
                timestamp=tl.created_at,
            )
            for tl in tool_logs
        ]

        snapshot = WorldSnapshot(
            run_id=run_id,
            run_status=run.status.value if hasattr(run.status, "value") else str(run.status),
            file_count=len(files),
            files_processed=files_processed,
            people_count=person_repo.count_by_run(run_id),
            pending_rates=person_repo.count_pending_rates(run_id),
            open_contradictions=open_contradictions,
            open_tasks=open_tasks,
            active_locks=active_locks,
            staging_total=finance_repo.count_staging(run_id),
            staging_pending=finance_repo.count_staging_by_status(run_id, StagingStatus.PENDING),
            staging_promoted=finance_repo.count_staging_by_status(run_id, StagingStatus.PROMOTED),
            ledger_count=len(finance_repo.list_ledger_rows(run_id)),
            last_tool_outcomes=last_outcomes,
        )

        packet = _current_packet(state)
        packet.world_snapshot = snapshot
        return {"context_packet": packet.model_dump()}

    # ------------------------------------------------------------------
    # Node 2 — build_anchor_lane
    # ------------------------------------------------------------------
    def build_anchor_lane(state: GraphState) -> dict:
        run_id: int = state["run_id"]
        person_repo = PersonRepository(session)
        finance_repo = FinanceRepository(session)

        people = person_repo.list_by_run(run_id)
        # Sort by name for determinism
        people_sorted = sorted(people, key=lambda p: p.name)

        anchors = [
            PersonAnchor(
                person_id=p.id,
                name=p.name,
                role=p.role,
                hourly_rate=p.hourly_rate,
                rate_status=p.rate_status.value if hasattr(p.rate_status, "value") else str(p.rate_status),
            )
            for p in people_sorted
        ]

        confirmed_aliases = finance_repo.list_confirmed_aliases(run_id)
        alias_total = session.exec(
            select(func.count()).select_from(PersonAlias).where(PersonAlias.run_id == run_id)
        ).one()

        timesheet_rows = len(
            finance_repo.list_staging_rows(run_id, row_type=StagingRowType.TIMESHEET)
        )
        payroll_rows = len(
            finance_repo.list_staging_rows(run_id, row_type=StagingRowType.PAYROLL)
        )

        anchor_lane = PeopleTimeAnchor(
            people=anchors,
            alias_confirmed=len(confirmed_aliases),
            alias_total=alias_total,
            timesheet_staging_rows=timesheet_rows,
            payroll_staging_rows=payroll_rows,
        )

        packet = _current_packet(state)
        packet.people_time_anchor = anchor_lane
        return {"context_packet": packet.model_dump()}

    # ------------------------------------------------------------------
    # Node 3 — memory_retrieve
    # ------------------------------------------------------------------
    def memory_retrieve(state: GraphState) -> dict:
        run_id: int = state["run_id"]

        docs = list(
            session.exec(select(MemoryDoc).where(MemoryDoc.run_id == run_id)).all()
        )

        entries = [
            MemoryEntry(
                memory_id=doc.id,
                path=doc.path,
                snippet=doc.content_md[:200],
                content_hash=doc.content_hash,
            )
            for doc in docs
        ]

        packet = _current_packet(state)
        packet.memory_summaries = MemorySummaries(entries=entries)
        return {"context_packet": packet.model_dump()}

    # ------------------------------------------------------------------
    # Node 4 — retrieve_evidence_pack
    # ------------------------------------------------------------------
    def retrieve_evidence_pack(state: GraphState) -> dict:
        run_id: int = state["run_id"]
        user_message: str = state.get("user_message", "") or ""

        if not user_message.strip():
            packet = _current_packet(state)
            packet.evidence_pack = EvidencePack(
                items=[], query_used=None, retrieval_method="fts",
            )
            return {"context_packet": packet.model_dump()}

        # FTS search via raw SQL (same engine as session)
        fts_results = session.exec(
            text(
                "SELECT id, snippet(segment_fts, 1, '<b>', '</b>', '...', 64) "
                "FROM segment_fts "
                "WHERE segment_fts MATCH :query "
                "ORDER BY rank "
                "LIMIT :limit"
            ),
            params={"query": user_message, "limit": 10},
        ).all()

        items: list[EvidenceItem] = []
        for row in fts_results:
            seg_id = row[0]
            segment = session.get(Segment, seg_id)
            if segment is None:
                continue

            # Get provenance from segment + parent file
            file_obj = session.get(File, segment.file_id) if segment.file_id else None

            items.append(
                EvidenceItem(
                    segment_id=seg_id,
                    content=segment.content,
                    source_file_id=segment.source_file_id,
                    original_filename=file_obj.original_filename if file_obj else None,
                    page_number=segment.page_number,
                    row_number=segment.row_number,
                    score=row[1] if isinstance(row[1], (int, float)) else None,
                    source_type=file_obj.mime_type if file_obj else None,
                )
            )

        # Sort by FTS rank (items are already rank-ordered from SQL)
        packet = _current_packet(state)
        packet.evidence_pack = EvidencePack(
            items=items,
            query_used=user_message,
            retrieval_method="fts",
        )
        return {"context_packet": packet.model_dump()}

    # ------------------------------------------------------------------
    # Node 5 — context_compiler
    # ------------------------------------------------------------------
    def context_compiler(state: GraphState) -> dict:
        packet = _current_packet(state)
        budget = packet.token_budget

        # Trim world_snapshot — last_tool_outcomes
        if packet.world_snapshot and packet.world_snapshot.last_tool_outcomes:
            ws_json = packet.world_snapshot.model_dump_json()
            while _est_tokens(ws_json) > budget.world_snapshot and packet.world_snapshot.last_tool_outcomes:
                packet.world_snapshot.last_tool_outcomes.pop()
                ws_json = packet.world_snapshot.model_dump_json()

        # Trim anchor lane — truncate people list
        if packet.people_time_anchor and packet.people_time_anchor.people:
            pta_json = packet.people_time_anchor.model_dump_json()
            while _est_tokens(pta_json) > budget.people_time_anchor and packet.people_time_anchor.people:
                packet.people_time_anchor.people.pop()
                pta_json = packet.people_time_anchor.model_dump_json()

        # Trim memory summaries — remove from end
        if packet.memory_summaries and packet.memory_summaries.entries:
            ms_json = packet.memory_summaries.model_dump_json()
            while _est_tokens(ms_json) > budget.memory_summaries and packet.memory_summaries.entries:
                packet.memory_summaries.entries.pop()
                ms_json = packet.memory_summaries.model_dump_json()

        # Trim evidence pack — remove lowest-score items from end
        if packet.evidence_pack and packet.evidence_pack.items:
            ep_json = packet.evidence_pack.model_dump_json()
            while _est_tokens(ep_json) > budget.evidence_pack and packet.evidence_pack.items:
                packet.evidence_pack.items.pop()
                ep_json = packet.evidence_pack.model_dump_json()

        packet.compiled_at = datetime.now(timezone.utc)
        return {"context_packet": packet.model_dump()}

    return {
        "load_world_snapshot": load_world_snapshot,
        "build_anchor_lane": build_anchor_lane,
        "memory_retrieve": memory_retrieve,
        "retrieve_evidence_pack": retrieve_evidence_pack,
        "context_compiler": context_compiler,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _current_packet(state: GraphState) -> ContextPacket:
    """Reconstruct the ContextPacket from state, or create a fresh one."""
    raw = state.get("context_packet")
    if raw:
        return ContextPacket.model_validate(raw)
    return ContextPacket()


def _est_tokens(text: str) -> int:
    """Rough token estimate: chars / 4."""
    return len(text) // 4
