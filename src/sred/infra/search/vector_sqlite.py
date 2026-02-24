"""sqlite-vec backed VectorStore implementation."""
from __future__ import annotations

import json
import sqlite3
import struct
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import sqlite_vec

from sred.infra.search.vector_store import EmbeddingRecord, QueryResult, VectorStore

# Over-fetch factor for KNN pre-filter (post-filter narrows by run_id/model).
_OVERFETCH = 4


def _serialize_f32(vector: Sequence[float]) -> bytes:
    """Pack a float vector into little-endian binary (sqlite-vec format)."""
    return struct.pack(f"{len(vector)}f", *vector)


class SqliteVecStore(VectorStore):
    """VectorStore backed by the sqlite-vec extension (vec0 virtual tables).

    Uses a **dedicated** raw sqlite3 connection (not the SQLModel engine)
    because vec0 requires ``enable_load_extension(True)``.

    Two-table pattern per dimension:
    * ``vec_meta`` — regular table for metadata (run_id, entity_id, …)
    * ``vec_idx_{dim}`` — vec0 virtual table with fixed-dimension vectors

    Rows are aligned by rowid between the two tables.
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.enable_load_extension(True)
        sqlite_vec.load(self._conn)
        self._conn.enable_load_extension(False)

        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vec_meta (
                id         INTEGER PRIMARY KEY,
                run_id     INTEGER NOT NULL,
                entity_id  INTEGER NOT NULL,
                embedding_model TEXT NOT NULL,
                dim        INTEGER NOT NULL,
                metadata   TEXT NOT NULL DEFAULT '{}',
                UNIQUE(run_id, embedding_model, entity_id)
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_vec_meta_run_model "
            "ON vec_meta(run_id, embedding_model)"
        )
        self._conn.commit()

        # Track which vec_idx_{dim} tables already exist.
        self._known_dims: set[int] = set()
        for (name,) in self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'vec_idx_%'"
        ).fetchall():
            try:
                self._known_dims.add(int(name.split("vec_idx_")[1]))
            except (IndexError, ValueError):
                pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_dim_table(self, dim: int) -> None:
        if dim in self._known_dims:
            return
        self._conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_idx_{dim} "
            f"USING vec0(embedding float[{dim}] distance_metric=cosine)"
        )
        self._conn.commit()
        self._known_dims.add(dim)

    # ------------------------------------------------------------------
    # VectorStore interface
    # ------------------------------------------------------------------

    def upsert_embeddings(self, records: Sequence[EmbeddingRecord]) -> int:
        if not records:
            return 0

        # Group by dimension so we can ensure tables exist.
        dims_seen: set[int] = set()
        for rec in records:
            dim = len(rec.vector)
            if dim not in dims_seen:
                self._ensure_dim_table(dim)
                dims_seen.add(dim)

        count = 0
        for rec in records:
            dim = len(rec.vector)
            meta_json = json.dumps(dict(rec.metadata)) if rec.metadata else "{}"

            # Check if this (run_id, embedding_model, entity_id) already exists.
            existing = self._conn.execute(
                "SELECT id, dim FROM vec_meta "
                "WHERE run_id = ? AND embedding_model = ? AND entity_id = ?",
                (rec.run_id, rec.embedding_model, rec.entity_id),
            ).fetchone()

            if existing is not None:
                rowid, old_dim = existing
                # Delete old vector (possibly from a different dim table).
                self._conn.execute(
                    f"DELETE FROM vec_idx_{old_dim} WHERE rowid = ?", (rowid,)
                )
                # Update meta row.
                self._conn.execute(
                    "UPDATE vec_meta SET dim = ?, metadata = ? WHERE id = ?",
                    (dim, meta_json, rowid),
                )
                # Insert new vector.
                self._conn.execute(
                    f"INSERT INTO vec_idx_{dim}(rowid, embedding) VALUES (?, ?)",
                    (rowid, _serialize_f32(rec.vector)),
                )
            else:
                # Insert new meta row — let SQLite assign the rowid.
                cur = self._conn.execute(
                    "INSERT INTO vec_meta(run_id, entity_id, embedding_model, dim, metadata) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (rec.run_id, rec.entity_id, rec.embedding_model, dim, meta_json),
                )
                rowid = cur.lastrowid
                self._conn.execute(
                    f"INSERT INTO vec_idx_{dim}(rowid, embedding) VALUES (?, ?)",
                    (rowid, _serialize_f32(rec.vector)),
                )
            count += 1

        self._conn.commit()
        return count

    def query(
        self,
        *,
        run_id: int,
        embedding_model: str,
        query_vector: Sequence[float],
        top_k: int = 10,
        filters: Mapping[str, Any] | None = None,
    ) -> list[QueryResult]:
        if top_k <= 0:
            raise ValueError("top_k must be >= 1.")

        dim = len(query_vector)
        if dim not in self._known_dims:
            return []

        # Over-fetch to account for post-filtering by run_id / model / metadata.
        fetch_k = top_k * _OVERFETCH

        knn_rows = self._conn.execute(
            f"SELECT rowid, distance FROM vec_idx_{dim} "
            "WHERE embedding MATCH ? AND k = ? ORDER BY distance",
            (_serialize_f32(query_vector), fetch_k),
        ).fetchall()

        if not knn_rows:
            return []

        # Bulk-fetch metadata for candidate rowids.
        rowid_list = [r[0] for r in knn_rows]
        distance_map = {r[0]: r[1] for r in knn_rows}

        placeholders = ",".join("?" * len(rowid_list))
        meta_rows = self._conn.execute(
            f"SELECT id, run_id, entity_id, embedding_model, metadata "
            f"FROM vec_meta WHERE id IN ({placeholders}) "
            f"AND run_id = ? AND embedding_model = ?",
            (*rowid_list, run_id, embedding_model),
        ).fetchall()

        results: list[QueryResult] = []
        for mid, mrun, mentity, mmodel, mmeta_json in meta_rows:
            meta: dict[str, Any] = json.loads(mmeta_json) if mmeta_json else {}
            # Apply optional metadata filters.
            if filters and any(meta.get(k) != v for k, v in filters.items()):
                continue
            results.append(
                QueryResult(
                    run_id=mrun,
                    entity_id=mentity,
                    embedding_model=mmodel,
                    score=1.0 - distance_map[mid],
                    metadata=meta,
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def delete_by_run(self, run_id: int) -> int:
        # Find all rows for this run, grouped by dimension.
        rows = self._conn.execute(
            "SELECT id, dim FROM vec_meta WHERE run_id = ?", (run_id,)
        ).fetchall()
        if not rows:
            return 0

        # Group by dim for batch deletes.
        by_dim: dict[int, list[int]] = {}
        for rowid, dim in rows:
            by_dim.setdefault(dim, []).append(rowid)

        for dim, rowids in by_dim.items():
            placeholders = ",".join("?" * len(rowids))
            self._conn.execute(
                f"DELETE FROM vec_idx_{dim} WHERE rowid IN ({placeholders})", rowids
            )

        self._conn.execute("DELETE FROM vec_meta WHERE run_id = ?", (run_id,))
        self._conn.commit()
        return len(rows)

    def rebuild_index(self, *, run_id: int | None = None) -> None:
        # vec0 maintains its own index automatically — nothing to do.
        pass

    def close(self) -> None:
        """Close the underlying sqlite3 connection."""
        self._conn.close()
