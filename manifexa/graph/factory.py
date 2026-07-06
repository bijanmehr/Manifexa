"""Pick a graph engine.

Default is **embedded ArcadeDB** — in-process, on-disk under the home (Cypher +
vector, no server, no Docker). If it can't start (package not installed), the
app falls back to the zero-config in-process **NetworkX** engine so it always
runs. Override explicitly with ``MANIFEXA_ENGINE`` (``networkx`` | ``arcadedb``
| ``neo4j``), ``ARCADEDB_PATH``, or ``NEO4J_URI``.
"""
from __future__ import annotations

import os
from pathlib import Path

from .networkx_engine import NetworkXEngine


def engine_from_env(home=None):
    choice = os.environ.get("MANIFEXA_ENGINE", "").lower()

    if choice == "networkx":
        return NetworkXEngine()

    if choice == "neo4j" or (choice == "" and os.environ.get("NEO4J_URI")):
        from .neo4j_engine import Neo4jEngine

        uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        auth = (os.environ.get("NEO4J_USER", "neo4j"), os.environ.get("NEO4J_PASSWORD", ""))
        return Neo4jEngine(uri, auth)

    if choice in ("", "arcadedb"):
        try:
            from .arcadedb_engine import ArcadeDBEngine

            path = os.environ.get("ARCADEDB_PATH") or (
                str(Path(home) / "graph.arcadedb") if home else "manifexa.arcadedb")
            return ArcadeDBEngine.open(path)
        except Exception:
            if choice == "arcadedb":
                raise          # explicitly asked for it → surface the failure
            # implicit default couldn't start ArcadeDB → fall back so the app still runs

    return NetworkXEngine()
