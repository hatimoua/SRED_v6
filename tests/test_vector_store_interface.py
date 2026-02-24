"""Baseline tests for the VectorStore interface contract."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pytest

from sred.infra.search.vector_store import EmbeddingRecord, QueryResult, VectorStore


def _cosine_score(left: Sequence[float], right: Sequence[float]) -> float:
    left_arr = np.asarray(left, dtype=np.float32)
    right_arr = np.asarray(right, dtype=np.float32)
    if left_arr.shape != right_arr.shape:
        raise ValueError("Vector dimensions must match for cosine similarity.")
    denom = float(np.linalg.norm(left_arr) * np.linalg.norm(right_arr))
    if denom == 0.0:
        return 0.0
    return float(np.dot(left_arr, right_arr) / denom)


class InMemoryVectorStore(VectorStore):
    """Small in-memory implementation used only for baseline contract tests."""

    def __init__(self) -> None:
        self._rows: dict[tuple[int, str, int], EmbeddingRecord] = {}
        self.rebuild_calls: list[int | None] = []

    def upsert_embeddings(self, records: Sequence[EmbeddingRecord]) -> int:
        for record in records:
            key = (record.run_id, record.embedding_model, record.entity_id)
            self._rows[key] = record
        return len(records)

    def query(
        self,
        *,
        run_id: int,
        embedding_model: str,
        query_vector: Sequence[float],
        top_k: int = 10,
        filters: Mapping[str, object] | None = None,
    ) -> list[QueryResult]:
        if top_k <= 0:
            raise ValueError("top_k must be >= 1.")

        hits: list[QueryResult] = []
        for record in self._rows.values():
            if record.run_id != run_id or record.embedding_model != embedding_model:
                continue
            if filters:
                if any(record.metadata.get(key) != value for key, value in filters.items()):
                    continue
            hits.append(
                QueryResult(
                    run_id=record.run_id,
                    entity_id=record.entity_id,
                    embedding_model=record.embedding_model,
                    score=_cosine_score(query_vector, record.vector),
                    metadata=record.metadata,
                )
            )

        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[:top_k]

    def delete_by_run(self, run_id: int) -> int:
        keys = [key for key in self._rows if key[0] == run_id]
        for key in keys:
            del self._rows[key]
        return len(keys)

    def rebuild_index(self, *, run_id: int | None = None) -> None:
        self.rebuild_calls.append(run_id)

    def close(self) -> None:
        pass


def test_vector_store_contract_has_required_methods():
    required = {"upsert_embeddings", "query", "delete_by_run", "rebuild_index", "close"}
    assert required.issubset(VectorStore.__abstractmethods__)


def test_upsert_and_query_small_dataset_returns_ranked_hits():
    store = InMemoryVectorStore()
    count = store.upsert_embeddings(
        [
            EmbeddingRecord(
                run_id=1,
                entity_id=101,
                embedding_model="text-embedding-3-large",
                vector=[1.0, 0.0],
                metadata={"segment_type": "timesheet"},
            ),
            EmbeddingRecord(
                run_id=1,
                entity_id=102,
                embedding_model="text-embedding-3-large",
                vector=[0.9, 0.1],
                metadata={"segment_type": "timesheet"},
            ),
            EmbeddingRecord(
                run_id=1,
                entity_id=103,
                embedding_model="text-embedding-3-large",
                vector=[-1.0, 0.0],
                metadata={"segment_type": "invoice"},
            ),
            EmbeddingRecord(
                run_id=2,
                entity_id=201,
                embedding_model="text-embedding-3-large",
                vector=[1.0, 0.0],
                metadata={"segment_type": "timesheet"},
            ),
        ]
    )
    assert count == 4

    hits = store.query(
        run_id=1,
        embedding_model="text-embedding-3-large",
        query_vector=[1.0, 0.0],
        top_k=2,
    )

    assert [hit.entity_id for hit in hits] == [101, 102]
    assert hits[0].score >= hits[1].score


def test_query_supports_metadata_filters():
    store = InMemoryVectorStore()
    store.upsert_embeddings(
        [
            EmbeddingRecord(
                run_id=1,
                entity_id=301,
                embedding_model="text-embedding-3-large",
                vector=[1.0, 0.0],
                metadata={"segment_type": "timesheet"},
            ),
            EmbeddingRecord(
                run_id=1,
                entity_id=302,
                embedding_model="text-embedding-3-large",
                vector=[1.0, 0.0],
                metadata={"segment_type": "invoice"},
            ),
        ]
    )

    hits = store.query(
        run_id=1,
        embedding_model="text-embedding-3-large",
        query_vector=[1.0, 0.0],
        filters={"segment_type": "timesheet"},
    )
    assert [hit.entity_id for hit in hits] == [301]


@pytest.mark.parametrize("invalid_top_k", [0, -1])
def test_query_rejects_non_positive_top_k(invalid_top_k: int):
    store = InMemoryVectorStore()
    store.upsert_embeddings(
        [
            EmbeddingRecord(
                run_id=1,
                entity_id=401,
                embedding_model="text-embedding-3-large",
                vector=[1.0, 0.0],
                metadata={"segment_type": "timesheet"},
            ),
        ]
    )

    with pytest.raises(ValueError, match="top_k must be >= 1"):
        store.query(
            run_id=1,
            embedding_model="text-embedding-3-large",
            query_vector=[1.0, 0.0],
            top_k=invalid_top_k,
        )


def test_delete_by_run_is_run_scoped():
    store = InMemoryVectorStore()
    store.upsert_embeddings(
        [
            EmbeddingRecord(run_id=1, entity_id=1, embedding_model="model-a", vector=[1.0, 0.0]),
            EmbeddingRecord(run_id=1, entity_id=2, embedding_model="model-a", vector=[0.0, 1.0]),
            EmbeddingRecord(run_id=2, entity_id=3, embedding_model="model-a", vector=[1.0, 0.0]),
        ]
    )

    deleted = store.delete_by_run(1)
    assert deleted == 2

    run_1_hits = store.query(
        run_id=1,
        embedding_model="model-a",
        query_vector=[1.0, 0.0],
    )
    run_2_hits = store.query(
        run_id=2,
        embedding_model="model-a",
        query_vector=[1.0, 0.0],
    )

    assert run_1_hits == []
    assert [hit.entity_id for hit in run_2_hits] == [3]


def test_rebuild_index_keeps_queryability():
    store = InMemoryVectorStore()
    store.upsert_embeddings(
        [
            EmbeddingRecord(run_id=7, entity_id=70, embedding_model="model-a", vector=[1.0, 0.0]),
            EmbeddingRecord(run_id=7, entity_id=71, embedding_model="model-a", vector=[0.0, 1.0]),
        ]
    )

    before = store.query(
        run_id=7,
        embedding_model="model-a",
        query_vector=[1.0, 0.0],
    )
    store.rebuild_index(run_id=7)
    after = store.query(
        run_id=7,
        embedding_model="model-a",
        query_vector=[1.0, 0.0],
    )

    assert store.rebuild_calls == [7]
    assert [item.entity_id for item in before] == [item.entity_id for item in after]
