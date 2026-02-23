"""Deterministic context-lane nodes for LangGraph orchestration.

Each node follows the LangGraph convention: receives GraphState, returns a
partial state dict.  Deterministic nodes are DB-backed and side-effect free
except ``tool_executor`` (which writes tool logs/DB updates).  When an
``LLMClient`` is provided, a ``planner`` node is also returned.

Use ``make_nodes(session)`` to get a dict of node functions closed over a
SQLAlchemy Session, keeping nodes testable without FastAPI.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable

from sred.config import settings

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
from sred.models.agent_log import ToolCallLog
from sred.models.memory import MemoryDoc
from sred.models.world import (
    Contradiction,
    ContradictionSeverity,
    ContradictionStatus,
    DecisionLock,
    ReviewTask,
    ReviewTaskStatus,
)
from sred.orchestration.llm_protocol import LLMClient
from sred.orchestration.state import (
    ContextPacket,
    EvidenceItem,
    EvidencePack,
    GraphState,
    MemoryEntry,
    MemorySummaries,
    PeopleTimeAnchor,
    PlannerDecision,
    PersonAnchor,
    TokenBudget,
    ToolOutcome,
    ToolRequest,
    WorldSnapshot,
    make_thread_id,
)

logger = logging.getLogger(__name__)


def make_nodes(
    session: Session,
    llm_client: LLMClient | None = None,
) -> dict[str, Callable]:
    """Return a dict of node functions closed over *session*.

    Each value is a ``def node(state: GraphState) -> dict`` callable
    suitable for use as a LangGraph node.

    When *llm_client* is provided, a ``"planner"`` node is included that
    calls the LLM to decide the next tool call or finalization.
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

    # ------------------------------------------------------------------
    # Shared helper — gate snapshot from DB truth (deterministic)
    # ------------------------------------------------------------------
    def _build_gate_snapshot(run_id: int) -> dict[str, Any]:
        blocking_contradictions = list(
            session.exec(
                select(Contradiction).where(
                    Contradiction.run_id == run_id,
                    Contradiction.severity == ContradictionSeverity.BLOCKING,
                    Contradiction.status == ContradictionStatus.OPEN,
                ).order_by(Contradiction.id)
            ).all()
        )
        required_tasks = list(
            session.exec(
                select(ReviewTask).where(
                    ReviewTask.run_id == run_id,
                    ReviewTask.severity == ContradictionSeverity.BLOCKING,
                    ReviewTask.status == ReviewTaskStatus.OPEN,
                ).order_by(ReviewTask.id)
            ).all()
        )
        active_locks = list(
            session.exec(
                select(DecisionLock).where(
                    DecisionLock.run_id == run_id,
                    DecisionLock.active == True,  # noqa: E712
                ).order_by(DecisionLock.id)
            ).all()
        )

        return {
            "blocking_contradictions": [
                {
                    "id": c.id,
                    "issue_key": c.issue_key,
                    "type": c.contradiction_type.value if hasattr(c.contradiction_type, "value") else str(c.contradiction_type),
                    "severity": c.severity.value if hasattr(c.severity, "value") else str(c.severity),
                    "description": c.description,
                }
                for c in blocking_contradictions
            ],
            "required_tasks": [
                {
                    "id": t.id,
                    "issue_key": t.issue_key,
                    "title": t.title,
                    "severity": t.severity.value if hasattr(t.severity, "value") else str(t.severity),
                    "status": t.status.value if hasattr(t.status, "value") else str(t.status),
                }
                for t in required_tasks
            ],
            "active_locks": [
                {
                    "id": lk.id,
                    "issue_key": lk.issue_key,
                    "reason": lk.reason,
                    "decision_id": lk.decision_id,
                }
                for lk in active_locks
            ],
            "counts": {
                "blocking_contradictions": len(blocking_contradictions),
                "required_tasks": len(required_tasks),
                "active_locks": len(active_locks),
            },
        }

    # ------------------------------------------------------------------
    # Node 6 — tool_executor (deterministic tool call execution)
    # ------------------------------------------------------------------
    def tool_executor(state: GraphState) -> dict:
        run_id: int = state["run_id"]
        session_id: str | None = state.get("session_id")
        thread_id: str | None = state.get("thread_id")
        if thread_id is None and session_id:
            thread_id = make_thread_id(run_id, session_id)
        queue_raw = list(state.get("tool_queue", []) or [])
        if not queue_raw:
            return {}

        try:
            request = ToolRequest.model_validate(queue_raw[0])
        except Exception as exc:
            return {
                "tool_queue": queue_raw[1:],
                "errors": state.get("errors", []) + [f"Invalid tool request: {exc}"],
            }

        tool_name = request.tool_name
        arguments = request.arguments or {}
        args_json = json.dumps(arguments, sort_keys=True, default=str)
        tool_call_id = request.idempotency_key or f"tool_call_{run_id}_{time.time_ns()}"

        started = time.monotonic()
        success = True
        try:
            _ensure_tools_registered()
            from sred.agent.registry import get_tool_handler

            handler = get_tool_handler(tool_name)
            result = handler(session, run_id, **arguments)
            session.commit()
        except KeyError:
            result = {"error": f"Unknown tool: {tool_name}"}
            success = False
            session.rollback()
        except Exception as exc:
            logger.exception("Tool execution failed for %s", tool_name)
            result = {"error": str(exc)}
            success = False
            session.rollback()

        duration_ms = int((time.monotonic() - started) * 1000)
        tool_log = ToolCallLog(
            run_id=run_id,
            session_id=session_id,
            thread_id=thread_id,
            tool_name=tool_name,
            arguments_json=args_json,
            result_json=json.dumps(result, default=str)[:4000],
            success=success,
            duration_ms=duration_ms,
        )
        session.add(tool_log)
        session.commit()

        assistant_tool_call_message = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {"name": tool_name, "arguments": args_json},
                }
            ],
        }
        tool_message = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": json.dumps(result, default=str),
        }

        update: dict[str, Any] = {
            "tool_queue": queue_raw[1:],
            "last_tool_result": {
                "tool_name": tool_name,
                "arguments": arguments,
                "result": result,
                "success": success,
                "duration_ms": duration_ms,
            },
            "messages": state.get("messages", []) + [assistant_tool_call_message, tool_message],
        }
        if state.get("thread_id") is None and thread_id is not None:
            update["thread_id"] = thread_id
        if not success:
            update["errors"] = state.get("errors", []) + [f"Tool {tool_name} failed"]
        return update

    # ------------------------------------------------------------------
    # Node 7 — gate_evaluator (deterministic, DB-backed)
    # ------------------------------------------------------------------
    def gate_evaluator(state: GraphState) -> dict:
        run_id: int = state["run_id"]
        snapshot = _build_gate_snapshot(run_id)
        blocked = any(snapshot["counts"].values())
        return {
            "gate_snapshot": snapshot,
            "is_blocked": blocked,
        }

    # ------------------------------------------------------------------
    # Node 8 — human_gate (assemble strict NEEDS_REVIEW payload)
    # ------------------------------------------------------------------
    def human_gate(state: GraphState) -> dict:
        run_id: int = state["run_id"]
        session_id: str | None = state.get("session_id")
        thread_id: str | None = state.get("thread_id")
        if thread_id is None and session_id:
            thread_id = make_thread_id(run_id, session_id)
        prior_stop_reason = state.get("stop_reason", "")
        snapshot = state.get("gate_snapshot") or _build_gate_snapshot(run_id)

        required_actions: list[dict[str, Any]] = []
        required_actions.extend(
            {"action": "RESOLVE_TASK", "task_id": t["id"], "issue_key": t["issue_key"]}
            for t in snapshot["required_tasks"]
        )
        required_actions.extend(
            {"action": "RESOLVE_CONTRADICTION", "contradiction_id": c["id"], "issue_key": c["issue_key"]}
            for c in snapshot["blocking_contradictions"]
        )
        required_actions.extend(
            {"action": "SUPERSEDE_LOCK", "lock_id": lk["id"], "issue_key": lk["issue_key"]}
            for lk in snapshot["active_locks"]
        )

        missing_evidence = [
            {"issue_key": c["issue_key"], "reason": c["description"]}
            for c in snapshot["blocking_contradictions"]
            if c["type"] == "MISSING_EVIDENCE"
        ]
        ask_user_prompt = ""
        if prior_stop_reason == "ask_user":
            for msg in reversed(state.get("messages", [])):
                if msg.get("role") == "assistant" and msg.get("content"):
                    ask_user_prompt = str(msg.get("content"))
                    break

        payload = {
            "status": "NEEDS_REVIEW",
            "run_id": run_id,
            "session_id": session_id,
            "thread_id": thread_id,
            "required_actions": required_actions,
            "missing_evidence": missing_evidence,
            "blocking_contradictions": snapshot["blocking_contradictions"],
            "required_tasks": snapshot["required_tasks"],
            "active_locks": snapshot["active_locks"],
        }
        if ask_user_prompt:
            payload["user_prompt"] = ask_user_prompt
        update: dict[str, Any] = {
            "is_blocked": True,
            "stop_reason": "ask_user" if prior_stop_reason == "ask_user" else "blocked",
            "gate_snapshot": snapshot,
            "needs_review_payload": payload,
        }
        if state.get("thread_id") is None and thread_id is not None:
            update["thread_id"] = thread_id
        return update

    # ------------------------------------------------------------------
    # Node 9 — summarizer (deterministic turn summary)
    # ------------------------------------------------------------------
    def summarizer(state: GraphState) -> dict:
        stop_reason = state.get("stop_reason", "")
        summary = "Turn complete."
        if stop_reason == "blocked":
            summary = "Turn paused for human review."
        elif stop_reason == "error":
            summary = "Turn stopped due to an error."
        elif stop_reason == "max_steps":
            summary = "Turn stopped after reaching max steps."
        elif state.get("last_tool_result"):
            ltr = state["last_tool_result"]
            summary = (
                f"Executed tool {ltr.get('tool_name')} "
                f"({'success' if ltr.get('success') else 'failed'})."
            )
        return {"summary_text": summary}

    # ------------------------------------------------------------------
    # Node 10 — finalizer (normalize terminal payload)
    # ------------------------------------------------------------------
    def finalizer(state: GraphState) -> dict:
        stop_reason = state.get("stop_reason", "")
        is_blocked = bool(state.get("is_blocked"))
        review_payload = state.get("needs_review_payload") or {}
        status = "OK"
        message = ""
        next_actions: list[dict[str, Any]] = []
        assistant_message = ""
        for msg in reversed(state.get("messages", [])):
            if msg.get("role") == "assistant" and msg.get("content"):
                assistant_message = str(msg.get("content"))
                break

        if stop_reason in {"error", "max_steps"}:
            status = "ERROR"
            errs = state.get("errors", [])
            message = errs[-1] if errs else f"Agent stopped with reason: {stop_reason}"
        elif stop_reason == "ask_user" or is_blocked or stop_reason == "blocked":
            status = "NEEDS_REVIEW"
            next_actions = list(review_payload.get("required_actions") or [])
            message = assistant_message or "Human review required before continuing."
        else:
            message = assistant_message or state.get("summary_text", "Turn complete.")

        return {
            "finalized": True,
            "final_payload": {
                "status": status,
                "message": message,
                "next_actions": next_actions,
            },
        }

    # ------------------------------------------------------------------
    # Node 11 — planner (LLM, bounded)
    # ------------------------------------------------------------------
    def planner(state: GraphState) -> dict:
        assert llm_client is not None, "planner node requires an LLMClient"

        step_count: int = state.get("step_count", 0)
        max_steps: int = state.get("max_steps", 10)

        # Guard: max steps reached — stop without calling LLM
        if step_count >= max_steps:
            return {
                "stop_reason": "max_steps",
                "tool_queue": [],
                "exit_requested": True,
            }

        packet = _current_packet(state)
        system_prompt = _build_planner_system_prompt(packet, state)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": state.get("user_message", "")},
        ]
        # Append prior conversation messages (tool results, etc.)
        for msg in state.get("messages", []):
            messages.append(msg)

        raw = llm_client.chat_completions_create(
            model=settings.OPENAI_MODEL_AGENT,
            messages=messages,
            response_format=_planner_response_format(),
        )

        try:
            decision = PlannerDecision.model_validate_json(raw)
        except Exception as exc:
            logger.error("Planner output failed validation: %s", exc)
            return {
                "stop_reason": "error",
                "errors": state.get("errors", []) + [f"Planner parse error: {exc}"],
                "tool_queue": [],
                "exit_requested": True,
            }

        # Validate tool names against registry
        if not decision.done:
            valid_names = _get_valid_tool_names()
            for tr in decision.tool_requests:
                if tr.tool_name not in valid_names:
                    logger.error("Planner requested unknown tool: %s", tr.tool_name)
                    return {
                        "stop_reason": "error",
                        "errors": state.get("errors", [])
                        + [f"Unknown tool: {tr.tool_name}"],
                        "tool_queue": [],
                        "exit_requested": True,
                    }

        if decision.done:
            assistant_msg = {
                "role": "assistant",
                "content": decision.draft_response,
            }
            return {
                "stop_reason": decision.stop_reason,
                "messages": state.get("messages", []) + [assistant_msg],
                "tool_queue": [],
                "exit_requested": True,
            }

        # Not done — enqueue tool requests
        return {
            "tool_queue": [tr.model_dump() for tr in decision.tool_requests],
            "step_count": step_count + 1,
            "exit_requested": False,
        }

    # ------------------------------------------------------------------
    # Assemble return dict
    # ------------------------------------------------------------------
    nodes = {
        "load_world_snapshot": load_world_snapshot,
        "build_anchor_lane": build_anchor_lane,
        "memory_retrieve": memory_retrieve,
        "retrieve_evidence_pack": retrieve_evidence_pack,
        "context_compiler": context_compiler,
        "tool_executor": tool_executor,
        "gate_evaluator": gate_evaluator,
        "human_gate": human_gate,
        "summarizer": summarizer,
        "finalizer": finalizer,
    }
    if llm_client is not None:
        nodes["planner"] = planner
    return nodes


# ---------------------------------------------------------------------------
# Planner prompt construction
# ---------------------------------------------------------------------------

_PLANNER_PREAMBLE = """\
You are the SR&ED Automation Planner.  Your job is to decide the NEXT action
for processing a Canadian SR&ED tax-credit claim.

RULES:
1. You may ONLY reference facts present in the context below.  Never invent
   data, file names, people, or amounts.
2. You may request exactly ONE tool call at a time.
3. When the task is complete or you need human input, set done=True with an
   appropriate stop_reason ("complete" or "ask_user") and a draft_response.
4. Keep reasoning concise.
5. Respond with valid JSON matching the PlannerDecision schema.
6. If the World Snapshot shows any open contradictions, open tasks, or active
   locks, you must NOT use stop_reason="complete"; use stop_reason="ask_user"
   with a concise action request instead.
"""


def _build_planner_system_prompt(packet: ContextPacket, state: GraphState) -> str:
    """Render the ContextPacket lanes + available tools into a system prompt."""
    sections: list[str] = [_PLANNER_PREAMBLE]

    # Lane 1 — World Snapshot
    if packet.world_snapshot:
        ws = packet.world_snapshot
        sections.append(
            f"## World Snapshot (DB Truth)\n"
            f"Run {ws.run_id} — status: {ws.run_status}\n"
            f"Files: {ws.file_count} ({ws.files_processed} processed) | "
            f"People: {ws.people_count} (pending rates: {ws.pending_rates})\n"
            f"Contradictions: {ws.open_contradictions} open | "
            f"Tasks: {ws.open_tasks} open | Locks: {ws.active_locks}\n"
            f"Staging: {ws.staging_total} total ({ws.staging_pending} pending, "
            f"{ws.staging_promoted} promoted) | Ledger rows: {ws.ledger_count}"
        )
        if ws.last_tool_outcomes:
            outcomes = "\n".join(
                f"  - {o.name}: {'OK' if o.success else 'FAIL'} — {o.summary}"
                for o in ws.last_tool_outcomes
            )
            sections.append(f"Recent tool results:\n{outcomes}")

    # Lane 2 — People & Time Anchor
    if packet.people_time_anchor:
        pta = packet.people_time_anchor
        people_lines = "\n".join(
            f"  - {p.name} (id={p.person_id}, role={p.role}, "
            f"rate={'$'+str(p.hourly_rate) if p.hourly_rate else 'N/A'}, "
            f"status={p.rate_status})"
            for p in pta.people
        )
        sections.append(
            f"## People & Time Anchor\n"
            f"Aliases: {pta.alias_confirmed}/{pta.alias_total} confirmed\n"
            f"Staging rows: {pta.timesheet_staging_rows} timesheet, "
            f"{pta.payroll_staging_rows} payroll\n"
            f"People:\n{people_lines}" if people_lines else
            f"## People & Time Anchor\n"
            f"Aliases: {pta.alias_confirmed}/{pta.alias_total} confirmed\n"
            f"Staging rows: {pta.timesheet_staging_rows} timesheet, "
            f"{pta.payroll_staging_rows} payroll\nPeople: (none)"
        )

    # Lane 3 — Memory Summaries
    if packet.memory_summaries and packet.memory_summaries.entries:
        mem_lines = "\n".join(
            f"  - [{e.memory_id}] {e.path}: {e.snippet}"
            for e in packet.memory_summaries.entries
        )
        sections.append(f"## Memory Summaries\n{mem_lines}")

    # Lane 4 — Evidence Pack
    if packet.evidence_pack and packet.evidence_pack.items:
        ev_lines = "\n".join(
            f"  - [seg {it.segment_id}] {it.original_filename or 'unknown'}"
            f" p{it.page_number} r{it.row_number}: "
            f"{it.content[:120]}"
            for it in packet.evidence_pack.items
        )
        sections.append(
            f"## Evidence Pack (query: {packet.evidence_pack.query_used})\n{ev_lines}"
        )

    # Available tools
    tool_names = sorted(_get_valid_tool_names())
    if tool_names:
        sections.append(f"## Available Tools\n{', '.join(tool_names)}")

    return "\n\n".join(sections)


def _get_valid_tool_names() -> set[str]:
    """Return the set of registered tool names (lazy import)."""
    try:
        _ensure_tools_registered()
        from sred.agent.registry import TOOL_REGISTRY
        return set(TOOL_REGISTRY.keys())
    except ImportError:
        return set()


def _planner_response_format() -> dict[str, Any]:
    """Build the OpenAI structured-output response_format dict.

    ``strict=True`` tells the API to guarantee schema adherence.  Pydantic's
    generated schema is compatible because all fields either have defaults or
    are required — no unsupported constructs.
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "PlannerDecision",
            "strict": True,
            "schema": PlannerDecision.model_json_schema(),
        },
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


def _ensure_tools_registered() -> None:
    """Import tool module for side-effect registration in TOOL_REGISTRY."""
    try:
        import sred.agent.tools  # noqa: F401
    except Exception:
        # Planner/tool execution will fail gracefully if registry remains empty.
        return
