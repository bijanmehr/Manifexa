"""NodeView — one node's full information as a structured record.

Assembles a node from its two sources of truth: the entity's frontmatter (scalar
**attributes** — doi, year, url, …) and the graph (**relations** — typed edges
to other nodes, grouped by kind). This is the "proper data structure" the rest
of the app inspects and that exploration/connection features build on, rather
than re-deriving from raw frontmatter each time.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import schema

_WIKILINK = re.compile(r"\[\[(.+?)\]\]")


@dataclass
class NodeView:
    id: str
    type: str
    title: str
    status: str
    attributes: dict = field(default_factory=dict)          # doi, year, url, …
    relations: dict = field(default_factory=dict)           # rel -> [{key,title,type,status}, …]
    notes: str = ""
    issues: list = field(default_factory=list)              # schema warnings/errors

    def relation(self, name: str) -> list:
        return self.relations.get(name, [])

    @property
    def degree(self) -> int:
        return sum(len(v) for v in self.relations.values())


def _names(value) -> list[str]:
    """Author-style values → display names ([[Ada]] or plain 'Ada')."""
    out = []
    for item in value if isinstance(value, (list, tuple)) else [value]:
        if not isinstance(item, str):
            continue
        m = _WIKILINK.search(item)
        out.append((m.group(1) if m else item).strip())
    return [n for n in out if n]


def _is_wikilink_list(v) -> bool:
    return isinstance(v, (list, tuple)) and bool(v) and all(
        isinstance(x, str) and "[[" in x for x in v)


def build_view(entity, engine) -> NodeView:
    """Assemble ``entity`` (+ its graph edges) into a :class:`NodeView`."""
    relations: dict = {}
    if engine is not None and engine.has_node(entity.id):
        for nbr, rel in engine.neighbors_with_rel(entity.id):
            n = engine.node(nbr) or {"key": nbr}
            relations.setdefault(rel or "related", []).append(
                {"key": nbr, "title": n.get("title") or nbr,
                 "type": n.get("type"), "status": n.get("status")})

    # Fold a paper's `authors` frontmatter (OpenAlex/manual) into `authored`,
    # de-duped against author nodes already reached through the graph.
    seen = {r["title"] for group in relations.values() for r in group}
    for name in _names(entity.meta.get("authors")):
        if name not in seen:
            relations.setdefault("authored", []).append(
                {"key": name, "title": name, "type": "person", "status": None})
            seen.add(name)

    skip = set(schema.IDENTITY) | {schema.RELATION_KEY, "authors"}
    attributes = {k: v for k, v in entity.meta.items()
                  if k not in skip and not _is_wikilink_list(v)}

    return NodeView(id=entity.id, type=entity.type, title=entity.title,
                    status=entity.status, attributes=attributes, relations=relations,
                    notes=entity.body, issues=schema.validate(entity))
