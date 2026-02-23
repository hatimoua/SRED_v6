"""Integration tests for LangGraph wiring (Phase 4.6)."""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from sred.agent import registry as registry_mod
from sred.models.agent_log import ToolCallLog
from sred.models.core import Person, RateStatus, Run, RunStatus
from sred.models.world import (
    ContradictionSeverity,
    DecisionLock,
    ReviewDecision,
    ReviewTask,
    ReviewTaskStatus,
)
from sred.orchestration import nodes as nodes_mod
from sred.orchestration.graph import build_graph
from sred.orchestration.state import PlannerDecision, ToolRequest, init_state


class SequencedLLM:
    """Return pre-baked planner JSON responses in sequence."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.call_count = 0
        self.system_prompts: list[str] = []

    def chat_completions_create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> str:
        self.system_prompts.append(str(messages[0].get("content", "")))
        if self.call_count >= len(self._responses):
            raise AssertionError("Planner called more times than expected")
        raw = self._responses[self.call_count]
        self.call_count += 1
        return raw


def _seed_run_with_person(session: Session) -> Run:
    run = Run(name="Graph Test Run", status=RunStatus.PROCESSING)
    session.add(run)
    session.flush()
    person = Person(
        run_id=run.id,
        name="Alice",
        role="Developer",
        hourly_rate=100.0,
        rate_status=RateStatus.SET,
    )
    session.add(person)
    session.flush()
    return run


def test_tool_loop_executes_then_rebuilds_context_then_finalizes(use_test_engine):
    with Session(use_test_engine) as session:
        run = _seed_run_with_person(session)
        session.commit()

        fake_llm = SequencedLLM(
            responses=[
                PlannerDecision(
                    done=False,
                    tool_requests=[ToolRequest(tool_name="people_list", arguments={})],
                    reasoning="Need people snapshot",
                ).model_dump_json(),
                PlannerDecision(
                    done=True,
                    stop_reason="complete",
                    draft_response="Finished after listing people.",
                    reasoning="Done after tool output",
                ).model_dump_json(),
            ]
        )
        graph = build_graph(session, llm_client=fake_llm)
        result = graph.invoke(init_state(run.id, "loop-1", "List people and finish"))

        assert fake_llm.call_count == 2
        assert "people_list" in fake_llm.system_prompts[1]
        assert result["finalized"] is True
        assert result["stop_reason"] == "complete"
        assert result["final_payload"]["status"] == "OK"

        tool_logs = session.exec(
            select(ToolCallLog).where(ToolCallLog.run_id == run.id)
        ).all()
        assert len(tool_logs) == 1
        assert tool_logs[0].tool_name == "people_list"


def test_tool_creates_lock_and_returns_needs_review(use_test_engine, monkeypatch):
    def _activate_lock_tool(session: Session, run_id: int, **_: Any) -> dict[str, Any]:
        issue_key = f"LOCK:{run_id}:tool"
        task = ReviewTask(
            run_id=run_id,
            issue_key=issue_key,
            title="Lock seed task",
            description="Created by test tool",
            severity=ContradictionSeverity.BLOCKING,
            status=ReviewTaskStatus.RESOLVED,
        )
        session.add(task)
        session.flush()

        decision = ReviewDecision(run_id=run_id, task_id=task.id, decision="Lock this issue")
        session.add(decision)
        session.flush()

        lock = DecisionLock(
            run_id=run_id,
            issue_key=issue_key,
            decision_id=decision.id,
            reason="test lock",
            active=True,
        )
        session.add(lock)
        return {"status": "lock_created", "issue_key": issue_key}

    monkeypatch.setattr(nodes_mod, "_get_valid_tool_names", lambda: {"activate_lock"})

    def _get_handler(name: str):
        if name != "activate_lock":
            raise KeyError(name)
        return _activate_lock_tool

    monkeypatch.setattr(registry_mod, "get_tool_handler", _get_handler)

    with Session(use_test_engine) as session:
        run = _seed_run_with_person(session)
        session.commit()

        fake_llm = SequencedLLM(
            responses=[
                PlannerDecision(
                    done=False,
                    tool_requests=[
                        ToolRequest(
                            tool_name="activate_lock",
                            arguments={},
                            idempotency_key="lock-call-1",
                        )
                    ],
                    reasoning="Trigger blocking lock",
                ).model_dump_json(),
            ]
        )
        graph = build_graph(session, llm_client=fake_llm)
        result = graph.invoke(init_state(run.id, "lock-1", "Trigger a lock"))

        assert fake_llm.call_count == 1
        assert result["finalized"] is True
        assert result["stop_reason"] == "blocked"
        assert result["final_payload"]["status"] == "NEEDS_REVIEW"
        assert result["needs_review_payload"]["status"] == "NEEDS_REVIEW"
        assert any(
            a["action"] == "SUPERSEDE_LOCK"
            for a in result["needs_review_payload"]["required_actions"]
        )


def test_done_path_exits_without_tool_execution(use_test_engine):
    with Session(use_test_engine) as session:
        run = _seed_run_with_person(session)
        session.commit()

        fake_llm = SequencedLLM(
            responses=[
                PlannerDecision(
                    done=True,
                    stop_reason="complete",
                    draft_response="No tool needed.",
                    reasoning="Enough context already",
                ).model_dump_json()
            ]
        )
        graph = build_graph(session, llm_client=fake_llm)
        result = graph.invoke(init_state(run.id, "done-1", "Just summarize"))

        assert fake_llm.call_count == 1
        assert result["finalized"] is True
        assert result["stop_reason"] == "complete"
        assert result["final_payload"]["status"] == "OK"

        tool_calls = session.exec(
            select(ToolCallLog).where(ToolCallLog.run_id == run.id)
        ).all()
        assert tool_calls == []
