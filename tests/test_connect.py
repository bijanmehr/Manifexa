"""LLM auto-connect on launch — resolve the provider, bring up a tunnel if
configured, and fail clearly (not cryptically) when the box is unreachable.

Network/SSH are injected (``reach`` / ``bring_up``) so the logic is unit-tested.
"""
import pytest

from manifexa.llm import connect
from manifexa.llm.provider import OllamaProvider


def test_no_config_is_a_noop():
    assert connect.ensure_llm({}, reach=lambda u: True, bring_up=lambda t: None) == (None, "")


def test_reachable_ollama_returns_a_provider():
    cfg = {"provider": "ollama", "host": "http://localhost:11435", "model": "qwen3-coder-next:q8_0"}
    prov, status = connect.ensure_llm(cfg, reach=lambda u: True, bring_up=lambda t: None)
    assert isinstance(prov, OllamaProvider)
    assert prov.model == "qwen3-coder-next:q8_0" and prov.host == "http://localhost:11435"
    assert "ready" in status.lower()


def test_unreachable_returns_offline_provider_with_a_clear_error():
    cfg = {"provider": "ollama", "host": "http://localhost:11435", "model": "m",
           "tunnel": {"ssh": "balthar", "local_port": 11435, "remote_port": 11434}}
    prov, status = connect.ensure_llm(cfg, reach=lambda u: False, bring_up=lambda t: None)
    assert "offline" in status.lower() and "balthar" in status         # names the box
    with pytest.raises(RuntimeError):                                  # LLM ops fail loudly, not silently
        prov.generate("anything")


def test_brings_up_the_tunnel_when_down_then_connects():
    calls, state = {"n": 0}, {"up": False}

    def reach(_url):
        return state["up"]

    def bring_up(_t):
        calls["n"] += 1
        state["up"] = True                                            # tunnel establishes → now reachable

    cfg = {"provider": "ollama", "host": "http://localhost:11435",
           "tunnel": {"ssh": "balthar", "local_port": 11435, "remote_port": 11434}}
    prov, status = connect.ensure_llm(cfg, reach=reach, bring_up=bring_up)
    assert calls["n"] == 1 and isinstance(prov, OllamaProvider)        # tried the tunnel, then connected


def test_env_overrides_config(monkeypatch):
    monkeypatch.setenv("MANIFEXA_LLM", "ollama")
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:9999")
    monkeypatch.setenv("MANIFEXA_LLM_MODEL", "envmodel")
    prov, _ = connect.ensure_llm(reach=lambda u: True, bring_up=lambda t: None)   # cfg=None → env + global
    assert isinstance(prov, OllamaProvider) and prov.model == "envmodel"
    assert prov.host == "http://localhost:9999"
