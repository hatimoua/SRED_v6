from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text

from sred.infra.db.schema_compat import ensure_schema_compat


def _column_names(db_path: Path, table_name: str) -> set[str]:
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def _index_names(db_path: Path, table_name: str) -> set[str]:
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA index_list({table_name})")).fetchall()
    return {row[1] for row in rows}


def test_ensure_schema_compat_adds_toolcalllog_thread_id_for_legacy_db(tmp_path):
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE toolcalllog (
                    id INTEGER PRIMARY KEY,
                    run_id INTEGER NOT NULL,
                    session_id VARCHAR,
                    tool_name VARCHAR NOT NULL,
                    arguments_json VARCHAR NOT NULL,
                    result_json VARCHAR NOT NULL,
                    success BOOLEAN NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )

    ensure_schema_compat(engine)

    assert "thread_id" in _column_names(db_path, "toolcalllog")
    assert "ix_toolcalllog_thread_id" in _index_names(db_path, "toolcalllog")

    # idempotent: running again should not fail and should keep schema intact
    ensure_schema_compat(engine)
    assert "thread_id" in _column_names(db_path, "toolcalllog")
