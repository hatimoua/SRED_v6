"""Search endpoints."""
from fastapi import APIRouter, Depends
from sred.api.deps import get_uow
from sred.api.schemas.search import SearchQuery, SearchResponse
from sred.infra.db.uow import UnitOfWork
from sred.services.search_service import SearchService

router = APIRouter(prefix="/runs/{run_id}", tags=["search"])


@router.post("/search", response_model=SearchResponse)
def search(
    run_id: int, payload: SearchQuery, uow: UnitOfWork = Depends(get_uow),
) -> SearchResponse:
    return SearchService(uow).search(run_id, payload)
