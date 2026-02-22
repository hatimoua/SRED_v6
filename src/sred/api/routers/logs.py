"""Execution trace / logs endpoints."""
from fastapi import APIRouter, Depends, Query
from sred.api.deps import get_uow
from sred.api.schemas.logs import ToolCallLogList, LLMCallLogList
from sred.infra.db.uow import UnitOfWork
from sred.services.logs_service import LogsService

router = APIRouter(prefix="/runs/{run_id}/logs", tags=["logs"])


@router.get("/tool-calls", response_model=ToolCallLogList)
def list_tool_calls(
    run_id: int,
    limit: int = 50,
    offset: int = 0,
    tool_name: str | None = Query(default=None),
    uow: UnitOfWork = Depends(get_uow),
) -> ToolCallLogList:
    return LogsService(uow).list_tool_calls(run_id, limit=limit, offset=offset, tool_name=tool_name)


@router.get("/llm-calls", response_model=LLMCallLogList)
def list_llm_calls(
    run_id: int,
    limit: int = 20,
    offset: int = 0,
    uow: UnitOfWork = Depends(get_uow),
) -> LLMCallLogList:
    return LogsService(uow).list_llm_calls(run_id, limit=limit, offset=offset)


@router.get("/sessions")
def list_sessions(run_id: int, uow: UnitOfWork = Depends(get_uow)) -> list[dict]:
    return LogsService(uow).list_sessions(run_id)


@router.get("/sessions/{session_id}")
def get_session_trace(
    run_id: int, session_id: str, uow: UnitOfWork = Depends(get_uow),
) -> dict:
    return LogsService(uow).get_session_trace(run_id, session_id)
