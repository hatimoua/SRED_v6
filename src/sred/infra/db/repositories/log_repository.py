"""Repository for agent log records. No business logic."""
from __future__ import annotations
from sqlalchemy import func
from sqlmodel import Session, select, desc, col
from sred.models.agent_log import ToolCallLog, LLMCallLog


class LogRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    # --- ToolCallLog ---

    def list_tool_calls(
        self, run_id: int, *, limit: int = 50, offset: int = 0, tool_name: str | None = None,
    ) -> list[ToolCallLog]:
        stmt = select(ToolCallLog).where(ToolCallLog.run_id == run_id)
        if tool_name:
            stmt = stmt.where(ToolCallLog.tool_name == tool_name)
        stmt = stmt.order_by(desc(ToolCallLog.created_at)).offset(offset).limit(limit)
        return list(self._s.exec(stmt).all())

    def count_tool_calls(self, run_id: int, *, tool_name: str | None = None) -> int:
        stmt = select(func.count()).select_from(ToolCallLog).where(ToolCallLog.run_id == run_id)
        if tool_name:
            stmt = stmt.where(ToolCallLog.tool_name == tool_name)
        return self._s.exec(stmt).one()

    # --- LLMCallLog ---

    def list_llm_calls(
        self, run_id: int, *, limit: int = 20, offset: int = 0,
    ) -> list[LLMCallLog]:
        stmt = (
            select(LLMCallLog)
            .where(LLMCallLog.run_id == run_id)
            .order_by(desc(LLMCallLog.created_at))
            .offset(offset)
            .limit(limit)
        )
        return list(self._s.exec(stmt).all())

    def count_llm_calls(self, run_id: int) -> int:
        return self._s.exec(
            select(func.count()).select_from(LLMCallLog).where(LLMCallLog.run_id == run_id)
        ).one()

    def list_llm_calls_by_session(
        self, run_id: int, session_id: str,
    ) -> list[LLMCallLog]:
        return list(self._s.exec(
            select(LLMCallLog)
            .where(LLMCallLog.run_id == run_id, LLMCallLog.session_id == session_id)
            .order_by(LLMCallLog.created_at)
        ).all())

    def list_tool_calls_by_session(
        self, run_id: int, session_id: str,
    ) -> list[ToolCallLog]:
        return list(self._s.exec(
            select(ToolCallLog)
            .where(ToolCallLog.run_id == run_id, ToolCallLog.session_id == session_id)
            .order_by(ToolCallLog.created_at)
        ).all())

    def list_sessions(self, run_id: int) -> list[dict]:
        """Return distinct sessions with metadata, most recent first."""
        llm_rows = self._s.exec(
            select(LLMCallLog)
            .where(LLMCallLog.run_id == run_id, LLMCallLog.session_id != None)  # noqa: E711
            .order_by(desc(LLMCallLog.created_at))
        ).all()

        seen: dict[str, dict] = {}
        for row in llm_rows:
            sid = row.session_id
            if sid and sid not in seen:
                seen[sid] = {
                    "session_id": sid,
                    "started_at": row.created_at,
                    "model": row.model,
                    "first_prompt": row.prompt_summary[:120] if row.prompt_summary else "",
                }
        return list(seen.values())
