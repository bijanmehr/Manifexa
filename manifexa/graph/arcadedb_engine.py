"""ArcadeDB graph engine — embedded, in-process, same interface as NetworkX.

Runs ArcadeDB *inside the process* via the ``arcadedb-embedded`` bindings
(bundled JRE — no server, no Docker, no Java install). A database is just a
folder on disk, like SQLite. Nodes are ``(:Entity {key,type,title,status})``,
relationships are ``[:LINK {rel}]`` queried undirected — identical semantics to
the NetworkX and Neo4j engines, so discovery is the same on any backend.

Writes go through Cypher ``MERGE`` (idempotent, index-backed); whole-graph
algorithms (shortest path, betweenness) are computed in-process with NetworkX
over the fetched edges, so they don't depend on any ArcadeDB-specific Cypher.

The constructor takes an already-open ``db`` handle so the query/parse logic is
injectable; :meth:`open` is the real embedded entry point.
"""
from __future__ import annotations

_SCHEMA = (
    "CREATE VERTEX TYPE Entity IF NOT EXISTS",
    "CREATE EDGE TYPE LINK IF NOT EXISTS",
    "CREATE PROPERTY Entity.key IF NOT EXISTS STRING",
    "CREATE INDEX IF NOT EXISTS ON Entity (key) UNIQUE",
)


def _quiet_jvm():
    """Silence ArcadeDB's JVM console logging (it logs through java.util.logging),
    so its INFO / index-build lines can't corrupt the full-screen TUI — notably
    when a `vault` switch opens a new database mid-session. Persists per process."""
    try:
        import jpype

        if not jpype.isJVMStarted():
            return
        jul = jpype.JPackage("java").util.logging
        jul.LogManager.getLogManager().reset()
        jul.Logger.getLogger("").setLevel(jul.Level.OFF)
    except Exception:
        pass


class ArcadeDBEngine:
    def __init__(self, db) -> None:
        self._db = db
        for ddl in _SCHEMA:
            self._db.command("sql", ddl)

    @classmethod
    def open(cls, path: str) -> "ArcadeDBEngine":
        """Open (or create) an embedded ArcadeDB at ``path`` — a folder on disk."""
        import arcadedb_embedded as adb

        db = adb.open_database(path) if adb.database_exists(path) else adb.create_database(path)
        _quiet_jvm()                       # before schema DDL, so index-build stays silent
        return cls(db)

    # --- helpers ---
    def _rows(self, cypher: str, params: dict | None = None) -> list[dict]:
        rs = self._db.query("cypher", cypher, params) if params is not None else self._db.query("cypher", cypher)
        return [r.to_dict() for r in rs]

    def _write(self, cypher: str, params: dict) -> None:
        self._db.begin()
        try:
            self._db.command("cypher", cypher, params)
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise

    # --- writes ---
    def add_node(self, key: str, **attrs) -> None:
        clean = {k: v for k, v in attrs.items() if v is not None}
        sets = ", ".join(f"n.`{k}` = ${k}" for k in clean)
        cypher = "MERGE (n:Entity {key:$key})" + (f" SET {sets}" if sets else "")
        self._write(cypher, {"key": key, **clean})

    def add_edge(self, src: str, dst: str, rel: str) -> None:
        self._write(
            "MATCH (a:Entity {key:$src}), (b:Entity {key:$dst}) MERGE (a)-[r:LINK {rel:$rel}]->(b)",
            {"src": src, "dst": dst, "rel": rel},
        )

    def clear(self) -> None:
        self._db.begin()
        try:
            self._db.command("sql", "DELETE FROM LINK")
            self._db.command("sql", "DELETE FROM Entity")
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise

    # --- reads ---
    def has_node(self, key: str) -> bool:
        r = self._rows("MATCH (n:Entity {key:$key}) RETURN count(n) AS c", {"key": key})
        return bool(r) and (r[0].get("c") or 0) > 0

    def node(self, key: str):
        r = self._rows(
            "MATCH (n:Entity {key:$key}) RETURN n.key AS key, n.type AS type, n.title AS title, n.status AS status",
            {"key": key},
        )
        return {k: v for k, v in r[0].items() if v is not None} if r else None

    def nodes(self) -> list[str]:
        return [row["key"] for row in self._rows("MATCH (n:Entity) RETURN n.key AS key")]

    def neighbors(self, key: str) -> list[str]:
        return [row["k"] for row in self._rows(
            "MATCH (:Entity {key:$key})-[:LINK]-(m:Entity) RETURN DISTINCT m.key AS k", {"key": key})]

    def neighbors_with_rel(self, key: str) -> list[tuple[str, str]]:
        return [(row["k"], row["rel"]) for row in self._rows(
            "MATCH (:Entity {key:$key})-[r:LINK]-(m:Entity) RETURN m.key AS k, r.rel AS rel", {"key": key})]

    def _nx(self):
        import networkx as nx

        g = nx.Graph()
        for k in self.nodes():
            g.add_node(k)
        for row in self._rows("MATCH (a:Entity)-[:LINK]-(b:Entity) RETURN a.key AS a, b.key AS b"):
            g.add_edge(row["a"], row["b"])
        return g

    def shortest_path(self, src: str, dst: str):
        import networkx as nx

        if src == dst:
            return [src] if self.has_node(src) else None
        g = self._nx()
        if not (g.has_node(src) and g.has_node(dst)):
            return None
        try:
            return nx.shortest_path(g, src, dst)
        except nx.NetworkXNoPath:
            return None

    def betweenness(self) -> dict[str, float]:
        import networkx as nx

        return nx.betweenness_centrality(self._nx())

    def close(self) -> None:
        try:
            self._db.close()
        except Exception:
            pass
