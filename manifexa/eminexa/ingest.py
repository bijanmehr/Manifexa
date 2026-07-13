"""Ingest one person into the cache: a full `person` node + one stub per coauthor
+ one `coauthored` edge per coauthor, all ``source="eminexa"``. The existing
``App.rebuild()`` projects these into the graph; discovery (clusters/bridges/
around) then works on people for free. Mirrors ``sources.enrich.enrich_seed``."""
from __future__ import annotations

from . import scholar as _scholar
from .node import build_person_node
from .resolve import resolve_seed


def ingest_person(cache, pc, seed: str, today_year: int, from_date: str, fetch=None) -> dict:
    scholar_info = None
    snapshot = None
    if _scholar.is_scholar_url(seed):
        # Scholar link → fetch + parse (deterministic) → paper-anchor to OpenAlex.
        raw = (fetch or _scholar.fetch_profile)(seed)
        profile = _scholar.parse_profile(raw)
        r = _scholar.resolve_scholar(pc, profile)
        aid = r["author_id"]
        scholar_info = {"name": profile.name, "corroboration": r["corroboration"], "searched": r["searched"]}
        snapshot = {k: v for k, v in {                       # leading-edge, from Scholar
            "current_affiliation": profile.affiliation,
            "email_domain": profile.email_domain,
            "scholar_url": seed,
            "scholar_name": profile.name,
            "publications": profile.publications[:200] or None,
        }.items() if v}
    else:
        aid = resolve_seed(pc, seed)

    author = pc.get_author(aid)
    works = pc.works_by_author(aid, from_date=from_date)
    node = build_person_node(author, works, today_year=today_year)
    if snapshot:
        node["meta"].update(snapshot)

    cache.upsert_node(node["key"], "person", node["title"], node["meta"], source="eminexa")
    edges = 0
    for c in node["meta"]["coauthors"]:
        if not cache.get_node(c["id"]):          # never clobber a full node with a stub
            cache.upsert_node(c["id"], "person", c["name"],
                              {"openalex": c["id"], "stub": True}, source="eminexa")
        cache.upsert_edge(node["key"], c["id"], "coauthored", source="eminexa")
        edges += 1
    result = {"person": node["key"], "name": node["title"],
              "coauthors": len(node["meta"]["coauthors"]), "edges": edges}
    if scholar_info:
        result["scholar"] = scholar_info
    return result
