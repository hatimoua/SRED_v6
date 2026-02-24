"""Search infrastructure contracts and adapters."""

from sred.infra.search.vector_sqlite import SqliteVecStore
from sred.infra.search.vector_store import EmbeddingRecord, QueryResult, VectorStore

__all__ = [
    "EmbeddingRecord",
    "QueryResult",
    "SqliteVecStore",
    "VectorStore",
]
