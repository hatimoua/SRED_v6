"""Tests for Phase 4.3 — deterministic context-lane nodes.

Seeds a Run + Files + People + Contradictions + Tasks + Locks + StagingRows +
MemoryDocs + Segments (with FTS index) and verifies each node independently.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlmodel import Session

from sred.models.agent_log import ToolCallLog
from sred.models.alias import AliasStatus, PersonAlias
from sred.models.core import File, FileStatus, Person, RateStatus, Run, RunStatus, Segment
from sred.models.finance import (
    LedgerLabourHour,
    StagingRow,
    StagingRowType,
    StagingStatus,
)
from sred.models.memory import MemoryDoc
from sred.models.world import (
    Contradiction,
    ContradictionSeverity,
    ContradictionStatus,
    ContradictionType,
    DecisionLock,
    ReviewDecision,
    ReviewTask,
    ReviewTaskStatus,
)
from sred.orchestration.nodes import make_nodes
from sred.orchestration.state import (
    ContextPacket,
    EvidencePack,
    MemorySummaries,
    PeopleTimeAnchor,
    TokenBudget,
    WorldSnapshot,
    init_state,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha(val: str) -> str:
    return hashlib.sha256(val.encode()).hexdigest()


def _seed_run(session: Session, *, name: str = "Test Run") -> Run:
    run = Run(name=name, status=RunStatus.PROCESSING)
    session.add(run)
    session.flush()
    return run


def _seed_file(session: Session, run_id: int, *, filename: str = "test.csv", status: FileStatus = FileStatus.PROCESSED) -> File:
    f = File(
        run_id=run_id,
        path=f"data/runs/{run_id}/uploads/{filename}",
        original_filename=filename,
        file_type="text/csv",
        mime_type="text/csv",
        size_bytes=100,
        content_hash=_sha(filename),
        status=status,
    )
    session.add(f)
    session.flush()
    return f


def _seed_person(session: Session, run_id: int, *, name: str, role: str = "Dev", rate: float | None = None) -> Person:
    p = Person(
        run_id=run_id,
        name=name,
        role=role,
        hourly_rate=rate,
        rate_status=RateStatus.SET if rate else RateStatus.PENDING,
    )
    session.add(p)
    session.flush()
    return p


def _seed_segment(session: Session, run_id: int, file_id: int, content: str, *, page: int | None = None, row: int | None = None) -> Segment:
    seg = Segment(
        run_id=run_id,
        file_id=file_id,
        content=content,
        source_file_id=file_id,
        page_number=page,
        row_number=row,
    )
    session.add(seg)
    session.flush()
    # Index into FTS
    session.exec(
        text(
            "INSERT INTO segment_fts(rowid, id, content) VALUES (:rid, :sid, :content)"
        ),
        params={"rid": seg.id, "sid": seg.id, "content": content},
    )
    session.flush()
    return seg


def _seed_contradiction(session: Session, run_id: int, *, status: ContradictionStatus = ContradictionStatus.OPEN) -> Contradiction:
    c = Contradiction(
        run_id=run_id,
        issue_key=f"TEST:{_sha(str(run_id) + str(status))[:8]}",
        contradiction_type=ContradictionType.MISSING_RATE,
        severity=ContradictionSeverity.MEDIUM,
        description="test contradiction",
        status=status,
    )
    session.add(c)
    session.flush()
    return c


def _seed_task(session: Session, run_id: int, *, status: ReviewTaskStatus = ReviewTaskStatus.OPEN) -> ReviewTask:
    t = ReviewTask(
        run_id=run_id,
        issue_key=f"TASK:{_sha(str(run_id) + str(status))[:8]}",
        title="test task",
        description="test task description",
        status=status,
    )
    session.add(t)
    session.flush()
    return t


def _seed_lock(session: Session, run_id: int, *, active: bool = True) -> DecisionLock:
    # Need a task + decision first
    task = _seed_task(session, run_id, status=ReviewTaskStatus.RESOLVED)
    decision = ReviewDecision(run_id=run_id, task_id=task.id, decision="approved")
    session.add(decision)
    session.flush()
    lock = DecisionLock(
        run_id=run_id,
        issue_key=task.issue_key,
        decision_id=decision.id,
        reason="locked",
        active=active,
    )
    session.add(lock)
    session.flush()
    return lock


def _seed_staging(session: Session, run_id: int, *, row_type: StagingRowType = StagingRowType.TIMESHEET, status: StagingStatus = StagingStatus.PENDING) -> StagingRow:
    row = StagingRow(
        run_id=run_id,
        raw_data="{}",
        status=status,
        row_type=row_type,
        row_hash=_sha(f"{run_id}-{row_type}-{status}"),
        normalized_text="staging row text",
    )
    session.add(row)
    session.flush()
    return row


def _seed_ledger(session: Session, run_id: int) -> LedgerLabourHour:
    row = LedgerLabourHour(
        run_id=run_id, person_id=None, date=date(2025, 1, 1), hours=8.0,
    )
    session.add(row)
    session.flush()
    return row


def _seed_tool_call(session: Session, run_id: int, *, tool_name: str = "test_tool", success: bool = True) -> ToolCallLog:
    tc = ToolCallLog(
        run_id=run_id,
        tool_name=tool_name,
        arguments_json="{}",
        result_json='{"ok": true}',
        success=success,
        duration_ms=50,
    )
    session.add(tc)
    session.flush()
    return tc


def _seed_memory(session: Session, run_id: int, *, path: str = "memory/summary.md", content: str = "This is a memory doc.") -> MemoryDoc:
    doc = MemoryDoc(
        run_id=run_id,
        path=path,
        content_md=content,
        content_hash=_sha(content),
    )
    session.add(doc)
    session.flush()
    return doc


def _seed_alias(session: Session, run_id: int, person_id: int, *, alias: str, status: AliasStatus = AliasStatus.CONFIRMED) -> PersonAlias:
    a = PersonAlias(
        run_id=run_id,
        person_id=person_id,
        alias=alias,
        status=status,
        confidence=0.95,
    )
    session.add(a)
    session.flush()
    return a


# ---------------------------------------------------------------------------
# Tests — Node 1: load_world_snapshot
# ---------------------------------------------------------------------------


def test_load_world_snapshot_counts(use_test_engine):
    with Session(use_test_engine) as session:
        run = _seed_run(session)
        _seed_file(session, run.id, filename="a.csv", status=FileStatus.PROCESSED)
        _seed_file(session, run.id, filename="b.csv", status=FileStatus.UPLOADED)
        _seed_person(session, run.id, name="Alice", rate=50.0)
        _seed_person(session, run.id, name="Bob")  # pending rate
        _seed_contradiction(session, run.id, status=ContradictionStatus.OPEN)
        _seed_contradiction(session, run.id, status=ContradictionStatus.RESOLVED)
        _seed_task(session, run.id, status=ReviewTaskStatus.OPEN)
        _seed_lock(session, run.id, active=True)
        _seed_lock(session, run.id, active=False)
        _seed_staging(session, run.id, row_type=StagingRowType.TIMESHEET, status=StagingStatus.PENDING)
        _seed_staging(session, run.id, row_type=StagingRowType.PAYROLL, status=StagingStatus.PROMOTED)
        _seed_ledger(session, run.id)
        _seed_tool_call(session, run.id, tool_name="ingest_file")
        _seed_tool_call(session, run.id, tool_name="validate_data")
        session.commit()

        nodes = make_nodes(session)
        state = init_state(run.id, "s1", "hello")
        result = nodes["load_world_snapshot"](state)

        packet = ContextPacket.model_validate(result["context_packet"])
        ws = packet.world_snapshot
        assert ws is not None
        assert ws.run_id == run.id
        assert ws.run_status == "PROCESSING"
        assert ws.file_count == 2
        assert ws.files_processed == 1
        assert ws.people_count == 2
        assert ws.pending_rates == 1
        assert ws.open_contradictions == 1
        assert ws.open_tasks == 1
        assert ws.active_locks == 1
        assert ws.staging_total == 2
        assert ws.staging_pending == 1
        assert ws.staging_promoted == 1
        assert ws.ledger_count == 1
        assert len(ws.last_tool_outcomes) == 2


def test_load_world_snapshot_missing_run(use_test_engine):
    with Session(use_test_engine) as session:
        nodes = make_nodes(session)
        state = init_state(9999, "s1", "hello")
        result = nodes["load_world_snapshot"](state)

        packet = ContextPacket.model_validate(result["context_packet"])
        ws = packet.world_snapshot
        assert ws is not None
        assert ws.run_id == 9999
        assert ws.run_status == "UNKNOWN"
        assert ws.file_count == 0


# ---------------------------------------------------------------------------
# Tests — Node 2: build_anchor_lane
# ---------------------------------------------------------------------------


def test_build_anchor_lane_deterministic(use_test_engine):
    with Session(use_test_engine) as session:
        run = _seed_run(session)
        p_charlie = _seed_person(session, run.id, name="Charlie", rate=60.0)
        p_alice = _seed_person(session, run.id, name="Alice", rate=50.0)
        p_bob = _seed_person(session, run.id, name="Bob")
        _seed_alias(session, run.id, p_alice.id, alias="A. Smith", status=AliasStatus.CONFIRMED)
        _seed_alias(session, run.id, p_bob.id, alias="Robert", status=AliasStatus.PROPOSED)
        _seed_staging(session, run.id, row_type=StagingRowType.TIMESHEET, status=StagingStatus.PENDING)
        _seed_staging(session, run.id, row_type=StagingRowType.PAYROLL, status=StagingStatus.PENDING)
        session.commit()

        nodes = make_nodes(session)
        state = init_state(run.id, "s1", "hello")
        result = nodes["build_anchor_lane"](state)

        packet = ContextPacket.model_validate(result["context_packet"])
        pta = packet.people_time_anchor
        assert pta is not None
        assert len(pta.people) == 3
        # Sorted by name: Alice, Bob, Charlie
        assert pta.people[0].name == "Alice"
        assert pta.people[1].name == "Bob"
        assert pta.people[2].name == "Charlie"
        assert pta.people[0].hourly_rate == 50.0
        assert pta.people[2].hourly_rate == 60.0
        assert pta.alias_confirmed == 1
        assert pta.alias_total == 2
        assert pta.timesheet_staging_rows == 1
        assert pta.payroll_staging_rows == 1


def test_build_anchor_lane_empty(use_test_engine):
    with Session(use_test_engine) as session:
        run = _seed_run(session)
        session.commit()

        nodes = make_nodes(session)
        state = init_state(run.id, "s1", "hello")
        result = nodes["build_anchor_lane"](state)

        packet = ContextPacket.model_validate(result["context_packet"])
        pta = packet.people_time_anchor
        assert pta is not None
        assert pta.people == []
        assert pta.alias_total == 0


# ---------------------------------------------------------------------------
# Tests — Node 3: memory_retrieve
# ---------------------------------------------------------------------------


def test_memory_retrieve_returns_entries(use_test_engine):
    with Session(use_test_engine) as session:
        run = _seed_run(session)
        _seed_memory(session, run.id, path="memory/summary.md", content="Summary of the project goals and milestones.")
        _seed_memory(session, run.id, path="memory/decisions.md", content="Key decisions made during the review process.")
        session.commit()

        nodes = make_nodes(session)
        state = init_state(run.id, "s1", "hello")
        result = nodes["memory_retrieve"](state)

        packet = ContextPacket.model_validate(result["context_packet"])
        ms = packet.memory_summaries
        assert ms is not None
        assert len(ms.entries) == 2
        assert ms.entries[0].path in ("memory/summary.md", "memory/decisions.md")
        assert len(ms.entries[0].snippet) <= 200


def test_memory_retrieve_empty(use_test_engine):
    with Session(use_test_engine) as session:
        run = _seed_run(session)
        session.commit()

        nodes = make_nodes(session)
        state = init_state(run.id, "s1", "hello")
        result = nodes["memory_retrieve"](state)

        packet = ContextPacket.model_validate(result["context_packet"])
        ms = packet.memory_summaries
        assert ms is not None
        assert ms.entries == []


# ---------------------------------------------------------------------------
# Tests — Node 4: retrieve_evidence_pack
# ---------------------------------------------------------------------------


def test_evidence_pack_provenance(use_test_engine):
    with Session(use_test_engine) as session:
        run = _seed_run(session)
        f = _seed_file(session, run.id, filename="timesheet.csv")
        _seed_segment(session, run.id, f.id, "Alice worked 40 hours on project alpha", page=1, row=5)
        _seed_segment(session, run.id, f.id, "Bob worked 35 hours on project beta", page=2, row=10)
        session.commit()

        nodes = make_nodes(session)
        state = init_state(run.id, "s1", "hours worked project")
        result = nodes["retrieve_evidence_pack"](state)

        packet = ContextPacket.model_validate(result["context_packet"])
        ep = packet.evidence_pack
        assert ep is not None
        assert ep.retrieval_method == "fts"
        assert ep.query_used == "hours worked project"
        assert len(ep.items) > 0
        for item in ep.items:
            assert item.segment_id is not None
            assert item.source_file_id is not None
            assert item.original_filename == "timesheet.csv"
            assert item.page_number is not None
            assert item.row_number is not None


def test_evidence_pack_empty_query(use_test_engine):
    with Session(use_test_engine) as session:
        run = _seed_run(session)
        session.commit()

        nodes = make_nodes(session)
        state = init_state(run.id, "s1", "")
        result = nodes["retrieve_evidence_pack"](state)

        packet = ContextPacket.model_validate(result["context_packet"])
        ep = packet.evidence_pack
        assert ep is not None
        assert ep.items == []
        assert ep.retrieval_method == "fts"


# ---------------------------------------------------------------------------
# Tests — Node 5: context_compiler
# ---------------------------------------------------------------------------


def test_context_compiler_token_trimming_evidence(use_test_engine):
    with Session(use_test_engine) as session:
        nodes = make_nodes(session)

        # Build a packet with many large evidence items
        big_items = [
            {
                "segment_id": i,
                "content": "x" * 2000,
                "source_file_id": 1,
                "original_filename": "test.csv",
                "page_number": 1,
                "row_number": i,
                "score": 10.0 - i,
                "source_type": "text/csv",
            }
            for i in range(20)
        ]
        packet = ContextPacket(
            evidence_pack=EvidencePack(items=big_items, query_used="test", retrieval_method="fts"),
            token_budget=TokenBudget(evidence_pack=500),
        )
        state = init_state(1, "s1", "test")
        state["context_packet"] = packet.model_dump()

        result = nodes["context_compiler"](state)
        compiled = ContextPacket.model_validate(result["context_packet"])
        assert compiled.evidence_pack is not None
        assert len(compiled.evidence_pack.items) < 20


def test_context_compiler_token_trimming_memory(use_test_engine):
    with Session(use_test_engine) as session:
        nodes = make_nodes(session)

        big_entries = [
            {
                "memory_id": i,
                "path": f"memory/doc{i}.md",
                "snippet": "y" * 1500,
                "content_hash": _sha(str(i)),
            }
            for i in range(20)
        ]
        packet = ContextPacket(
            memory_summaries=MemorySummaries(entries=big_entries),
            token_budget=TokenBudget(memory_summaries=500),
        )
        state = init_state(1, "s1", "test")
        state["context_packet"] = packet.model_dump()

        result = nodes["context_compiler"](state)
        compiled = ContextPacket.model_validate(result["context_packet"])
        assert compiled.memory_summaries is not None
        assert len(compiled.memory_summaries.entries) < 20


def test_context_compiler_token_trimming_people(use_test_engine):
    with Session(use_test_engine) as session:
        nodes = make_nodes(session)

        big_people = [
            {
                "person_id": i,
                "name": f"Person {i} with a very long name " * 10,
                "role": "Developer",
                "hourly_rate": 50.0,
                "rate_status": "SET",
            }
            for i in range(50)
        ]
        packet = ContextPacket(
            people_time_anchor=PeopleTimeAnchor(people=big_people),
            token_budget=TokenBudget(people_time_anchor=200),
        )
        state = init_state(1, "s1", "test")
        state["context_packet"] = packet.model_dump()

        result = nodes["context_compiler"](state)
        compiled = ContextPacket.model_validate(result["context_packet"])
        assert compiled.people_time_anchor is not None
        assert len(compiled.people_time_anchor.people) < 50


def test_context_compiler_sets_compiled_at(use_test_engine):
    with Session(use_test_engine) as session:
        nodes = make_nodes(session)

        packet = ContextPacket()
        state = init_state(1, "s1", "test")
        state["context_packet"] = packet.model_dump()

        before = datetime.now(timezone.utc)
        result = nodes["context_compiler"](state)
        after = datetime.now(timezone.utc)

        compiled = ContextPacket.model_validate(result["context_packet"])
        assert compiled.compiled_at is not None
        assert before <= compiled.compiled_at <= after


def test_context_compiler_preserves_within_budget(use_test_engine):
    with Session(use_test_engine) as session:
        nodes = make_nodes(session)

        # Small data well within default budget
        packet = ContextPacket(
            world_snapshot=WorldSnapshot(run_id=1, run_status="PROCESSING"),
            people_time_anchor=PeopleTimeAnchor(
                people=[{"person_id": 1, "name": "Alice", "role": "Dev", "hourly_rate": 50.0, "rate_status": "SET"}],
            ),
            memory_summaries=MemorySummaries(
                entries=[{"memory_id": 1, "path": "m.md", "snippet": "short", "content_hash": "abc"}],
            ),
            evidence_pack=EvidencePack(
                items=[{"segment_id": 1, "content": "small content", "source_file_id": 1}],
                query_used="test",
                retrieval_method="fts",
            ),
        )
        state = init_state(1, "s1", "test")
        state["context_packet"] = packet.model_dump()

        result = nodes["context_compiler"](state)
        compiled = ContextPacket.model_validate(result["context_packet"])

        # Nothing trimmed
        assert len(compiled.people_time_anchor.people) == 1
        assert len(compiled.memory_summaries.entries) == 1
        assert len(compiled.evidence_pack.items) == 1
        assert compiled.compiled_at is not None
