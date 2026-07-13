"""Author-centric OpenAlex fetches with a polite throttle (≤10 req/s) and 429
backoff. Wraps an OpenAlexClient (or any object exposing ``_get(path, params)``),
so ingest can't get rate-limited (we hit sustained 429s during design)."""
from __future__ import annotations

import time
import urllib.error

from ..sources.openalex import normalize_openalex_id

_MIN_INTERVAL = 0.12          # ~8 req/s, under OpenAlex's 10/s
_BACKOFF_BASE = 2.0           # seconds; grows per retry (overridable in tests)
_last = [0.0]


def _throttle() -> None:
    dt = time.monotonic() - _last[0]
    if dt < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - dt)
    _last[0] = time.monotonic()


class PeopleClient:
    """Author + works fetches for Eminexa. Thin over an OpenAlexClient."""

    def __init__(self, oa, tries: int = 5) -> None:
        self._oa = oa
        self._tries = tries

    def _get(self, path, params=None) -> dict:
        for i in range(self._tries):
            _throttle()
            try:
                return self._oa._get(path, params or {})
            except urllib.error.HTTPError as e:
                if e.code == 429 and i < self._tries - 1:
                    retry_after = 0
                    try:
                        retry_after = int((e.headers or {}).get("Retry-After") or 0)
                    except (TypeError, ValueError):
                        retry_after = 0
                    time.sleep(max(retry_after, _BACKOFF_BASE * (2 ** i)))   # honor Retry-After, else exp backoff
                    continue
                raise
        raise RuntimeError("unreachable")

    def get_author(self, author_id) -> dict:
        return self._get(f"authors/{normalize_openalex_id(author_id)}")

    def works_by_author(self, author_id, from_date: str, cap: int = 200) -> list[dict]:
        aid = normalize_openalex_id(author_id)
        sel = "id,title,doi,publication_year,topics,authorships"
        return self._get("works", {
            "filter": f"author.id:{aid},from_publication_date:{from_date}",
            "sort": "publication_date:desc", "per_page": str(cap), "select": sel,
        }).get("results", [])

    def search_works(self, query: str, per_page: int = 1) -> list[dict]:
        """Title/keyword search — used to paper-anchor a Scholar profile to an
        OpenAlex author (results carry authorships for name-matching)."""
        sel = "id,title,doi,publication_year,authorships"
        return self._get("works", {"search": query, "per_page": str(per_page),
                                    "select": sel}).get("results", [])

    def author_by_orcid(self, orcid) -> dict | None:
        r = self._get("authors", {"filter": f"orcid:{orcid}", "per_page": "1"}).get("results", [])
        return r[0] if r else None
