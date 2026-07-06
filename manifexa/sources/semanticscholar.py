"""Semantic Scholar source — primarily an embedding provider.

Attaches SPECTER2 vectors to papers already in the graph, matched by **DOI** and
stored under the same key the graph uses (the OpenAlex id) — so semantic
similarity lines up with the rest of the data. Pure transforms are tested; the
HTTP client is thin and exercised live on the user's machine.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .http import get_json

_DOI_PREFIX = "https://doi.org/"


def normalize_doi(doi: str) -> str:
    if doi and doi.lower().startswith(_DOI_PREFIX):
        return doi[len(_DOI_PREFIX):]
    return doi


def s2_embedding(paper: dict):
    emb = paper.get("embedding")
    if emb and emb.get("vector"):
        return emb["vector"]
    return None


def enrich_embeddings(client, vault, cache) -> dict:
    """Fetch + store embeddings for every paper (vault + cache) that has a DOI."""
    targets: dict[str, str] = {}
    for e in vault.list():
        if e.type == "paper":
            key, doi = e.meta.get("openalex"), e.meta.get("doi")
            if key and doi:
                targets[key] = doi
    for n in cache.nodes():
        if n["type"] == "paper" and n["meta"].get("doi"):
            targets[n["key"]] = n["meta"]["doi"]

    embedded = 0
    for key, doi in targets.items():
        if cache.get_embedding(key) is not None:
            continue
        vec = client.embedding(doi)
        if vec:
            cache.set_embedding(key, vec)
            embedded += 1
    return {"embedded": embedded}


class SemanticScholarClient:
    BASE = "https://api.semanticscholar.org/graph/v1"

    def __init__(self, api_key: str | None = None, timeout: int = 15) -> None:
        self.api_key = api_key
        self.timeout = timeout

    def _get(self, path: str, params: dict) -> dict:
        url = f"{self.BASE}/{path}?" + urllib.parse.urlencode(params)
        headers = {"User-Agent": "manifexa/0.1"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return get_json(url, headers=headers, timeout=self.timeout)

    def get_paper(self, paper_id: str, fields: str = "title,externalIds,embedding") -> dict:
        return self._get(f"paper/{paper_id}", {"fields": fields})

    def embedding(self, doi: str):
        try:
            paper = self.get_paper(f"DOI:{normalize_doi(doi)}", fields="embedding")
        except Exception:
            return None
        return s2_embedding(paper)
