"""Tests for SqliteVecStore (sqlite-vec backed VectorStore)."""
from __future__ import annotations

import random
import time
import tempfile
from pathlib import Path

import numpy as np
import pytest

from sred.infra.search.vector_store import EmbeddingRecord, QueryResult
from sred.infra.search.vector_sqlite import SqliteVecStore


@pytest.fixture
def store() -> SqliteVecStore:
    """In-memory SqliteVecStore for tests."""
    s = SqliteVecStore(":memory:")
    yield s
    s.close()


# ---------------------------------------------------------------
# Contract tests (mirror test_vector_store_interface.py scenarios)
# ---------------------------------------------------------------


def test_upsert_and_query_small_dataset_returns_ranked_hits(store: SqliteVecStore):
    count = store.upsert_embeddings(
        [
            EmbeddingRecord(
                run_id=1, entity_id=101, embedding_model="text-embedding-3-large",
                vector=[1.0, 0.0], metadata={"segment_type": "timesheet"},
            ),
            EmbeddingRecord(
                run_id=1, entity_id=102, embedding_model="text-embedding-3-large",
                vector=[0.9, 0.1], metadata={"segment_type": "timesheet"},
            ),
            EmbeddingRecord(
                run_id=1, entity_id=103, embedding_model="text-embedding-3-large",
                vector=[-1.0, 0.0], metadata={"segment_type": "invoice"},
            ),
            EmbeddingRecord(
                run_id=2, entity_id=201, embedding_model="text-embedding-3-large",
                vector=[1.0, 0.0], metadata={"segment_type": "timesheet"},
            ),
        ]
    )
    assert count == 4

    hits = store.query(
        run_id=1, embedding_model="text-embedding-3-large",
        query_vector=[1.0, 0.0], top_k=2,
    )
    assert [h.entity_id for h in hits] == [101, 102]
    assert hits[0].score >= hits[1].score


def test_query_supports_metadata_filters(store: SqliteVecStore):
    store.upsert_embeddings(
        [
            EmbeddingRecord(
                run_id=1, entity_id=301, embedding_model="text-embedding-3-large",
                vector=[1.0, 0.0], metadata={"segment_type": "timesheet"},
            ),
            EmbeddingRecord(
                run_id=1, entity_id=302, embedding_model="text-embedding-3-large",
                vector=[1.0, 0.0], metadata={"segment_type": "invoice"},
            ),
        ]
    )

    hits = store.query(
        run_id=1, embedding_model="text-embedding-3-large",
        query_vector=[1.0, 0.0], filters={"segment_type": "timesheet"},
    )
    assert [h.entity_id for h in hits] == [301]


@pytest.mark.parametrize("invalid_top_k", [0, -1])
def test_query_rejects_non_positive_top_k(store: SqliteVecStore, invalid_top_k: int):
    store.upsert_embeddings(
        [
            EmbeddingRecord(
                run_id=1, entity_id=401, embedding_model="text-embedding-3-large",
                vector=[1.0, 0.0], metadata={"segment_type": "timesheet"},
            ),
        ]
    )
    with pytest.raises(ValueError, match="top_k must be >= 1"):
        store.query(
            run_id=1, embedding_model="text-embedding-3-large",
            query_vector=[1.0, 0.0], top_k=invalid_top_k,
        )


def test_delete_by_run_is_run_scoped(store: SqliteVecStore):
    store.upsert_embeddings(
        [
            EmbeddingRecord(run_id=1, entity_id=1, embedding_model="model-a", vector=[1.0, 0.0]),
            EmbeddingRecord(run_id=1, entity_id=2, embedding_model="model-a", vector=[0.0, 1.0]),
            EmbeddingRecord(run_id=2, entity_id=3, embedding_model="model-a", vector=[1.0, 0.0]),
        ]
    )

    deleted = store.delete_by_run(1)
    assert deleted == 2

    assert store.query(run_id=1, embedding_model="model-a", query_vector=[1.0, 0.0]) == []
    assert [h.entity_id for h in store.query(run_id=2, embedding_model="model-a", query_vector=[1.0, 0.0])] == [3]


def test_rebuild_index_keeps_queryability(store: SqliteVecStore):
    store.upsert_embeddings(
        [
            EmbeddingRecord(run_id=7, entity_id=70, embedding_model="model-a", vector=[1.0, 0.0]),
            EmbeddingRecord(run_id=7, entity_id=71, embedding_model="model-a", vector=[0.0, 1.0]),
        ]
    )
    before = store.query(run_id=7, embedding_model="model-a", query_vector=[1.0, 0.0])
    store.rebuild_index(run_id=7)
    after = store.query(run_id=7, embedding_model="model-a", query_vector=[1.0, 0.0])
    assert [h.entity_id for h in before] == [h.entity_id for h in after]


# ---------------------------------------------------------------
# sqlite-vec specific tests
# ---------------------------------------------------------------


def test_benchmark_10k_vectors_query_under_50ms(store: SqliteVecStore):
    """Insert 10k 128-dim vectors and assert KNN query is fast."""
    rng = random.Random(42)
    records = [
        EmbeddingRecord(
            run_id=1, entity_id=i, embedding_model="bench",
            vector=[rng.gauss(0, 1) for _ in range(128)],
        )
        for i in range(10_000)
    ]
    store.upsert_embeddings(records)

    query_vec = [rng.gauss(0, 1) for _ in range(128)]
    t0 = time.perf_counter()
    hits = store.query(run_id=1, embedding_model="bench", query_vector=query_vec, top_k=10)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert len(hits) == 10
    assert elapsed_ms < 50, f"Query took {elapsed_ms:.1f}ms, expected < 50ms"


def test_multi_dimension_vectors(store: SqliteVecStore):
    """128-dim and 4-dim vectors stored and queried independently."""
    store.upsert_embeddings(
        [
            EmbeddingRecord(run_id=1, entity_id=1, embedding_model="small", vector=[1.0, 0.0, 0.0, 0.0]),
            EmbeddingRecord(run_id=1, entity_id=2, embedding_model="big", vector=[1.0] + [0.0] * 127),
        ]
    )

    hits_small = store.query(run_id=1, embedding_model="small", query_vector=[1.0, 0.0, 0.0, 0.0], top_k=5)
    hits_big = store.query(run_id=1, embedding_model="big", query_vector=[1.0] + [0.0] * 127, top_k=5)

    assert [h.entity_id for h in hits_small] == [1]
    assert [h.entity_id for h in hits_big] == [2]


def test_persistence_across_close_reopen(tmp_path: Path):
    """Data survives close + reopen from same file."""
    db_file = tmp_path / "vec.db"
    s1 = SqliteVecStore(db_file)
    s1.upsert_embeddings(
        [EmbeddingRecord(run_id=1, entity_id=42, embedding_model="m", vector=[1.0, 0.0])]
    )
    s1.close()

    s2 = SqliteVecStore(db_file)
    hits = s2.query(run_id=1, embedding_model="m", query_vector=[1.0, 0.0], top_k=5)
    s2.close()

    assert [h.entity_id for h in hits] == [42]


def test_upsert_idempotency(store: SqliteVecStore):
    """Inserting the same entity_id twice keeps only the latest vector."""
    store.upsert_embeddings(
        [EmbeddingRecord(run_id=1, entity_id=1, embedding_model="m", vector=[1.0, 0.0])]
    )
    store.upsert_embeddings(
        [EmbeddingRecord(run_id=1, entity_id=1, embedding_model="m", vector=[0.0, 1.0])]
    )

    hits = store.query(run_id=1, embedding_model="m", query_vector=[0.0, 1.0], top_k=5)
    assert len(hits) == 1
    assert hits[0].entity_id == 1
    # Score should be ~1.0 (exact match with [0,1]), not matching old [1,0].
    assert hits[0].score > 0.99


def test_empty_query_returns_empty(store: SqliteVecStore):
    """Query with no matching run_id returns empty list."""
    store.upsert_embeddings(
        [EmbeddingRecord(run_id=1, entity_id=1, embedding_model="m", vector=[1.0, 0.0])]
    )
    hits = store.query(run_id=999, embedding_model="m", query_vector=[1.0, 0.0])
    assert hits == []


def test_query_nonexistent_dimension_returns_empty(store: SqliteVecStore):
    """Query for a dimension that has no table returns empty list."""
    store.upsert_embeddings(
        [EmbeddingRecord(run_id=1, entity_id=1, embedding_model="m", vector=[1.0, 0.0])]
    )
    # Query with 4-dim vector — no vec_idx_4 table exists.
    hits = store.query(run_id=1, embedding_model="m", query_vector=[1.0, 0.0, 0.0, 0.0])
    assert hits == []


def test_score_clamped_non_negative_for_anti_correlated_vectors(store: SqliteVecStore):
    """Score is clamped to >= 0 even for vectors pointing in opposite directions.

    Cosine distance ranges [0, 2]; subtracting from 1.0 can yield negative
    values for anti-correlated pairs.  The clamp ensures callers always
    receive scores in [0, 1].
    """
    store.upsert_embeddings(
        [EmbeddingRecord(run_id=1, entity_id=1, embedding_model="m", vector=[1.0, 0.0])]
    )
    # Query with perfectly anti-correlated vector — cosine distance == 2.0
    hits = store.query(run_id=1, embedding_model="m", query_vector=[-1.0, 0.0], top_k=5)
    assert len(hits) == 1
    assert hits[0].score >= 0.0
