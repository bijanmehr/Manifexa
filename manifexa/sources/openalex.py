"""OpenAlex source — the enrichment backbone.

Two parts kept deliberately separate:

* **Pure transforms** (`normalize_openalex_id`, `work_to_entity`,
  `extract_neighbors`) turn OpenAlex JSON into our Entity / node / edge shapes.
  These hold all the logic and are unit-tested against recorded fixtures.
* **`OpenAlexClient`** does the actual HTTP with stdlib ``urllib`` — thin, no
  logic, exercised live on the user's machine.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .http import get_json
from ..store.entity import Entity
from ..store.slug import make_id

_PREFIX = "https://openalex.org/"


def normalize_openalex_id(oa_id: str) -> str:
    """``https://openalex.org/W123`` -> ``W123`` (idempotent)."""
    if oa_id and oa_id.startswith(_PREFIX):
        return oa_id[len(_PREFIX):]
    return oa_id


def _title(work: dict) -> str:
    return work.get("title") or work.get("display_name") or ""


def reconstruct_abstract(inverted_index) -> str:
    """OpenAlex stores abstracts as ``{word: [positions]}`` — put the words back
    in order."""
    if not inverted_index:
        return ""
    placed = [(p, w) for w, ps in inverted_index.items() for p in ps]
    return " ".join(w for _, w in sorted(placed))


def work_venue(work: dict) -> str:
    return ((work.get("primary_location") or {}).get("source") or {}).get("display_name") or ""


def work_topics(work: dict, limit: int = 4) -> list[str]:
    return [t["display_name"] for t in (work.get("topics") or [])[:limit] if t.get("display_name")]


def work_to_entity(work: dict) -> Entity:
    """An OpenAlex work -> a curated ``paper`` entity for the vault, filled out:
    authors, year, doi, venue, topics (as ``[[wikilinks]]``), abstract (body)."""
    title = _title(work)
    authors = [a.get("author", {}).get("display_name", "") for a in work.get("authorships", [])]
    meta = {
        "type": "paper",
        "title": title,
        "year": work.get("publication_year"),
        "doi": work.get("doi"),
        "venue": work_venue(work) or None,
        "openalex": normalize_openalex_id(work["id"]),
        "authors": [f"[[{name}]]" for name in authors if name],
        "topics": [f"[[{make_id('topic', t)}]]" for t in work_topics(work)],
        "status": "curated",
    }
    meta = {k: v for k, v in meta.items() if v not in (None, [])}          # keep frontmatter tidy
    body = reconstruct_abstract(work.get("abstract_inverted_index"))
    return Entity(id=make_id("paper", title), meta=meta, body=(f"## Abstract\n\n{body}\n" if body else ""))


def extract_neighbors(work: dict) -> tuple[list[dict], list[dict]]:
    """1-hop neighbours of a work: author/institution/reference nodes + edges.

    Edges reference the seed by its OpenAlex key so sync can reconcile them with
    the curated vault entity that carries the same ``openalex`` id.
    """
    seed = normalize_openalex_id(work["id"])
    nodes: list[dict] = []
    edges: list[dict] = []
    seen: set[str] = set()

    def add_node(key: str, type: str, title: str) -> None:
        if key and key not in seen:
            seen.add(key)
            nodes.append({"key": key, "type": type, "title": title})

    for ship in work.get("authorships", []):
        author = ship.get("author", {})
        akey = normalize_openalex_id(author.get("id", ""))
        if not akey:
            continue
        add_node(akey, "person", author.get("display_name", ""))
        edges.append({"src": akey, "dst": seed, "rel": "authored"})
        for inst in ship.get("institutions", []):
            ikey = normalize_openalex_id(inst.get("id", ""))
            if ikey:
                add_node(ikey, "lab", inst.get("display_name", ""))
                edges.append({"src": akey, "dst": ikey, "rel": "affiliated_with"})

    for ref in work.get("referenced_works", []):
        rkey = normalize_openalex_id(ref)
        add_node(rkey, "paper", "")
        edges.append({"src": seed, "dst": rkey, "rel": "cites"})

    return nodes, edges


class OpenAlexClient:
    """Thin HTTP client for the live OpenAlex API (no business logic)."""

    BASE = "https://api.openalex.org"

    def __init__(self, mailto: str | None = None, timeout: int = 15) -> None:
        self.mailto = mailto
        self.timeout = timeout

    def _get(self, path: str, params: dict | None = None) -> dict:
        params = dict(params or {})
        if self.mailto:
            params["mailto"] = self.mailto
        url = f"{self.BASE}/{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        return get_json(url, headers={"User-Agent": "manifexa/0.1"}, timeout=self.timeout)

    def get_work(self, work_id: str) -> dict:
        return self._get(f"works/{normalize_openalex_id(work_id)}")

    def search_works(self, query: str, per_page: int = 5) -> list[dict]:
        return self._get("works", {"search": query, "per_page": per_page}).get("results", [])

    def works_by_ids(self, ids: list[str]) -> list[dict]:
        if not ids:
            return []
        filt = "openalex:" + "|".join(normalize_openalex_id(i) for i in ids)
        return self._get("works", {"filter": filt, "per_page": len(ids)}).get("results", [])

    def cited_by(self, work_id: str, per_page: int = 25) -> list[dict]:
        filt = "cites:" + normalize_openalex_id(work_id)
        return self._get("works", {"filter": filt, "per_page": per_page}).get("results", [])
