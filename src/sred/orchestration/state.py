"""GraphState and ContextPacket definitions for LangGraph orchestration.

GraphState is a TypedDict (LangGraph-native). ContextPacket lanes are
Pydantic BaseModels for validation; stored in state as plain dicts via
.model_dump() and reconstructed with .model_validate() inside nodes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TypedDict

from pydantic import BaseModel, Field, model_validator

GRAPH_STATE_VERSION: int = 1

# ---------------------------------------------------------------------------
# ContextPacket lane sub-models (Pydantic)
# ---------------------------------------------------------------------------


class ToolOutcome(BaseModel):
    name: str
    success: bool
    summary: str
    timestamp: datetime


# Lane 1 — WorldSnapshot (DB truth)
class WorldSnapshot(BaseModel):
    run_id: int
    run_status: str
    file_count: int = 0
    files_processed: int = 0
    people_count: int = 0
    pending_rates: int = 0
    open_contradictions: int = 0
    open_tasks: int = 0
    active_locks: int = 0
    staging_total: int = 0
    staging_pending: int = 0
    staging_promoted: int = 0
    ledger_count: int = 0
    last_tool_outcomes: list[ToolOutcome] = Field(default_factory=list)


# Lane 2 — PeopleTimeAnchor (always-on facts)
class PersonAnchor(BaseModel):
    person_id: int
    name: str
    role: str | None = None
    hourly_rate: float | None = None
    rate_status: str | None = None


class PeopleTimeAnchor(BaseModel):
    people: list[PersonAnchor] = Field(default_factory=list)
    alias_confirmed: int = 0
    alias_total: int = 0
    timesheet_staging_rows: int = 0
    payroll_staging_rows: int = 0


# Lane 3 — MemorySummaries
class MemoryEntry(BaseModel):
    memory_id: int
    path: str
    snippet: str
    content_hash: str


class MemorySummaries(BaseModel):
    entries: list[MemoryEntry] = Field(default_factory=list)


# Lane 4 — EvidencePack
class EvidenceItem(BaseModel):
    segment_id: int
    content: str
    source_file_id: int | None = None
    original_filename: str | None = None
    page_number: int | None = None
    row_number: int | None = None
    score: float | None = None
    source_type: str | None = None


class EvidencePack(BaseModel):
    items: list[EvidenceItem] = Field(default_factory=list)
    query_used: str | None = None
    retrieval_method: str | None = None


# Token budget
class TokenBudget(BaseModel):
    world_snapshot: int = 800
    people_time_anchor: int = 1200
    memory_summaries: int = 1000
    evidence_pack: int = 3000
    total: int = 6000


# Combined ContextPacket
class ContextPacket(BaseModel):
    world_snapshot: WorldSnapshot | None = None
    people_time_anchor: PeopleTimeAnchor | None = None
    memory_summaries: MemorySummaries | None = None
    evidence_pack: EvidencePack | None = None
    token_budget: TokenBudget = Field(default_factory=TokenBudget)
    compiled_at: datetime | None = None


# ---------------------------------------------------------------------------
# ToolRequest (for tool_queue)
# ---------------------------------------------------------------------------


class ToolRequest(BaseModel):
    tool_name: str
    arguments: dict = Field(default_factory=dict)
    idempotency_key: str | None = None


# ---------------------------------------------------------------------------
# PlannerDecision (structured output from planner LLM call)
# ---------------------------------------------------------------------------


class PlannerDecision(BaseModel):
    """Schema-validated output from the planner node's LLM call.

    Invariants enforced by ``validate_consistency``:
    - ``done=True`` → must have ``stop_reason`` + ``draft_response``, no ``tool_requests``
    - ``done=False`` → must have ≥1 ``tool_requests``
    """

    done: bool
    stop_reason: str | None = None
    draft_response: str | None = None
    tool_requests: list[ToolRequest] = Field(default_factory=list)
    reasoning: str = ""

    @model_validator(mode="after")
    def validate_consistency(self) -> PlannerDecision:
        if self.done:
            if not self.stop_reason:
                raise ValueError("done=True requires stop_reason")
            if not self.draft_response:
                raise ValueError("done=True requires draft_response")
            if self.tool_requests:
                raise ValueError("done=True must not have tool_requests")
        else:
            if not self.tool_requests:
                raise ValueError("done=False requires at least one tool_request")
        return self


# ---------------------------------------------------------------------------
# GraphState (TypedDict — LangGraph native)
# ---------------------------------------------------------------------------


class GraphState(TypedDict, total=False):
    # Identity
    run_id: int
    session_id: str
    thread_id: str
    # Conversation
    user_message: str
    messages: list[dict]
    # Context
    context_packet: dict  # ContextPacket.model_dump()
    # Tool execution
    tool_queue: list[dict]  # list of ToolRequest dicts
    last_tool_result: dict
    # Gate + review payloads
    gate_snapshot: dict
    needs_review_payload: dict
    # Control flow
    stop_reason: str  # "complete"|"max_steps"|"blocked"|"error"|""
    is_blocked: bool
    errors: list[str]
    step_count: int
    max_steps: int
    # Versioning
    graph_state_version: int


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def make_thread_id(run_id: int, session_id: str) -> str:
    """Deterministic thread ID: ``"{run_id}:{session_id}"``."""
    return f"{run_id}:{session_id}"


def init_state(
    run_id: int,
    session_id: str,
    user_message: str,
    max_steps: int = 10,
) -> GraphState:
    """Create a fresh GraphState with sensible defaults."""
    return GraphState(
        run_id=run_id,
        session_id=session_id,
        thread_id=make_thread_id(run_id, session_id),
        user_message=user_message,
        messages=[],
        context_packet=ContextPacket().model_dump(),
        tool_queue=[],
        last_tool_result={},
        stop_reason="",
        is_blocked=False,
        errors=[],
        step_count=0,
        max_steps=max_steps,
        graph_state_version=GRAPH_STATE_VERSION,
    )
