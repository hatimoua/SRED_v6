"""Tests for Phase 4.4 — Planner node, PlannerDecision model, LLMClient protocol."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from sred.orchestration.llm_protocol import LLMClient
from sred.orchestration.state import (
    ContextPacket,
    GraphState,
    PlannerDecision,
    ToolRequest,
    WorldSnapshot,
    init_state,
)
from sred.orchestration import nodes as nodes_mod
from sred.orchestration.nodes import make_nodes


# ---------------------------------------------------------------------------
# FakeLLMClient
# ---------------------------------------------------------------------------


class FakeLLMClient:
    """Test double that returns a pre-configured JSON string."""

    def __init__(self, response_json: str) -> None:
        self._response = response_json
        self.call_count = 0
        self.last_messages: list[dict[str, Any]] | None = None

    def chat_completions_create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> str:
        self.call_count += 1
        self.last_messages = messages
        return self._response


# Verify FakeLLMClient satisfies Protocol at runtime
assert isinstance(FakeLLMClient("{}"), LLMClient)


# ---------------------------------------------------------------------------
# PlannerDecision validation tests
# ---------------------------------------------------------------------------


class TestPlannerDecisionValidation:
    def test_done_valid(self):
        d = PlannerDecision(
            done=True,
            stop_reason="complete",
            draft_response="All done.",
            reasoning="nothing left",
        )
        assert d.done is True
        assert d.stop_reason == "complete"
        assert d.tool_requests == []

    def test_tool_valid(self):
        d = PlannerDecision(
            done=False,
            tool_requests=[ToolRequest(tool_name="extract_hours", arguments={"file_id": 1})],
            reasoning="need to extract",
        )
        assert d.done is False
        assert len(d.tool_requests) == 1

    def test_done_missing_response_raises(self):
        with pytest.raises(ValidationError, match="draft_response"):
            PlannerDecision(done=True, stop_reason="complete")

    def test_not_done_no_tools_raises(self):
        with pytest.raises(ValidationError, match="at least one tool_request"):
            PlannerDecision(done=False, tool_requests=[])

    def test_done_with_tools_raises(self):
        with pytest.raises(ValidationError, match="must not have tool_requests"):
            PlannerDecision(
                done=True,
                stop_reason="complete",
                draft_response="done",
                tool_requests=[ToolRequest(tool_name="foo")],
            )


# ---------------------------------------------------------------------------
# Planner node integration tests (FakeLLMClient, no DB)
# ---------------------------------------------------------------------------


def _make_state(**overrides: Any) -> GraphState:
    """Create a minimal GraphState for planner tests."""
    s = init_state(run_id=1, session_id="test", user_message="process files")
    # Give it a minimal world snapshot so prompt building works
    packet = ContextPacket(
        world_snapshot=WorldSnapshot(run_id=1, run_status="PROCESSING")
    )
    s["context_packet"] = packet.model_dump()
    s.update(overrides)
    return s


class TestPlannerNode:
    def test_returns_tool_queue(self, monkeypatch):
        # Patch valid tool names so "list_files" is recognized
        monkeypatch.setattr(nodes_mod, "_get_valid_tool_names", lambda: {"list_files"})

        decision = PlannerDecision(
            done=False,
            tool_requests=[ToolRequest(tool_name="list_files", arguments={})],
            reasoning="need files",
        )
        fake = FakeLLMClient(decision.model_dump_json())
        # Mock session — planner never touches it
        nodes = make_nodes(MagicMock(), llm_client=fake)
        planner = nodes["planner"]

        state = _make_state()
        result = planner(state)

        assert fake.call_count == 1
        assert len(result["tool_queue"]) == 1
        assert result["tool_queue"][0]["tool_name"] == "list_files"
        assert result["step_count"] == 1

    def test_returns_stop_on_done(self):
        decision = PlannerDecision(
            done=True,
            stop_reason="complete",
            draft_response="All files processed successfully.",
            reasoning="everything done",
        )
        fake = FakeLLMClient(decision.model_dump_json())
        nodes = make_nodes(MagicMock(), llm_client=fake)
        planner = nodes["planner"]

        state = _make_state()
        result = planner(state)

        assert result["stop_reason"] == "complete"
        assert result["tool_queue"] == []
        # Assistant message appended
        assert any(
            m["role"] == "assistant" and "processed" in m["content"]
            for m in result["messages"]
        )

    def test_max_steps_guard(self):
        fake = FakeLLMClient("{}")  # Should never be called
        nodes = make_nodes(MagicMock(), llm_client=fake)
        planner = nodes["planner"]

        state = _make_state(step_count=10, max_steps=10)
        result = planner(state)

        assert result["stop_reason"] == "max_steps"
        assert result["tool_queue"] == []
        assert fake.call_count == 0  # LLM not called

    def test_unknown_tool_error(self):
        decision = PlannerDecision(
            done=False,
            tool_requests=[ToolRequest(tool_name="nonexistent_tool_xyz", arguments={})],
            reasoning="trying unknown",
        )
        fake = FakeLLMClient(decision.model_dump_json())
        nodes = make_nodes(MagicMock(), llm_client=fake)
        planner = nodes["planner"]

        state = _make_state()
        result = planner(state)

        assert result["stop_reason"] == "error"
        assert any("Unknown tool" in e for e in result["errors"])

    def test_planner_absent_without_llm_client(self):
        # When no llm_client is provided, planner key should be absent
        nodes = make_nodes(MagicMock())
        assert "planner" not in nodes
        # But deterministic nodes are still present
        assert "load_world_snapshot" in nodes
        assert "context_compiler" in nodes
