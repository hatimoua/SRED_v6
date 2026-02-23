"""Tests for LangGraph SqliteSaver checkpointing (Phase 4.2)."""

from __future__ import annotations

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata

from sred.orchestration.checkpointer import get_checkpointer, clear_checkpoints


def _make_config(thread_id: str, checkpoint_ns: str = "", checkpoint_id: str = ""):
    """Build a minimal RunnableConfig for the checkpointer."""
    return {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "checkpoint_id": checkpoint_id,
        }
    }


def _empty_checkpoint(checkpoint_id: str = "1") -> Checkpoint:
    return Checkpoint(
        v=1,
        id=checkpoint_id,
        ts="2026-01-01T00:00:00+00:00",
        channel_values={},
        channel_versions={},
        versions_seen={},
        pending_sends=[],
    )


# -------------------------------------------------------------------
# 1. get_checkpointer returns SqliteSaver
# -------------------------------------------------------------------
def test_get_checkpointer_returns_sqlite_saver(tmp_path):
    db = tmp_path / "cp.db"
    saver = get_checkpointer(db_path=db)
    assert isinstance(saver, SqliteSaver)
    saver.conn.close()


# -------------------------------------------------------------------
# 2. Checkpoint roundtrip — put then get
# -------------------------------------------------------------------
def test_checkpoint_roundtrip(tmp_path):
    db = tmp_path / "cp.db"
    saver = get_checkpointer(db_path=db)
    config = _make_config("1:abc")
    cp = _empty_checkpoint("chk-1")
    metadata = CheckpointMetadata()

    saver.put(config, cp, metadata, {})
    got = saver.get_tuple(config)

    assert got is not None
    assert got.checkpoint["id"] == "chk-1"
    saver.conn.close()


# -------------------------------------------------------------------
# 3. Resume — latest checkpoint returned for same thread
# -------------------------------------------------------------------
def test_resume_returns_latest(tmp_path):
    db = tmp_path / "cp.db"
    saver = get_checkpointer(db_path=db)
    config = _make_config("1:abc")

    cp1 = _empty_checkpoint("chk-1")
    cp2 = _empty_checkpoint("chk-2")

    saver.put(config, cp1, CheckpointMetadata(), {})
    saver.put(config, cp2, CheckpointMetadata(), {})

    got = saver.get_tuple(config)
    assert got is not None
    assert got.checkpoint["id"] == "chk-2"
    saver.conn.close()


# -------------------------------------------------------------------
# 4. clear_checkpoints by run_id
# -------------------------------------------------------------------
def test_clear_by_run_id(tmp_path):
    db = tmp_path / "cp.db"
    saver = get_checkpointer(db_path=db)

    saver.put(_make_config("1:a"), _empty_checkpoint("c1"), CheckpointMetadata(), {})
    saver.put(_make_config("1:b"), _empty_checkpoint("c2"), CheckpointMetadata(), {})
    saver.put(_make_config("2:a"), _empty_checkpoint("c3"), CheckpointMetadata(), {})

    deleted = clear_checkpoints(db_path=db, run_id=1)
    assert deleted > 0

    # run 1 threads gone
    assert saver.get_tuple(_make_config("1:a")) is None
    assert saver.get_tuple(_make_config("1:b")) is None
    # run 2 survives
    assert saver.get_tuple(_make_config("2:a")) is not None
    saver.conn.close()


# -------------------------------------------------------------------
# 5. clear_checkpoints by specific thread
# -------------------------------------------------------------------
def test_clear_by_thread(tmp_path):
    db = tmp_path / "cp.db"
    saver = get_checkpointer(db_path=db)

    saver.put(_make_config("1:a"), _empty_checkpoint("c1"), CheckpointMetadata(), {})
    saver.put(_make_config("1:b"), _empty_checkpoint("c2"), CheckpointMetadata(), {})

    deleted = clear_checkpoints(db_path=db, run_id=1, session_id="a")
    assert deleted > 0

    assert saver.get_tuple(_make_config("1:a")) is None
    assert saver.get_tuple(_make_config("1:b")) is not None
    saver.conn.close()


# -------------------------------------------------------------------
# 6. clear_checkpoints all
# -------------------------------------------------------------------
def test_clear_all(tmp_path):
    db = tmp_path / "cp.db"
    saver = get_checkpointer(db_path=db)

    saver.put(_make_config("1:a"), _empty_checkpoint("c1"), CheckpointMetadata(), {})
    saver.put(_make_config("2:b"), _empty_checkpoint("c2"), CheckpointMetadata(), {})

    deleted = clear_checkpoints(db_path=db)
    assert deleted > 0

    assert saver.get_tuple(_make_config("1:a")) is None
    assert saver.get_tuple(_make_config("2:b")) is None
    saver.conn.close()


# -------------------------------------------------------------------
# 7. WAL mode enabled on checkpoint DB
# -------------------------------------------------------------------
def test_wal_mode(tmp_path):
    db = tmp_path / "cp.db"
    saver = get_checkpointer(db_path=db)

    journal = saver.conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert journal == "wal"
    saver.conn.close()


# -------------------------------------------------------------------
# 8. saver.setup() creates exactly 'checkpoints' and 'writes' tables
#    (locks in the real table names for langgraph-checkpoint-sqlite==3.0.3)
# -------------------------------------------------------------------
def test_setup_creates_expected_tables(tmp_path):
    db = tmp_path / "cp.db"
    conn = sqlite3.connect(str(db))
    saver = SqliteSaver(conn=conn)
    saver.setup()

    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()

    assert "checkpoints" in tables, f"'checkpoints' table missing; got {tables}"
    assert "writes" in tables, f"'writes' table missing; got {tables}"
