"""Promote — turn a cached candidate into a curated entity file.

The promoted entity keeps the candidate's source key as its ``openalex`` id, so
every edge the cache already holds for it reconciles onto the new curated node
on the next sync. This is the step that closes the loop: discovery surfaces a
candidate, you vouch for it, and it becomes part of your truth.
"""
from __future__ import annotations

from .store.entity import Entity
from .store.slug import make_id


def promote(vault, cache, candidate_key: str, note: str = "") -> str:
    node = cache.get_node(candidate_key)
    if node is None:
        raise KeyError(candidate_key)

    type = node["type"]
    title = node["title"] or candidate_key
    entity = Entity(
        id=make_id(type, title),
        meta={"type": type, "title": title, "openalex": candidate_key, "status": "curated"},
        body=note,
    )
    vault.write(entity)
    return entity.id
