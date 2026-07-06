"""Semantic discovery — "hidden literature" by embedding similarity.

Papers (and other entities) carry dense vectors (e.g. Semantic Scholar's
SPECTER2). Cosine similarity over those vectors surfaces work that's *about the
same thing* even with no citation or authorship link — the connection search
and citation-chasing miss. Personal scale, so similarity is computed in-process
with numpy; no vector database needed.
"""
from __future__ import annotations

import numpy as np


def cosine(a, b) -> float:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def similar(cache, key: str, limit: int = 10) -> list[dict]:
    """The entities whose embeddings are most similar to ``key``'s."""
    target = cache.get_embedding(key)
    if target is None:
        return []
    out = [
        {"key": k, "score": cosine(target, vec)}
        for k, vec in cache.embeddings().items()
        if k != key
    ]
    out.sort(key=lambda r: -r["score"])
    return out[:limit]
