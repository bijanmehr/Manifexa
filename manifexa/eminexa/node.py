"""Build the locked Eminexa `person` node from an OpenAlex author + their window
works. Everything is derived from the (5-year) window works — sharper than the
lifetime author fields — while lifetime prominence (works/cites/h-index) is kept
as a cheap seniority signal. Pure: inject the data, no I/O."""
from __future__ import annotations

import collections

from .clean import dedup_works
from ..sources.openalex import normalize_openalex_id


def build_person_node(author: dict, works: list[dict], today_year: int) -> dict:
    aid = normalize_openalex_id(author["id"])
    works = dedup_works(works)

    topics: collections.Counter = collections.Counter()
    affs: collections.Counter = collections.Counter()
    coauth: dict[str, dict] = {}
    ids: list[str] = []
    for w in works:
        ids.append(normalize_openalex_id(w["id"]))
        yr = w.get("publication_year") or 0
        for t in (w.get("topics") or [])[:3]:
            if t.get("display_name"):
                topics[t["display_name"]] += 1
        for sh in w.get("authorships", []):
            au = sh.get("author") or {}
            k = normalize_openalex_id(au.get("id") or "")
            if not k:
                continue
            if k == aid:
                for s in (sh.get("raw_affiliation_strings") or []):
                    affs[s] += 1
            else:
                c = coauth.setdefault(k, {"id": k, "name": au.get("display_name", ""), "n_shared": 0, "last_year": 0})
                c["n_shared"] += 1
                c["last_year"] = max(c["last_year"], yr)

    orcid = (author.get("orcid") or "").replace("https://orcid.org/", "") or None
    alts = [x for x in (author.get("display_name_alternatives") or []) if x != author.get("display_name")]
    meta = {
        "openalex": aid,
        "orcid": orcid,
        "aliases": alts,
        "works_count": author.get("works_count"),
        "cited_by_count": author.get("cited_by_count"),
        "h_index": (author.get("summary_stats") or {}).get("h_index"),
        "window_work_ids": ids,
        "topics": [t for t, _ in topics.most_common(8)],
        "affiliations": [a for a, _ in affs.most_common(5)],
        "coauthors": sorted(coauth.values(), key=lambda c: (-c["n_shared"], c["name"])),
        "source": "eminexa",
    }
    return {"key": aid, "type": "person", "title": author.get("display_name", ""), "meta": meta}
