"""LangGraph wiring for the SR&ED agent orchestration flow."""

from __future__ import annotations

from typing import Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from sqlmodel import Session

from sred.orchestration.llm_protocol import LLMClient
from sred.orchestration.nodes import make_nodes
from sred.orchestration.state import GraphState


def build_graph(
    session: Session,
    llm_client: LLMClient,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """Compile the orchestration graph with a clean tool-loop vs exit split."""
    nodes = make_nodes(session, llm_client=llm_client)

    graph = StateGraph(GraphState)
    for node_name in (
        "load_world_snapshot",
        "build_anchor_lane",
        "memory_retrieve",
        "retrieve_evidence_pack",
        "context_compiler",
        "planner",
        "tool_executor",
        "gate_evaluator",
        "human_gate",
        "summarizer",
        "finalizer",
    ):
        graph.add_node(node_name, nodes[node_name])

    # Initial deterministic context build
    graph.add_edge(START, "load_world_snapshot")
    graph.add_edge("load_world_snapshot", "build_anchor_lane")
    graph.add_edge("build_anchor_lane", "memory_retrieve")
    graph.add_edge("memory_retrieve", "retrieve_evidence_pack")
    graph.add_edge("retrieve_evidence_pack", "context_compiler")
    graph.add_edge("context_compiler", "planner")

    # planner(done=no) -> tool loop; planner(done=yes/error/max_steps) -> exit evaluation
    graph.add_conditional_edges(
        "planner",
        _route_after_planner,
        {
            "tool_loop": "tool_executor",
            "exit_eval": "gate_evaluator",
        },
    )

    graph.add_edge("tool_executor", "gate_evaluator")
    graph.add_conditional_edges(
        "gate_evaluator",
        _route_after_gate,
        {
            "blocked": "human_gate",
            "continue_tool_loop": "load_world_snapshot",
            "finalize": "summarizer",
        },
    )

    # Human gate converges to exit
    graph.add_edge("human_gate", "summarizer")
    graph.add_edge("summarizer", "finalizer")
    graph.add_edge("finalizer", END)

    return graph.compile(checkpointer=checkpointer)


def _route_after_planner(state: GraphState) -> Literal["tool_loop", "exit_eval"]:
    return "tool_loop" if state.get("tool_queue") else "exit_eval"


def _route_after_gate(state: GraphState) -> Literal["blocked", "continue_tool_loop", "finalize"]:
    stop_reason = state.get("stop_reason")
    if state.get("exit_requested") and stop_reason in {"error", "max_steps"}:
        return "finalize"
    if state.get("is_blocked"):
        return "blocked"
    if state.get("exit_requested"):
        return "finalize"
    return "continue_tool_loop"
