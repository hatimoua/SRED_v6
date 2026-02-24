import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from sred.search.embeddings import compute_text_hash, store_embeddings
from sred.search.vector_search import cosine_similarity, search_vectors
from sred.search.hybrid_search import (
    rrf_fusion, SearchResult, vector_search_wrapper, hybrid_search, EntityType,
)
from sred.infra.search.vector_store import QueryResult, VectorStore
from sred.models.core import Run, Segment
from sred.models.vector import VectorEmbedding
from sqlmodel import Session, SQLModel, create_engine
from sred.logging import logger


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_hash():
    assert compute_text_hash("test") == "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"


def test_cosine():
    v1 = np.array([1, 0], dtype=np.float32)
    v2 = np.array([1, 0], dtype=np.float32)
    assert cosine_similarity(v1, v2) > 0.99

    v3 = np.array([0, 1], dtype=np.float32)
    assert cosine_similarity(v1, v3) < 0.01


def test_vector_storage(session):
    run = Run(name="Test")
    session.add(run)
    session.commit()

    # Mock OpenAI
    with patch("sred.search.embeddings.get_embeddings_from_openai") as mock_openai:
        mock_openai.return_value = [[0.1, 0.2], [0.3, 0.4]]

        texts = ["A", "B"]
        ids = [1, 2]
        store_embeddings(session, texts, ids, EntityType.SEGMENT, run.id)

        # Check DB
        vecs = session.query(VectorEmbedding).all()
        assert len(vecs) == 2

        # Check caching (should not call openai again)
        mock_openai.reset_mock()
        store_embeddings(session, texts, ids, EntityType.SEGMENT, run.id)
        mock_openai.assert_not_called()


def test_rrf():
    # Setup hits
    fts = [SearchResult(id=1, content="A", score=0, source="FTS", rank_fts=1)]
    vec = [SearchResult(id=1, content="A", score=0.9, source="VEC", rank_vector=1)]

    fused = rrf_fusion(fts, vec, k=1)
    # Score for ID 1: 1/(1+1) + 1/(1+1) = 0.5 + 0.5 = 1.0
    assert len(fused) == 1
    assert fused[0].id == 1
    assert abs(fused[0].score - 1.0) < 0.001


def test_vector_search_wrapper_with_vector_store(session):
    """vector_search_wrapper delegates to VectorStore.query() when provided."""
    # Seed a Segment so session.get(Segment, ...) succeeds.
    run = Run(name="Test")
    session.add(run)
    session.flush()

    from sred.models.core import File

    f = File(
        run_id=run.id,
        original_filename="test.txt",
        path="/tmp/test.txt",
        file_type="text/plain",
        mime_type="text/plain",
        size_bytes=100,
        content_hash="abc123",
    )
    session.add(f)
    session.flush()

    seg = Segment(file_id=f.id, run_id=run.id, content="Hello world segment")
    session.add(seg)
    session.commit()

    mock_store = MagicMock(spec=VectorStore)
    mock_store.query.return_value = [
        QueryResult(
            run_id=run.id,
            entity_id=seg.id,
            embedding_model="text-embedding-3-large",
            score=0.85,
            metadata={},
        ),
    ]

    with patch("sred.search.hybrid_search.get_query_embedding", return_value=[0.1, 0.2]):
        results = vector_search_wrapper(
            session, "hello", run.id, limit=5, vector_store=mock_store
        )

    mock_store.query.assert_called_once()
    assert len(results) == 1
    assert results[0].id == seg.id
    assert results[0].score == 0.85
    assert results[0].source == "VECTOR"
    assert results[0].rank_vector == 1


def test_hybrid_search_with_vector_store(session):
    """hybrid_search combines FTS and VectorStore results via RRF."""
    run = Run(name="Test")
    session.add(run)
    session.flush()

    from sred.models.core import File

    f = File(
        run_id=run.id,
        original_filename="test.txt",
        path="/tmp/test.txt",
        file_type="text/plain",
        mime_type="text/plain",
        size_bytes=100,
        content_hash="abc123",
    )
    session.add(f)
    session.flush()

    seg1 = Segment(file_id=f.id, run_id=run.id, content="Segment one")
    seg2 = Segment(file_id=f.id, run_id=run.id, content="Segment two")
    session.add_all([seg1, seg2])
    session.commit()

    mock_store = MagicMock(spec=VectorStore)
    mock_store.query.return_value = [
        QueryResult(
            run_id=run.id,
            entity_id=seg1.id,
            embedding_model="text-embedding-3-large",
            score=0.9,
            metadata={},
        ),
        QueryResult(
            run_id=run.id,
            entity_id=seg2.id,
            embedding_model="text-embedding-3-large",
            score=0.7,
            metadata={},
        ),
    ]

    # Mock FTS to return seg1 only
    fts_results = [
        SearchResult(id=seg1.id, content="Segment one", score=0, source="FTS", rank_fts=1),
    ]

    with (
        patch("sred.search.hybrid_search.get_query_embedding", return_value=[0.1, 0.2]),
        patch("sred.search.hybrid_search.search_segments", return_value=[(seg1.id, "Segment one")]),
    ):
        results = hybrid_search(
            session, "test query", run.id, limit=5, vector_store=mock_store
        )

    # seg1 should appear (from both FTS and vector → higher RRF score)
    # seg2 should appear (from vector only)
    assert len(results) == 2
    assert results[0].id == seg1.id  # higher combined score
    assert results[0].source == "HYBRID"
    assert results[0].score > results[1].score
    assert results[1].id == seg2.id
