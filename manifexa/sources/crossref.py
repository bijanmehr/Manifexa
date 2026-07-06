"""Crossref source — authoritative metadata-of-record, used as a fallback.

When OpenAlex can't resolve a seed, Crossref still has the canonical DOI record.
No citation graph, but it gets the paper into your vault. Transform is pure and
tested; the HTTP client is thin.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .http import get_json
from ..store.entity import Entity
from ..store.slug import make_id

_DOI_PREFIX = "https://doi.org/"


def crossref_work_to_entity(work: dict) -> Entity:
    title = (work.get("title") or [""])[0] or ""
    authors = [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in work.get("author", [])]
    year = None
    parts = (work.get("issued") or {}).get("date-parts")
    if parts and parts[0]:
        year = parts[0][0]
    doi = work.get("DOI")
    meta = {
        "type": "paper",
        "title": title,
        "year": year,
        "doi": f"{_DOI_PREFIX}{doi}" if doi else None,
        "authors": [f"[[{a}]]" for a in authors if a],
        "status": "curated",
    }
    return Entity(id=make_id("paper", title), meta=meta)


class CrossrefClient:
    BASE = "https://api.crossref.org"

    def __init__(self, mailto: str | None = None, timeout: int = 15) -> None:
        self.mailto = mailto
        self.timeout = timeout

    def get_work(self, doi: str) -> dict:
        d = doi[len(_DOI_PREFIX):] if doi.lower().startswith(_DOI_PREFIX) else doi
        url = f"{self.BASE}/works/{urllib.parse.quote(d)}"
        if self.mailto:
            url += "?" + urllib.parse.urlencode({"mailto": self.mailto})
        return get_json(url, headers={"User-Agent": "manifexa/0.1"}, timeout=self.timeout).get("message", {})
