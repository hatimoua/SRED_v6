"""Agent messaging service backed by LangGraph orchestration."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver

from sred.api.schemas.agent import AgentCitationRead, AgentMessageRequest, AgentMessageResponse
from sred.domain.exceptions import NotFoundError
from sred.infra.db.repositories.run_repository import RunRepository
from sred.infra.db.uow import UnitOfWork
from sred.orchestration.checkpointer import get_checkpointer
from sred.orchestration.graph import build_graph
from sred.orchestration.llm_protocol import LLMClient, OpenAILLMClient


class AgentService:
    def __init__(
        self,
        uow: UnitOfWork,
        *,
        llm_client: LLMClient | None = None,
        checkpointer_factory: Callable[[], BaseCheckpointSaver] | None = None,
    ) -> None:
        self._uow = uow
        self._llm_client = llm_client or OpenAILLMClient()
        self._checkpointer_factory = checkpointer_factory or get_checkpointer

    def send_message(self, run_id: int, payload: AgentMessageRequest) -> AgentMessageResponse:
        run = RunRepository(self._uow.session).get_by_id(run_id)
        if run is None:
            raise NotFoundError(f"Run {run_id} not found")

        checkpointer = self._checkpointer_factory()
        try:
            graph = build_graph(
                self._uow.session,
                llm_client=self._llm_client,
                checkpointer=checkpointer,
            )
            thread_id = f"{run_id}:{payload.session_id}"
            config = {"configurable": {"thread_id": thread_id}}
            # Send only per-turn inputs so checkpointed state is preserved on resume.
            result = graph.invoke(
                {
                    "run_id": run_id,
                    "session_id": payload.session_id,
                    "user_message": payload.message,
                },
                config=config,
            )
            final_payload = dict(result.get("final_payload") or {})
            citations = self._extract_citations(result)
            return AgentMessageResponse(
                status=final_payload.get("status", "ERROR"),
                message=final_payload.get("message", "Agent did not return a message."),
                next_actions=list(final_payload.get("next_actions") or []),
                references=citations,
                citations=citations,
            )
        finally:
            conn = getattr(checkpointer, "conn", None)
            if conn is not None:
                conn.close()

    def _extract_citations(self, result: dict[str, Any]) -> list[AgentCitationRead]:
        raw_packet = result.get("context_packet") or {}
        raw_evidence = (raw_packet.get("evidence_pack") or {}).get("items") or []
        citations: list[AgentCitationRead] = []
        for item in raw_evidence:
            snippet = str(item.get("content", "") or "").strip()
            if not snippet:
                continue
            citations.append(
                AgentCitationRead(
                    segment_id=item.get("segment_id"),
                    snippet=snippet[:240],
                    filename=item.get("original_filename"),
                    page_number=item.get("page_number"),
                    row_number=item.get("row_number"),
                    score=item.get("score"),
                    source_type=item.get("source_type"),
                )
            )
        return citations
