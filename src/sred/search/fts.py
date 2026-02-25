from sqlalchemy import text
from sqlmodel import Session
from sred.db import engine
from sred.models.core import Segment
from sred.models.memory import MemoryDoc
from sred.logging import logger


def setup_fts():
    """Create FTS5 virtual tables and tracking tables if they don't exist."""
    with Session(engine) as session:
        # Segment FTS
        session.exec(text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS segment_fts USING fts5(
                id UNINDEXED,
                content,
                content='segment',
                content_rowid='id'
            );
        """))

        # MemoryDoc FTS
        session.exec(text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                id UNINDEXED,
                content_md,
                content='memorydoc',
                content_rowid='id'
            );
        """))

        # Tracking tables — record which rowids are currently in each FTS index.
        # Required because calling FTS5 'delete' on a rowid that was never inserted
        # causes "database disk image is malformed" (SQLite undefined behaviour).
        session.exec(text("""
            CREATE TABLE IF NOT EXISTS segment_fts_log (
                segment_id INTEGER PRIMARY KEY
            );
        """))
        session.exec(text("""
            CREATE TABLE IF NOT EXISTS memory_fts_log (
                memory_id INTEGER PRIMARY KEY
            );
        """))

        session.commit()


def reindex_all():
    """Rebuild FTS index from source tables.

    Drops and recreates the FTS5 virtual tables to handle corruption,
    then repopulates from the source tables. Also resets the tracking tables
    so that incremental indexing remains consistent.
    """
    logger.info("Reindexing FTS5 tables...")
    with Session(engine) as session:
        # Drop and recreate to handle any corruption
        session.exec(text("DROP TABLE IF EXISTS segment_fts;"))
        session.exec(text("DROP TABLE IF EXISTS memory_fts;"))
        session.commit()

    # Recreate the virtual tables (and ensure tracking tables exist)
    setup_fts()

    with Session(engine) as session:
        # Re-insert Segments
        session.exec(text("""
            INSERT INTO segment_fts(rowid, id, content)
            SELECT id, id, content FROM segment;
        """))

        # Re-insert MemoryDocs
        session.exec(text("""
            INSERT INTO memory_fts(rowid, id, content_md)
            SELECT id, id, content_md FROM memorydoc;
        """))

        # Sync tracking tables to match what is now in the FTS indices.
        session.exec(text("DELETE FROM segment_fts_log;"))
        session.exec(text(
            "INSERT OR IGNORE INTO segment_fts_log(segment_id) SELECT id FROM segment;"
        ))
        session.exec(text("DELETE FROM memory_fts_log;"))
        session.exec(text(
            "INSERT OR IGNORE INTO memory_fts_log(memory_id) SELECT id FROM memorydoc;"
        ))

        session.commit()
    logger.info("Reindexing complete.")


def index_segments(segment_ids: list[int]):
    """Incrementally index specific segments into the FTS index.

    Idempotent: calling this twice for the same segment is safe.

    Uses ``segment_fts_log`` to track which rowids are currently in the FTS
    index. FTS5 'delete' is only issued for rowids that are confirmed to be
    present; issuing 'delete' for a rowid that was never inserted causes SQLite
    to mark the database as malformed.

    Both the delete and insert steps are batched (one IN-list statement each)
    so the total number of SQL statements is at most 3 regardless of batch size.
    """
    if not segment_ids:
        return
    setup_fts()  # ensure virtual table and tracking table exist
    # Cast to int to prevent any injection; build inline IN list (integers only).
    ids_sql = ",".join(str(int(sid)) for sid in segment_ids)
    with Session(engine) as session:
        # Find which IDs are already in the FTS index (tracked in log table).
        already_indexed = {
            row[0]
            for row in session.exec(text(
                f"SELECT segment_id FROM segment_fts_log WHERE segment_id IN ({ids_sql})"
            )).all()
        }

        # Delete only the entries that are confirmed to be in the index.
        if already_indexed:
            del_sql = ",".join(str(x) for x in already_indexed)
            session.exec(text(f"""
                INSERT INTO segment_fts(segment_fts, rowid, id, content)
                SELECT 'delete', id, id, content FROM segment
                WHERE id IN ({del_sql})
            """))

        # Insert all requested segments (fresh or re-indexed).
        session.exec(text(f"""
            INSERT INTO segment_fts(rowid, id, content)
            SELECT id, id, content FROM segment
            WHERE id IN ({ids_sql})
        """))

        # Record newly indexed IDs in the tracking table.
        session.exec(text(f"""
            INSERT OR IGNORE INTO segment_fts_log(segment_id)
            SELECT id FROM segment WHERE id IN ({ids_sql})
        """))

        session.commit()
    logger.info(f"Indexed {len(segment_ids)} segment(s) into FTS.")


def index_memory(memory_id: int):
    """Incrementally insert a single MemoryDoc into the FTS index.

    Idempotent: safe to call multiple times for the same memory_id.
    Uses ``memory_fts_log`` to avoid calling FTS5 'delete' on a rowid
    that was never inserted (which would corrupt the FTS index).
    """
    setup_fts()
    with Session(engine) as session:
        # Only delete if this memory_id is already in the FTS index.
        already = session.exec(text(
            "SELECT 1 FROM memory_fts_log WHERE memory_id = :mid"
        ), params={"mid": memory_id}).first()

        if already:
            session.exec(text("""
                INSERT INTO memory_fts(memory_fts, rowid, id, content_md)
                SELECT 'delete', id, id, content_md FROM memorydoc
                WHERE id = :mid
            """), params={"mid": memory_id})

        # Insert fresh entry.
        session.exec(text("""
            INSERT INTO memory_fts(rowid, id, content_md)
            SELECT id, id, content_md FROM memorydoc
            WHERE id = :mid
        """), params={"mid": memory_id})

        # Track as indexed.
        session.exec(text(
            "INSERT OR IGNORE INTO memory_fts_log(memory_id) VALUES (:mid)"
        ), params={"mid": memory_id})

        session.commit()


def search_segments(query: str, limit: int = 10):
    with Session(engine) as session:
        results = session.exec(text(f"""
            SELECT id, snippet(segment_fts, 1, '<b>', '</b>', '...', 64)
            FROM segment_fts
            WHERE segment_fts MATCH :query
            ORDER BY rank
            LIMIT :limit
        """), params={"query": query, "limit": limit}).all()
        return results
