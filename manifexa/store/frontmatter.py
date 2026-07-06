"""Read and write Markdown files with YAML frontmatter.

A document is ``---\\n<yaml>\\n---\\n<body>``. The frontmatter holds structured,
machine- and LLM-readable metadata; the body holds free-text notes. These two
functions are the only place the on-disk format is defined.
"""
from __future__ import annotations

import yaml

_FENCE = "---"


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a document into ``(frontmatter, body)``.

    A document with no frontmatter block returns ``({}, text)``. The blank
    line(s) separating the closing fence from the body are stripped.
    """
    if text.startswith(_FENCE):
        lines = text.split("\n")
        for i in range(1, len(lines)):
            if lines[i].strip() == _FENCE:
                yaml_block = "\n".join(lines[1:i])
                body = "\n".join(lines[i + 1:]).lstrip("\n")
                meta = yaml.safe_load(yaml_block) or {}
                return meta, body
    return {}, text


def serialize_frontmatter(meta: dict, body: str) -> str:
    """Render ``(frontmatter, body)`` back to a Markdown document."""
    yaml_block = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip()
    return f"{_FENCE}\n{yaml_block}\n{_FENCE}\n\n{body}"
