"""Enrichment — fan out from a seed into the cache.

``enrich_seed`` writes the seed as a curated entity, then pulls its 1-hop
neighbourhood (authors, institutions, references, citations) into the candidate
cache as nodes + edges. The client is injected so this is testable offline.
"""
from __future__ import annotations

from .openalex import extract_neighbors, normalize_openalex_id, work_to_entity


def _title(work: dict) -> str:
    return work.get("title") or work.get("display_name") or ""


def enrich_seed(client, vault, cache, seed_id: str, *, cap: int = 25) -> dict:
    work = client.get_work(seed_id)
    entity = work_to_entity(work)
    vault.write(entity)

    seed_key = normalize_openalex_id(work["id"])
    nodes, edges = extract_neighbors(work)

    # References arrive as ids only — fetch titles (and DOIs) in one batched call.
    ref_keys = [n["key"] for n in nodes if n["type"] == "paper" and not n["title"]]
    if ref_keys:
        fetched = {normalize_openalex_id(w["id"]): w for w in client.works_by_ids(ref_keys[:cap])}
        for n in nodes:
            if n["key"] in fetched:
                n["title"] = _title(fetched[n["key"]])
                n["doi"] = fetched[n["key"]].get("doi")

    # Citations: papers that cite the seed (arrive titled). Query by the
    # resolved OpenAlex key — the live API rejects a raw DOI here, which is what
    # crashed enrichment when seeding by DOI.
    for w in client.cited_by(seed_key, per_page=cap):
        key = normalize_openalex_id(w["id"])
        nodes.append({"key": key, "type": "paper", "title": _title(w), "doi": w.get("doi")})
        edges.append({"src": key, "dst": seed_key, "rel": "cites"})

    for n in nodes:
        meta = {"openalex": n["key"]}
        if n.get("doi"):
            meta["doi"] = n["doi"]
        cache.upsert_node(n["key"], n["type"], n["title"], meta)
    for e in edges:
        cache.upsert_edge(e["src"], e["dst"], e["rel"])

    return {"entity": entity.id, "nodes": len(nodes), "edges": len(edges)}
