"""The candidate cache — a SQLite store for bulk enrichment.

Everything fetched from a source (OpenAlex) lands here: candidate nodes and the
edges between them. It's derived data you own permanently, kept separate from
the curated vault so automation never floods your files. The graph engine is
built from the vault (truth) plus this cache (candidates + edges).

The connection is shared across threads and guarded by a lock, so concurrent
access is serialised and safe.
"""
from __future__ import annotations

import json
import sqlite3
import threading

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes(
    key TEXT PRIMARY KEY,
    type TEXT,
    title TEXT,
    meta TEXT,
    source TEXT
);
CREATE TABLE IF NOT EXISTS edges(
    src TEXT,
    dst TEXT,
    rel TEXT,
    source TEXT,
    PRIMARY KEY (src, dst, rel)
);
CREATE TABLE IF NOT EXISTS embeddings(
    key TEXT PRIMARY KEY,
    vec TEXT
);
"""


class Cache:
    def __init__(self, path=":memory:") -> None:
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self.conn.executescript(_SCHEMA)
            self.conn.commit()

    # --- nodes ---
    def upsert_node(self, key, type, title, meta=None, source="openalex") -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO nodes(key, type, title, meta, source) VALUES (?, ?, ?, ?, ?)",
                (key, type, title, json.dumps(meta or {}), source),
            )
            self.conn.commit()

    def get_node(self, key):
        with self._lock:
            row = self.conn.execute("SELECT * FROM nodes WHERE key = ?", (key,)).fetchone()
        return self._node(row) if row else None

    def nodes(self) -> list[dict]:
        with self._lock:
            rows = self.conn.execute("SELECT * FROM nodes").fetchall()
        return [self._node(r) for r in rows]

    @staticmethod
    def _node(row) -> dict:
        return {
            "key": row["key"],
            "type": row["type"],
            "title": row["title"],
            "meta": json.loads(row["meta"]),
            "source": row["source"],
        }

    # --- edges ---
    def upsert_edge(self, src, dst, rel, source="openalex") -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO edges(src, dst, rel, source) VALUES (?, ?, ?, ?)",
                (src, dst, rel, source),
            )
            self.conn.commit()

    def edges(self) -> list[dict]:
        with self._lock:
            rows = self.conn.execute("SELECT * FROM edges").fetchall()
        return [
            {"src": r["src"], "dst": r["dst"], "rel": r["rel"], "source": r["source"]}
            for r in rows
        ]

    # --- embeddings (for semantic similarity) ---
    def set_embedding(self, key, vector) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO embeddings(key, vec) VALUES (?, ?)",
                (key, json.dumps(list(vector))),
            )
            self.conn.commit()

    def get_embedding(self, key):
        with self._lock:
            row = self.conn.execute("SELECT vec FROM embeddings WHERE key = ?", (key,)).fetchone()
        return json.loads(row["vec"]) if row else None

    def embeddings(self) -> dict:
        with self._lock:
            rows = self.conn.execute("SELECT key, vec FROM embeddings").fetchall()
        return {r["key"]: json.loads(r["vec"]) for r in rows}

    def close(self) -> None:
        with self._lock:
            self.conn.close()
