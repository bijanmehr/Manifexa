"""Resolve a seed to an authoritative OpenAlex author id — never by bare name.

v1 seeds: an OpenAlex author id (``A…``) or an ORCID (bare or as an orcid.org
URL). A Google-Scholar URL is the agreed *default* input but its resolution
(fetch profile → paper-anchor → OpenAlex author) is Phase 2, so it raises a clear
deferral for now rather than guessing."""
from __future__ import annotations

import re

_ORCID = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")


def resolve_seed(pc, seed: str) -> str:
    s = (seed or "").strip()
    if "scholar.google." in s:
        raise ValueError("Scholar URLs are resolved during ingest, not resolve_seed")
    # canonical ids are uppercase (A…, ORCID check-char X); the TUI gate accepts
    # lowercase (re.I), so normalise here too or a routed seed would error out.
    s = s.replace("https://orcid.org/", "").replace("http://orcid.org/", "").upper()
    if re.fullmatch(r"A\d+", s):
        return s
    if _ORCID.match(s):
        a = pc.author_by_orcid(s)
        if a:
            return a["id"].split("/")[-1]
        raise ValueError(f"no OpenAlex author for ORCID {s}")
    raise ValueError(f"unrecognized seed '{seed}' — use an OpenAlex author id (A…) or an ORCID")
