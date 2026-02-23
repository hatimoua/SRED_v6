"""SqliteSaver checkpoint factory and management utilities.

Provides ``get_checkpointer()`` to create a LangGraph SqliteSaver connected
to the configured checkpoint DB, and ``clear_checkpoints()`` to selectively
delete checkpoint data by run, thread, or everything.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from sred.config import settings


def get_checkpointer(db_path: Path | None = None) -> SqliteSaver:
    """Create a SqliteSaver connected to the checkpoint DB.

    The connection uses WAL journal mode for concurrent-read safety and
    ``check_same_thread=False`` so the saver can be shared across threads.
    """
    path = str(db_path or settings.CHECKPOINT_DB)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    saver = SqliteSaver(conn=conn)
    saver.setup()
    return saver


def clear_checkpoints(
    db_path: Path | None = None,
    run_id: int | None = None,
    session_id: str | None = None,
) -> int:
    """Delete checkpoint rows. Returns count of deleted rows.

    * ``run_id`` + ``session_id`` — delete the single thread
      ``"{run_id}:{session_id}"``.
    * ``run_id`` only — delete all threads matching ``"{run_id}:%"``.
    * Neither — delete **all** rows (full reset).
    """
    path = str(db_path or settings.CHECKPOINT_DB)
    conn = sqlite3.connect(path, check_same_thread=False)

    total = 0
    try:
        for table in ("checkpoints", "writes"):
            if not _table_exists(conn, table):
                continue

            if run_id is not None and session_id is not None:
                thread_id = f"{run_id}:{session_id}"
                cur = conn.execute(
                    f"DELETE FROM {table} WHERE thread_id = ?", (thread_id,)
                )
            elif run_id is not None:
                pattern = f"{run_id}:%"
                cur = conn.execute(
                    f"DELETE FROM {table} WHERE thread_id LIKE ?", (pattern,)
                )
            else:
                cur = conn.execute(f"DELETE FROM {table}")

            total += cur.rowcount

        conn.commit()
    finally:
        conn.close()

    return total


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """Check if a table exists in the SQLite database."""
    row = conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row and row[0])
