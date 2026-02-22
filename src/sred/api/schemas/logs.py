"""Agent log DTOs — pure Pydantic, zero ORM imports."""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel


class ToolCallLogRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    run_id: int
    session_id: str | None = None
    tool_name: str
    arguments_json: str
    result_json: str
    success: bool
    duration_ms: int
    created_at: datetime | None = None


class LLMCallLogRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    run_id: int
    session_id: str | None = None
    model: str
    prompt_summary: str
    message_count: int
    tool_calls_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    finish_reason: str | None = None
    created_at: datetime | None = None


class ToolCallLogList(BaseModel):
    items: list[ToolCallLogRead]
    total: int


class LLMCallLogList(BaseModel):
    items: list[LLMCallLogRead]
    total: int
