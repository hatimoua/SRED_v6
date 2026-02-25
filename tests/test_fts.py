"""Regression tests for FTS incremental indexing (F1) and segment provenance (F2).

F1 — index_segments must be idempotent (calling it twice must not duplicate results).
F2 — create_text_segments() and process_csv_content() must set source_file_id.
"""
from __future__ import annotations

import pandas as pd
import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from sred.ingest.segment import create_text_segments, process_csv_content
from sred.models.core import File, Run, Segment
from sred.search.fts import index_segments, search_segments


# ---------------------------------------------------------------------------
# F1 — Idempotent FTS indexing
# ---------------------------------------------------------------------------

def test_index_segments_idempotent(use_test_engine):
    """Calling index_segments twice for the same segment must not duplicate results."""
    with Session(use_test_engine) as session:
        run = Run(name="FTS test")
        session.add(run)
        session.flush()

        f = File(
            run_id=run.id,
            original_filename="doc.txt",
            path="/tmp/doc.txt",
            file_type="text/plain",
            mime_type="text/plain",
            size_bytes=20,
            content_hash="fts-hash-1",
        )
        session.add(f)
        session.flush()

        seg = Segment(
            file_id=f.id,
            source_file_id=f.id,
            run_id=run.id,
            content="xylophone quantum unique phrase",
        )
        session.add(seg)
        session.commit()
        seg_id = seg.id

    # First index
    index_segments([seg_id])
    # Second index — must be idempotent, not a duplicate insert
    index_segments([seg_id])

    results = search_segments("xylophone quantum unique phrase")
    assert len(results) == 1, (
        f"Expected exactly 1 FTS hit after double-indexing, got {len(results)}"
    )
    assert results[0][0] == seg_id


def test_index_segments_empty_list_is_noop(use_test_engine):
    """index_segments([]) must return without error and leave FTS unchanged."""
    index_segments([])  # must not raise


def test_index_segments_batch_indexes_multiple(use_test_engine):
    """index_segments handles a batch of IDs in a single call."""
    with Session(use_test_engine) as session:
        run = Run(name="Batch test")
        session.add(run)
        session.flush()

        f = File(
            run_id=run.id,
            original_filename="batch.txt",
            path="/tmp/batch.txt",
            file_type="text/plain",
            mime_type="text/plain",
            size_bytes=10,
            content_hash="fts-hash-2",
        )
        session.add(f)
        session.flush()

        seg_a = Segment(file_id=f.id, source_file_id=f.id, run_id=run.id, content="alpha bravo charlie")
        seg_b = Segment(file_id=f.id, source_file_id=f.id, run_id=run.id, content="delta echo foxtrot")
        session.add_all([seg_a, seg_b])
        session.commit()
        ids = [seg_a.id, seg_b.id]

    index_segments(ids)

    assert len(search_segments("alpha bravo")) == 1
    assert len(search_segments("delta echo")) == 1


# ---------------------------------------------------------------------------
# F2 — source_file_id set on segment creation
# ---------------------------------------------------------------------------

@pytest.fixture(name="plain_session")
def plain_session_fixture():
    """In-memory session — no FTS needed for provenance tests."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _seed_run_and_file(session: Session, content_hash: str = "h1") -> tuple[Run, File]:
    run = Run(name="Provenance test")
    session.add(run)
    session.flush()
    f = File(
        run_id=run.id,
        original_filename="f.txt",
        path="/tmp/f.txt",
        file_type="text/plain",
        mime_type="text/plain",
        size_bytes=10,
        content_hash=content_hash,
    )
    session.add(f)
    session.flush()
    return run, f


def test_create_text_segments_sets_source_file_id(plain_session):
    """create_text_segments() must populate source_file_id = file.id on every segment."""
    _, f = _seed_run_and_file(plain_session, "h-txt")
    segs = create_text_segments(plain_session, f, "Hello world. " * 10)
    plain_session.commit()

    assert segs, "Expected at least one segment"
    for seg in segs:
        assert seg.source_file_id == f.id, (
            f"Segment {seg.id}: source_file_id={seg.source_file_id!r}, expected {f.id}"
        )


def test_process_csv_content_sets_source_file_id(plain_session):
    """process_csv_content() must populate source_file_id = file.id on every Segment."""
    _, f = _seed_run_and_file(plain_session, "h-csv")
    df = pd.DataFrame({"name": ["Alice", "Bob"], "hours": [8, 6]})
    process_csv_content(plain_session, f, df)
    plain_session.commit()

    segs = plain_session.exec(select(Segment).where(Segment.file_id == f.id)).all()
    assert len(segs) == 2
    for seg in segs:
        assert seg.source_file_id == f.id, (
            f"Segment {seg.id}: source_file_id={seg.source_file_id!r}, expected {f.id}"
        )
