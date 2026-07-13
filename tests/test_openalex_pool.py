import json

import manifexa.sources.openalex as oa


def test_client_sends_mailto_and_api_key(monkeypatch):
    cap = {}
    monkeypatch.setattr(oa, "get_json", lambda url, **k: cap.update(url=url) or {"results": []})
    oa.OpenAlexClient(mailto="me@x.com", api_key="KEY123")._get("works", {"filter": "x"})
    assert "mailto=me%40x.com" in cap["url"]        # polite pool
    assert "api_key=KEY123" in cap["url"]           # authenticated


def test_client_without_creds_sends_neither(monkeypatch):
    cap = {}
    monkeypatch.setattr(oa, "get_json", lambda url, **k: cap.update(url=url) or {})
    oa.OpenAlexClient()._get("works", {})
    assert "mailto=" not in cap["url"] and "api_key=" not in cap["url"]


def test_load_openalex_config_reads_file(tmp_path):
    p = tmp_path / "openalex.json"
    p.write_text(json.dumps({"mailto": "a@b.com", "api_key": "K"}))
    cfg = oa.load_openalex_config(str(p))
    assert cfg == {"mailto": "a@b.com", "api_key": "K"}


def test_load_openalex_config_missing_file_is_empty(tmp_path):
    assert oa.load_openalex_config(str(tmp_path / "nope.json")) == {}


def test_load_openalex_config_env_mailto_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENALEX_MAILTO", "env@x.com")
    cfg = oa.load_openalex_config(str(tmp_path / "nope.json"))
    assert cfg["mailto"] == "env@x.com"
