"""Search DTOs — pure Pydantic, zero ORM imports."""
from __future__ import annotations
from enum import Enum
from pydantic import BaseModel


class SearchMode(str, Enum):
    HYBRID = "Hybrid"
    FTS = "FTS Only"
    VECTOR = "Vector Only"


class SearchQuery(BaseModel):
    query: str
    mode: SearchMode = SearchMode.HYBRID
    limit: int = 20


class SearchResultRead(BaseModel):
    segment_id: int
    content: str
    score: float
    source: str
    filename: str | None = None
    page_info: str | None = None


class SearchResponse(BaseModel):
    results: list[SearchResultRead]
    total: int
