"""Agent messaging DTOs — pure Pydantic, zero ORM imports."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentMessageRequest(BaseModel):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class AgentCitationRead(BaseModel):
    segment_id: int | None = None
    snippet: str
    filename: str | None = None
    page_number: int | None = None
    row_number: int | None = None
    score: float | None = None
    source_type: str | None = None


class AgentMessageResponse(BaseModel):
    status: Literal["OK", "NEEDS_REVIEW", "ERROR"]
    message: str
    next_actions: list[dict[str, Any]] = Field(default_factory=list)
    references: list[AgentCitationRead] = Field(default_factory=list)
    citations: list[AgentCitationRead] = Field(default_factory=list)
