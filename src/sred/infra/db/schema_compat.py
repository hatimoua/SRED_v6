"""Runtime DB compatibility helpers for legacy SQLite schemas.

These helpers backfill additive schema changes for deployments that still rely
on ``SQLModel.metadata.create_all()`` instead of migrations.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

logger = logging.getLogger(__name__)


def ensure_schema_compat(engine: Engine) -> None:
    """Apply additive compatibility upgrades for existing SQLite databases."""
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as conn:
        _ensure_toolcalllog_thread_id(conn)


def _ensure_toolcalllog_thread_id(conn: Connection) -> None:
    if not _table_exists(conn, "toolcalllog"):
        return

    if not _column_exists(conn, "toolcalllog", "thread_id"):
        conn.execute(text("ALTER TABLE toolcalllog ADD COLUMN thread_id VARCHAR"))
        logger.info("Applied compatibility upgrade: added toolcalllog.thread_id")

    _ensure_index(conn, "ix_toolcalllog_thread_id", "toolcalllog", "thread_id")


def _table_exists(conn: Connection, table_name: str) -> bool:
    return (
        conn.execute(
            text(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = :name LIMIT 1"
            ),
            {"name": table_name},
        ).first()
        is not None
    )


def _column_exists(conn: Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(row[1] == column_name for row in rows)


def _ensure_index(
    conn: Connection, index_name: str, table_name: str, column_name: str
) -> None:
    exists = conn.execute(
        text(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'index' AND name = :name LIMIT 1"
        ),
        {"name": index_name},
    ).first()
    if exists is None:
        conn.execute(text(f"CREATE INDEX {index_name} ON {table_name} ({column_name})"))
