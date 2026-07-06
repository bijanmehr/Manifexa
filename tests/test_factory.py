import sys

import pytest

from manifexa.graph.factory import engine_from_env
from manifexa.graph.networkx_engine import NetworkXEngine


def test_networkx_when_forced(monkeypatch):
    monkeypatch.setenv("MANIFEXA_ENGINE", "networkx")
    assert isinstance(engine_from_env(), NetworkXEngine)


def test_falls_back_to_networkx_when_arcadedb_unavailable(monkeypatch):
    monkeypatch.delenv("MANIFEXA_ENGINE", raising=False)
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.setitem(sys.modules, "arcadedb_embedded", None)   # force its import to fail
    assert isinstance(engine_from_env(), NetworkXEngine)


def test_arcadedb_is_the_default_when_available(monkeypatch, tmp_path):
    pytest.importorskip("arcadedb_embedded")
    from manifexa.graph.arcadedb_engine import ArcadeDBEngine

    monkeypatch.delenv("MANIFEXA_ENGINE", raising=False)
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.setenv("ARCADEDB_PATH", str(tmp_path / "g.arcadedb"))
    eng = engine_from_env()
    try:
        assert isinstance(eng, ArcadeDBEngine)
    finally:
        eng.close()
