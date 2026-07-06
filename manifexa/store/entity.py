"""The Entity model — one node of the knowledge graph, backed by one file.

An entity is just its identity, its frontmatter (open-ended metadata), and its
free-text body. `type`, `title`, and `status` are conveniences read from the
frontmatter so the schema stays flexible. Relationships are expressed as
``[[wikilinks]]`` inside frontmatter values and the body.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .frontmatter import parse_frontmatter, serialize_frontmatter

_WIKILINK = re.compile(r"\[\[(.+?)\]\]")


def _iter_strings(value):
    """Yield every string found in a nested frontmatter value."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _iter_strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _iter_strings(v)


@dataclass
class Entity:
    id: str
    meta: dict = field(default_factory=dict)
    body: str = ""

    @property
    def type(self) -> str:
        return self.meta.get("type", "")

    @property
    def title(self) -> str:
        return self.meta.get("title", "")

    @property
    def status(self) -> str:
        return self.meta.get("status", "candidate")

    @classmethod
    def from_markdown(cls, id: str, text: str) -> "Entity":
        meta, body = parse_frontmatter(text)
        return cls(id=id, meta=meta, body=body)

    def to_markdown(self) -> str:
        return serialize_frontmatter(self.meta, self.body)

    @property
    def links(self) -> list[str]:
        """Unique ``[[wikilink]]`` targets from frontmatter values and body,
        in first-seen order."""
        targets: list[str] = []
        seen: set[str] = set()
        for s in [*_iter_strings(self.meta), self.body]:
            for raw in _WIKILINK.findall(s):
                target = raw.strip()
                if target not in seen:
                    seen.add(target)
                    targets.append(target)
        return targets

    @property
    def relations(self) -> list[tuple[str, str]]:
        """``(relation, target-id)`` pairs from the ``links`` frontmatter list —
        the labelled edges this entity draws by hand. Each item is
        ``"<rel> :: [[target]]"``; the ``<rel> ::`` prefix is optional and
        defaults to ``related``. This is what turns a curated ``[[wikilink]]``
        into a graph edge."""
        out: list[tuple[str, str]] = []
        for item in self.meta.get("links") or []:
            if not isinstance(item, str):
                continue
            rel, rest = "related", item
            if "::" in item:
                head, rest = item.split("::", 1)
                rel = head.strip() or "related"
            m = _WIKILINK.search(rest)
            target = (m.group(1) if m else rest).strip()
            if target:
                out.append((rel, target))
        return out
