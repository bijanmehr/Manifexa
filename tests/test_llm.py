"""LLM-powered graph ops — plumbing tested with a fake provider (no live model).

Mirrors the extract pattern: inject a provider that returns canned structured
output, and verify prompt-building + candidate-writing. Live Claude / Ollama
calls happen on the user's machine.
"""
from manifexa.graph.networkx_engine import NetworkXEngine
from manifexa.llm import operations as ops
from manifexa.llm.provider import AnthropicProvider, OllamaProvider, provider_from_env
from manifexa.store.cache import Cache


class FakeProvider:
    name = "fake"

    def __init__(self, payload):
        self.payload = payload
        self.prompts = []

    def generate(self, prompt, system=None, schema=None):
        self.prompts.append(prompt)
        return self.payload


def _engine():
    e = NetworkXEngine()
    e.add_node("person/ada", type="person", title="Ada Lovelace", status="curated")
    e.add_node("paper/notes", type="paper", title="Notes on the Engine", status="curated")
    e.add_edge("person/ada", "paper/notes", "authored")
    return e


def test_expand_writes_candidates_linked_to_the_focal():
    e, cache = _engine(), Cache()
    p = FakeProvider({
        "entities": [{"type": "person", "title": "Charles Babbage"}],
        "edges": [{"source": "Charles Babbage", "target": "Ada Lovelace", "rel": "collaborator"}],
    })
    res = ops.expand(p, e, cache, "person/ada")
    assert res["entities"] == 1
    assert any(n["key"] == "person/charles-babbage" for n in cache.nodes())
    assert all(n["source"].startswith("llm:") for n in cache.nodes())          # provenance
    triples = {(x["src"], x["dst"], x["rel"]) for x in cache.edges()}
    assert ("person/charles-babbage", "person/ada", "collaborator") in triples  # linked to focal
    assert "Ada Lovelace" in p.prompts[0]                                        # context in prompt


def test_complete_only_links_existing_nodes():
    e, cache = _engine(), Cache()
    p = FakeProvider({"entities": [], "edges": [
        {"source": "Ada Lovelace", "target": "Notes on the Engine", "rel": "describes"},  # both exist → kept
        {"source": "Ada Lovelace", "target": "Someone New", "rel": "knows"},              # missing → dropped
    ]})
    res = ops.complete(p, e, cache, "person/ada")
    assert res["edges"] == 1
    assert ("person/ada", "paper/notes", "describes") in {(x["src"], x["dst"], x["rel"]) for x in cache.edges()}


def test_ask_returns_only_valid_keys_in_order():
    p = FakeProvider({"keys": ["paper/notes", "person/ada", "bogus/key"]})
    assert ops.ask(p, _engine(), "engine notes") == ["paper/notes", "person/ada"]


def test_provider_from_env_selects(monkeypatch):
    monkeypatch.setenv("MANIFEXA_LLM", "ollama")
    assert isinstance(provider_from_env(), OllamaProvider)
    monkeypatch.setenv("MANIFEXA_LLM", "claude")
    assert isinstance(provider_from_env(), AnthropicProvider)


def test_app_wires_ask_to_the_injected_provider(tmp_path):
    from manifexa.app import App

    app = App(str(tmp_path), llm=FakeProvider({"keys": []}))
    app.create("person", "Ada Lovelace")
    app.llm = FakeProvider({"keys": ["person/ada-lovelace", "nope"]})
    assert app.ask("who wrote the first algorithm") == ["person/ada-lovelace"]
