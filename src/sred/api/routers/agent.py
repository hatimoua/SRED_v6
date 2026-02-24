"""Agent messaging endpoints."""
from fastapi import APIRouter, Depends

from sred.api.deps import get_uow
from sred.api.schemas.agent import AgentMessageRequest, AgentMessageResponse
from sred.infra.db.uow import UnitOfWork
from sred.services.agent_service import AgentService

router = APIRouter(prefix="/runs/{run_id}", tags=["agent"])


@router.post("/agent/message", response_model=AgentMessageResponse)
def send_agent_message(
    run_id: int,
    payload: AgentMessageRequest,
    uow: UnitOfWork = Depends(get_uow),
) -> AgentMessageResponse:
    return AgentService(uow).send_message(run_id, payload)
