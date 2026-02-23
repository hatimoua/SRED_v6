"""Pure unit tests for orchestration state models — no DB, no OpenAI, no LangGraph."""

import json
from datetime import datetime, timezone

from sred.orchestration.state import (
    GRAPH_STATE_VERSION,
    ContextPacket,
    EvidenceItem,
    EvidencePack,
    MemoryEntry,
    MemorySummaries,
    PeopleTimeAnchor,
    PersonAnchor,
    TokenBudget,
    ToolOutcome,
    ToolRequest,
    WorldSnapshot,
    init_state,
    make_thread_id,
)


def _full_context_packet() -> ContextPacket:
    """Build a fully-populated ContextPacket for testing."""
    return ContextPacket(
        world_snapshot=WorldSnapshot(
            run_id=1,
            run_status="PROCESSING",
            file_count=5,
            files_processed=3,
            people_count=2,
            pending_rates=1,
            open_contradictions=1,
            open_tasks=2,
            active_locks=0,
            staging_total=10,
            staging_pending=4,
            staging_promoted=6,
            ledger_count=3,
            last_tool_outcomes=[
                ToolOutcome(
                    name="extract_timesheet",
                    success=True,
                    summary="ok",
                    timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                )
            ],
        ),
        people_time_anchor=PeopleTimeAnchor(
            people=[
                PersonAnchor(person_id=1, name="Alice", role="dev", hourly_rate=50.0, rate_status="CONFIRMED"),
            ],
            alias_confirmed=3,
            alias_total=5,
            timesheet_staging_rows=10,
            payroll_staging_rows=8,
        ),
        memory_summaries=MemorySummaries(
            entries=[
                MemoryEntry(memory_id=1, path="memory/summary.md", snippet="short", content_hash="abc123"),
            ]
        ),
        evidence_pack=EvidencePack(
            items=[
                EvidenceItem(
                    segment_id=42,
                    content="timesheet row",
                    source_file_id=7,
                    original_filename="ts.csv",
                    page_number=None,
                    row_number=3,
                    score=0.92,
                    source_type="timesheet",
                )
            ],
            query_used="hours for Alice",
            retrieval_method="hybrid",
        ),
        token_budget=TokenBudget(),
        compiled_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


class TestContextPacketRoundtrip:
    def test_serialization_roundtrip(self):
        """model_dump → model_validate produces identical packet."""
        packet = _full_context_packet()
        data = packet.model_dump()
        restored = ContextPacket.model_validate(data)
        assert restored == packet


class TestInitState:
    def test_all_keys_present(self):
        """init_state returns a dict with every GraphState key."""
        state = init_state(run_id=1, session_id="s1", user_message="hello")
        expected_keys = {
            "run_id", "session_id", "thread_id",
            "user_message", "messages",
            "context_packet",
            "tool_queue", "last_tool_result",
            "stop_reason", "is_blocked", "exit_requested", "errors",
            "step_count", "max_steps",
            "graph_state_version",
        }
        assert set(state.keys()) == expected_keys

    def test_thread_id_correct(self):
        state = init_state(run_id=42, session_id="abc", user_message="hi")
        assert state["thread_id"] == "42:abc"


class TestGraphStateJsonSerializable:
    def test_json_roundtrip(self):
        """GraphState with a full context_packet survives JSON roundtrip."""
        state = init_state(run_id=1, session_id="s1", user_message="go")
        state["context_packet"] = _full_context_packet().model_dump(mode="json")
        raw = json.dumps(state)
        loaded = json.loads(raw)
        assert loaded["run_id"] == 1
        assert loaded["context_packet"]["world_snapshot"]["run_id"] == 1


class TestMakeThreadId:
    def test_deterministic(self):
        assert make_thread_id(5, "xyz") == "5:xyz"
        assert make_thread_id(5, "xyz") == make_thread_id(5, "xyz")


class TestTokenBudget:
    def test_defaults(self):
        tb = TokenBudget()
        assert tb.world_snapshot == 800
        assert tb.people_time_anchor == 1200
        assert tb.memory_summaries == 1000
        assert tb.evidence_pack == 3000
        assert tb.total == 6000
        assert tb.total == tb.world_snapshot + tb.people_time_anchor + tb.memory_summaries + tb.evidence_pack


class TestContextPacketPartial:
    def test_none_lanes_survive_roundtrip(self):
        packet = ContextPacket()  # all lanes None
        data = packet.model_dump()
        restored = ContextPacket.model_validate(data)
        assert restored.world_snapshot is None
        assert restored.people_time_anchor is None
        assert restored.memory_summaries is None
        assert restored.evidence_pack is None


class TestEvidenceItemProvenance:
    def test_all_fields_survive_serialization(self):
        item = EvidenceItem(
            segment_id=10,
            content="data",
            source_file_id=3,
            original_filename="inv.pdf",
            page_number=2,
            row_number=None,
            score=0.85,
            source_type="invoice",
        )
        data = item.model_dump()
        restored = EvidenceItem.model_validate(data)
        assert restored.segment_id == 10
        assert restored.source_file_id == 3
        assert restored.original_filename == "inv.pdf"
        assert restored.page_number == 2
        assert restored.row_number is None
        assert restored.score == 0.85
        assert restored.source_type == "invoice"


class TestGraphStateVersion:
    def test_is_int_gte_1(self):
        assert isinstance(GRAPH_STATE_VERSION, int)
        assert GRAPH_STATE_VERSION >= 1
