"""Per-type node schema — the enforced shape of a knowledge-graph node.

Each entity type declares its scalar ATTRIBUTES (name → kind, with a few marked
``required`` or ``recommended``) and its RELATION kinds (typed edges → the
target types they may point at). ``validate`` checks an entity against this on
write, so the graph stays clean enough to explore on; ``relation_ok`` checks an
edge's endpoints. A handful of UNIVERSAL fields (external ids, tags) are allowed
on any type, and the notes body is always free-form.

Enforcement is deliberately graded: a *missing required field* or a *bad-typed
value* or a *relation to a disallowed target* is an ERROR (rejected on write);
a *missing recommended field*, an *unknown attribute*, or an *unknown relation
name* is a WARN (surfaced, but allowed) — so you can still jot a rough paper by
hand and get a nudge rather than a wall.
"""
from __future__ import annotations

from dataclasses import dataclass

_ANY = ("*",)

# type -> {"attrs": {name: (kind, flag)}, "rels": {name: (target types…)}}
# kind ∈ {str, text, int, url, list};  flag ∈ {"", "required", "recommended"}
SCHEMA: dict[str, dict] = {
    "paper": {
        "attrs": {"title": ("str", "required"), "year": ("int", "recommended"),
                  "doi": ("str", "recommended"), "url": ("url", ""), "venue": ("str", ""),
                  "abstract": ("text", ""), "authors": ("list", ""), "topics": ("list", "")},
        "rels": {"authored": ("person",), "about": ("topic", "concept"),
                 "cites": ("paper", "book"), "related": _ANY},
    },
    "person": {
        "attrs": {"title": ("str", "required"), "orcid": ("str", ""),
                  "affiliation": ("str", ""), "url": ("url", "")},
        "rels": {"authored": ("paper", "book"), "affiliated_with": ("lab",), "related": _ANY},
    },
    "lab": {
        "attrs": {"title": ("str", "required"), "url": ("url", ""), "location": ("str", "")},
        "rels": {"affiliated_with": ("person",), "related": _ANY},
    },
    "topic": {
        "attrs": {"title": ("str", "required"), "description": ("text", "")},
        "rels": {"about": ("paper", "book"), "related": _ANY, "part_of": ("topic",)},
    },
    "concept": {
        "attrs": {"title": ("str", "required"), "description": ("text", ""), "kind": ("str", "")},
        "rels": {"about": ("paper", "book"), "related": _ANY, "part_of": ("concept",)},
    },
    "book": {
        "attrs": {"title": ("str", "required"), "year": ("int", ""), "isbn": ("str", ""),
                  "url": ("url", ""), "publisher": ("str", ""), "authors": ("list", "")},
        "rels": {"authored": ("person",), "about": ("topic", "concept"), "related": _ANY},
    },
    "note": {
        "attrs": {"title": ("str", "required")},
        "rels": {"related": _ANY},
    },
}

IDENTITY = ("type", "title", "status")
RELATION_KEY = "links"                       # frontmatter list carrying [[wikilink]] relations
UNIVERSAL_ATTRS = {"openalex": "str", "semantic_scholar": "str", "tags": "list", "aliases": "list"}


class SchemaError(ValueError):
    """Raised when a write violates the schema (one or more hard errors)."""


@dataclass(frozen=True)
class Issue:
    severity: str        # "error" | "warn"
    field: str
    message: str


def types() -> tuple[str, ...]:
    return tuple(SCHEMA)


def attrs_for(type: str) -> dict:
    return SCHEMA.get(type, {}).get("attrs", {})


def rels_for(type: str) -> dict:
    return SCHEMA.get(type, {}).get("rels", {})


def _empty(v) -> bool:
    return v is None or v == "" or v == []


def _typed_ok(kind: str, value) -> bool:
    if kind == "int":
        try:
            int(value)
            return True
        except (TypeError, ValueError):
            return False
    if kind == "list":
        return isinstance(value, (list, tuple))
    if kind == "url":
        return isinstance(value, str)      # shape is lenient; presence is what matters
    return isinstance(value, str)          # str / text


def validate(entity) -> list[Issue]:
    """All schema issues for ``entity`` (errors + warnings), in field order."""
    t = entity.type
    if t not in SCHEMA:
        return [Issue("error", "type", f"unknown type '{t}' — one of: {', '.join(SCHEMA)}")]

    issues: list[Issue] = []
    attrs = attrs_for(t)
    for name, (_kind, flag) in attrs.items():
        if _empty(entity.meta.get(name)):
            if flag == "required":
                issues.append(Issue("error", name, f"{t} requires '{name}'"))
            elif flag == "recommended":
                issues.append(Issue("warn", name, f"{t} usually has a '{name}'"))

    for k, v in entity.meta.items():
        if k in IDENTITY or k == RELATION_KEY:
            continue
        if k in UNIVERSAL_ATTRS:
            if not _empty(v) and not _typed_ok(UNIVERSAL_ATTRS[k], v):
                issues.append(Issue("error", k, f"'{k}' must be a {UNIVERSAL_ATTRS[k]}"))
            continue
        if k not in attrs:
            issues.append(Issue("warn", k, f"'{k}' isn't a known {t} field"))
            continue
        kind = attrs[k][0]
        if not _empty(v) and not _typed_ok(kind, v):
            issues.append(Issue("error", k, f"'{k}' must be a {kind}"))
    return issues


def errors(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.severity == "error"]


def warnings(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.severity == "warn"]


def valid_relations(src_type: str, dst_type: str) -> list[str]:
    """Relation names on ``src_type`` that may point at a ``dst_type``."""
    return [r for r, tg in rels_for(src_type).items() if tg == _ANY or (dst_type and dst_type in tg)]


def relation_ok(src_type: str, rel: str, dst_type: str) -> Issue | None:
    """Validate an edge ``src_type --rel--> dst_type``. Returns an error Issue if
    the target type is disallowed (with a hint at relations that would fit), a
    warn Issue for an unknown relation name, or ``None`` when it's clean."""
    rels = rels_for(src_type)
    if rel not in rels:
        return Issue("warn", rel, f"'{rel}' isn't a standard {src_type} relation")
    targets = rels[rel]
    if targets == _ANY or not dst_type or dst_type in targets:
        return None
    alt = valid_relations(src_type, dst_type)
    hint = f" — for {src_type} → {dst_type} use: {', '.join(alt)}" if alt else ""
    return Issue("error", rel, f"{src_type} '{rel}' expects {'/'.join(targets)}, not {dst_type}{hint}")
