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


def test_cache_delete_by_source_purges_matching_candidates():
    c = Cache()
    c.upsert_node("a", "paper", "A", source="openalex")
    c.upsert_node("b", "paper", "B", source="llm:local")
    c.upsert_edge("a", "b", "cites", source="llm:local")
    c.upsert_edge("x", "a", "cites", source="openalex")
    removed = c.delete_by_source("llm:")
    assert removed == 1                                          # one llm node dropped
    assert {n["key"] for n in c.nodes()} == {"a"}               # openalex node kept
    assert all(e["source"] == "openalex" for e in c.edges())    # llm edge gone


def test_app_forget_drops_llm_candidates_and_rebuilds(tmp_path, monkeypatch):
    monkeypatch.setenv("MANIFEXA_ENGINE", "networkx")
    from manifexa.app import App

    app = App(str(tmp_path))
    app.create("paper", "Real Paper")
    app.cache.upsert_node("ghost", "paper", "Hallucinated", source="llm:local")
    app.rebuild()
    assert app.graph().has_node("ghost")
    app.forget("llm:")
    assert not app.graph().has_node("ghost")                    # purged + graph rebuilt


def test_expand_dedups_proposals_against_existing_nodes():
    e = NetworkXEngine()
    e.add_node("paper/x", type="paper", title="Focal Paper", status="curated")
    e.add_node("person/hans", type="person", title="Nikolaus Hansen", status="candidate")  # already there
    cache = Cache()
    p = FakeProvider({
        "entities": [{"type": "person", "title": "nikolaus  hansen"}],   # different case/spacing
        "edges": [{"source": "nikolaus  hansen", "target": "Focal Paper", "rel": "authored"}],
    })
    ops.expand(p, e, cache, "paper/x")
    keys = {n["key"] for n in cache.nodes()}
    assert "person/nikolaus-hansen" not in keys                          # no duplicate person minted
    triples = {(x["src"], x["dst"], x["rel"]) for x in cache.edges()}
    assert ("person/hans", "paper/x", "authored") in triples             # edge reuses the existing node


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


def test_organize_groups_titled_nodes_into_themes():
    p = FakeProvider({"summary": "About the engine.", "themes": [
        {"label": "People", "keys": ["person/ada"]},
        {"label": "Papers", "keys": ["paper/notes"]},
    ]})
    r = ops.organize(p, _engine())
    assert r["summary"] == "About the engine."
    assert {t["label"] for t in r["themes"]} == {"People", "Papers"}
    assert "Ada Lovelace" in p.prompts[0]                         # titles fed to the model


def test_organize_drops_invalid_keys_and_buckets_untitled():
    e = NetworkXEngine()
    e.add_node("paper/a", type="paper", title="Real Paper", status="curated")
    e.add_node("W123", type="paper", title="", status="candidate")   # unfetched ref, no title
    p = FakeProvider({"summary": "x", "themes": [{"label": "T", "keys": ["paper/a", "bogus"]}]})
    r = ops.organize(p, e)
    assert r["themes"][0]["keys"] == ["paper/a"]                  # hallucinated key dropped
    assert "W123" in r["untitled"]                               # untitled refs bucketed separately


def test_app_organize_uses_the_injected_provider(tmp_path):
    from manifexa.app import App

    app = App(str(tmp_path), llm=FakeProvider({"summary": "s", "themes": []}))
    app.create("paper", "On Heat")
    assert app.organize()["summary"] == "s"


def test_map_ai_command_renders_summary_and_themes(tmp_path, monkeypatch):
    monkeypatch.setenv("MANIFEXA_ENGINE", "networkx")
    from manifexa.app import App
    from manifexa.tui import dispatch

    app = App(str(tmp_path), llm=FakeProvider({"summary": "About heat.", "themes": [
        {"label": "Thermodynamics", "keys": ["paper/on-heat"]}]}))
    app.create("paper", "On Heat")
    out = dispatch(app, "map ai")
    assert "About heat." in out and "Thermodynamics" in out and "On Heat" in out


def test_provider_from_env_selects(monkeypatch):
    monkeypatch.setenv("MANIFEXA_LLM", "ollama")
    assert isinstance(provider_from_env(), OllamaProvider)
    monkeypatch.setenv("MANIFEXA_LLM", "claude")
    assert isinstance(provider_from_env(), AnthropicProvider)


def test_ollama_generate_builds_a_schema_request_and_parses(monkeypatch):
    """Lock the Ollama contract: schema → `format`, response JSON parsed back —
    without needing a live model."""
    import json as _json
    import urllib.request

    seen = {}

    class _Resp:
        def __init__(self, payload):
            self._p = payload

        def read(self):
            return self._p

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["body"] = _json.loads(req.data.decode())
        return _Resp(_json.dumps({"response": _json.dumps({"keys": ["a", "b"]})}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    p = OllamaProvider(model="llama3.1", host="http://localhost:11434")
    out = p.generate("find X", system="you rank", schema={"type": "object"})
    assert out == {"keys": ["a", "b"]}                          # structured JSON parsed back
    assert seen["url"].endswith("/api/generate")
    assert seen["body"]["model"] == "llama3.1"
    assert seen["body"]["format"] == {"type": "object"}         # the schema is passed as `format`
    assert seen["body"]["stream"] is False
    assert seen["body"]["system"] == "you rank"


def test_app_wires_ask_to_the_injected_provider(tmp_path):
    from manifexa.app import App

    app = App(str(tmp_path), llm=FakeProvider({"keys": []}))
    app.create("person", "Ada Lovelace")
    app.llm = FakeProvider({"keys": ["person/ada-lovelace", "nope"]})
    assert app.ask("who wrote the first algorithm") == ["person/ada-lovelace"]
