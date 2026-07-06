"""Stable, human-readable identifiers.

An entity's id is ``<type>/<slug-of-title>`` — which is also its path in the
vault. Slugs are lowercase, alphanumeric, hyphen-separated.
"""
from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    return _NON_ALNUM.sub("-", text.lower()).strip("-")


def make_id(type: str, title: str) -> str:
    return f"{slugify(type)}/{slugify(title)}"
