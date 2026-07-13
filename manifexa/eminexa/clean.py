"""Cleaning guards — normalize scalar strings and dedup near-duplicate works
BEFORE any coauthor facts are computed (duplicate work records inflate counts,
which is exactly what the coauthor edges are built from)."""
from __future__ import annotations

import html
import re
import unicodedata


def normalize(s: str) -> str:
    """HTML-unescape, NFKC-fold, collapse whitespace, casefold. Deterministic."""
    if not s:
        return ""
    s = html.unescape(s)
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.casefold()


def _doi_norm(doi) -> str:
    return normalize((doi or "").replace("https://doi.org/", ""))


def _title_key(w: dict) -> str:
    t = normalize(w.get("title") or "")
    t = re.split(r"[-–]\s*suppl", t)[0]          # drop "- Supplementary ..."
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _cluster_tkey(w: dict) -> str:
    return _title_key(w) + "|" + str(w.get("publication_year"))


def dedup_works(works: list[dict]) -> list[dict]:
    """Collapse duplicate work records to one canonical per paper.

    Two passes so a DOI-less copy still joins its DOI-bearing twin:
      1. map each (title, year) that has *any* DOI to that DOI;
      2. cluster by DOI when the record has one (or its title-cluster does),
         else by (title, year). The record carrying a DOI wins as canonical.
    """
    title_doi: dict[str, str] = {}
    for w in works:
        d = _doi_norm(w.get("doi"))
        if d:
            title_doi.setdefault(_cluster_tkey(w), d)

    best: dict[str, dict] = {}
    for w in works:
        own = _doi_norm(w.get("doi"))
        d = own or title_doi.get(_cluster_tkey(w), "")
        key = ("doi:" + d) if d else ("t:" + _cluster_tkey(w))
        cur = best.get(key)
        if cur is None or (own and not _doi_norm(cur.get("doi"))):
            best[key] = w
    return list(best.values())
