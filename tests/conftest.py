"""Shared test fixtures for Phase 2 FastAPI tests.

Existing tests (test_db.py, test_search_logic.py, etc.) create their own
engines and sessions — this conftest does not touch those.

New fixtures:
  use_test_engine  — redirects UoW + infra layer to a temp-file SQLite DB.
  client           — FastAPI TestClient wired to the test engine.
"""
import os
import pytest
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import text


def pytest_configure(config):
    """Set a dummy API key before any test modules are imported.

    sred.llm.openai_client creates an OpenAI() instance at module load time;
    without a key in the environment the import fails during pytest collection.
    Tests that actually call the OpenAI API must mock the client themselves.
    """
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-for-tests")


@pytest.fixture
def use_test_engine(tmp_path, monkeypatch):
    """Monkeypatch infra/db engine references to an isolated temp-file SQLite DB.

    Uses a file (not :memory:) so ingest tests can exercise filesystem paths.
    """
    db_path = tmp_path / "test_sred.db"
    test_engine = create_engine(f"sqlite:///{db_path}", echo=False)

    import sred.models  # noqa: F401 — register all ORM mappers
    SQLModel.metadata.create_all(test_engine)

    # Create FTS5 virtual tables
    with Session(test_engine) as s:
        s.exec(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS segment_fts "
            "USING fts5(id UNINDEXED, content, content='segment', content_rowid='id');"
        ))
        s.exec(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts "
            "USING fts5(id UNINDEXED, content_md, content='memorydoc', content_rowid='id');"
        ))
        s.exec(text(
            "CREATE TABLE IF NOT EXISTS segment_fts_log (segment_id INTEGER PRIMARY KEY);"
        ))
        s.exec(text(
            "CREATE TABLE IF NOT EXISTS memory_fts_log (memory_id INTEGER PRIMARY KEY);"
        ))
        s.commit()

    # Redirect all infra/db and FTS references to the test engine
    monkeypatch.setattr("sred.infra.db.engine.engine", test_engine)
    monkeypatch.setattr("sred.infra.db.uow.engine", test_engine)
    monkeypatch.setattr("sred.search.fts.engine", test_engine)

    yield test_engine

    SQLModel.metadata.drop_all(test_engine)
    test_engine.dispose()


@pytest.fixture
def client(use_test_engine):
    """FastAPI TestClient backed by the isolated test engine."""
    from fastapi.testclient import TestClient
    from sred.api.app import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c
