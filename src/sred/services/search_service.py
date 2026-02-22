"""Search use-case service."""
from __future__ import annotations
from sred.domain.exceptions import NotFoundError
from sred.infra.db.uow import UnitOfWork
from sred.infra.db.repositories.run_repository import RunRepository
from sred.api.schemas.search import SearchQuery, SearchResultRead, SearchResponse, SearchMode
from sred.search.hybrid_search import (
    fts_search, vector_search_wrapper, rrf_fusion, hybrid_search,
)
from sred.models.core import Segment, File


class SearchService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def search(self, run_id: int, payload: SearchQuery) -> SearchResponse:
        run_repo = RunRepository(self._uow.session)
        if run_repo.get_by_id(run_id) is None:
            raise NotFoundError(f"Run {run_id} not found")

        session = self._uow.session
        mode = payload.mode
        query = payload.query
        limit = payload.limit

        if mode == SearchMode.FTS:
            raw = fts_search(session, query, limit=limit)
        elif mode == SearchMode.VECTOR:
            raw = vector_search_wrapper(session, query, run_id, limit=limit)
        else:
            raw = hybrid_search(session, query, run_id, limit=limit)

        results: list[SearchResultRead] = []
        for res in raw:
            seg = session.get(Segment, res.id)
            if not seg:
                continue
            file = session.get(File, seg.file_id)
            filename = file.original_filename if file else "Unknown"
            page_info = (
                f"Page {seg.page_number}" if getattr(seg, "page_number", None)
                else f"Row {seg.row_number}" if getattr(seg, "row_number", None)
                else ""
            )
            results.append(SearchResultRead(
                segment_id=res.id,
                content=res.content,
                score=res.score,
                source=res.source,
                filename=filename,
                page_info=page_info,
            ))

        return SearchResponse(results=results, total=len(results))
