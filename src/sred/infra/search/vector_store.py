"""VectorStore contract used by semantic retrieval backends."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class EmbeddingRecord:
    """One embedding row stored in a vector backend."""

    run_id: int
    entity_id: int
    embedding_model: str
    vector: Sequence[float]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class QueryResult:
    """One scored hit returned by a vector query."""

    run_id: int
    entity_id: int
    embedding_model: str
    score: float
    metadata: Mapping[str, Any] = field(default_factory=dict)


class VectorStore(ABC):
    """Abstract interface for vector indexing and retrieval."""

    @abstractmethod
    def upsert_embeddings(self, records: Sequence[EmbeddingRecord]) -> int:
        """Insert or update embeddings and return number of processed records."""

    @abstractmethod
    def query(
        self,
        *,
        run_id: int,
        embedding_model: str,
        query_vector: Sequence[float],
        top_k: int = 10,
        filters: Mapping[str, Any] | None = None,
    ) -> list[QueryResult]:
        """Return top-k ranked results for one run/model, optionally filtered by metadata."""

    @abstractmethod
    def delete_by_run(self, run_id: int) -> int:
        """Delete all embeddings for a run and return deleted row count."""

    @abstractmethod
    def rebuild_index(self, *, run_id: int | None = None) -> None:
        """Rebuild the backend index globally or for one run."""
