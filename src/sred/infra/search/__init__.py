"""Search infrastructure contracts and adapters."""

from sred.infra.search.vector_sqlite import EmbeddingDimensionError, SqliteVecStore
from sred.infra.search.vector_store import EmbeddingRecord, QueryResult, VectorStore

__all__ = [
    "EmbeddingDimensionError",
    "EmbeddingRecord",
    "QueryResult",
    "SqliteVecStore",
    "VectorStore",
]
