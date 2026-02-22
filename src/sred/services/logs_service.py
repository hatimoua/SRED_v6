"""Logs use-case service."""
from __future__ import annotations
from sred.domain.exceptions import NotFoundError
from sred.infra.db.uow import UnitOfWork
from sred.infra.db.repositories.run_repository import RunRepository
from sred.infra.db.repositories.log_repository import LogRepository
from sred.api.schemas.logs import (
    ToolCallLogRead, ToolCallLogList,
    LLMCallLogRead, LLMCallLogList,
)


class LogsService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def _ensure_run(self, run_id: int) -> None:
        if RunRepository(self._uow.session).get_by_id(run_id) is None:
            raise NotFoundError(f"Run {run_id} not found")

    def list_tool_calls(
        self, run_id: int, *, limit: int = 50, offset: int = 0, tool_name: str | None = None,
    ) -> ToolCallLogList:
        self._ensure_run(run_id)
        repo = LogRepository(self._uow.session)
        items = repo.list_tool_calls(run_id, limit=limit, offset=offset, tool_name=tool_name)
        total = repo.count_tool_calls(run_id, tool_name=tool_name)
        return ToolCallLogList(
            items=[ToolCallLogRead.model_validate(i) for i in items],
            total=total,
        )

    def list_llm_calls(
        self, run_id: int, *, limit: int = 20, offset: int = 0,
    ) -> LLMCallLogList:
        self._ensure_run(run_id)
        repo = LogRepository(self._uow.session)
        items = repo.list_llm_calls(run_id, limit=limit, offset=offset)
        total = repo.count_llm_calls(run_id)
        return LLMCallLogList(
            items=[LLMCallLogRead.model_validate(i) for i in items],
            total=total,
        )

    def list_sessions(self, run_id: int) -> list[dict]:
        self._ensure_run(run_id)
        repo = LogRepository(self._uow.session)
        return repo.list_sessions(run_id)

    def get_session_trace(self, run_id: int, session_id: str) -> dict:
        self._ensure_run(run_id)
        repo = LogRepository(self._uow.session)
        llm_calls = repo.list_llm_calls_by_session(run_id, session_id)
        tool_calls = repo.list_tool_calls_by_session(run_id, session_id)
        return {
            "llm_calls": [LLMCallLogRead.model_validate(c) for c in llm_calls],
            "tool_calls": [ToolCallLogRead.model_validate(c) for c in tool_calls],
        }
