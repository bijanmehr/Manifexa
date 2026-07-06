"""Shared HTTP — JSON GET with retry/backoff for transient failures.

Every source (OpenAlex, Semantic Scholar, Crossref) goes through this, so rate
limits (429) and 5xx blips back off and retry instead of failing the call.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

_TRANSIENT = {429, 500, 502, 503, 504}


def get_json(url, headers=None, timeout=15, retries=3, backoff=0.5, _opener=None):
    opener = _opener or (lambda req, t: urllib.request.urlopen(req, timeout=t))
    req = urllib.request.Request(url, headers=headers or {})
    for attempt in range(retries + 1):
        try:
            with opener(req, timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in _TRANSIENT and attempt < retries:
                time.sleep(backoff * (2 ** attempt))
                continue
            raise
        except urllib.error.URLError:
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
                continue
            raise
