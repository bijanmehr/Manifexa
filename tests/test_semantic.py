from manifexa.discovery.semantic import cosine, similar
from manifexa.store.cache import Cache


def test_cosine_identical_is_one():
    assert cosine([1, 0, 0], [1, 0, 0]) == 1.0


def test_cosine_orthogonal_is_zero():
    assert cosine([1, 0], [0, 1]) == 0.0


def test_cosine_zero_vector_is_zero():
    assert cosine([0, 0], [1, 1]) == 0.0


def test_similar_ranks_by_cosine():
    c = Cache()
    c.set_embedding("target", [1.0, 0.0])
    c.set_embedding("near", [0.9, 0.1])
    c.set_embedding("far", [0.0, 1.0])
    res = similar(c, "target")
    assert [r["key"] for r in res] == ["near", "far"]
    assert res[0]["score"] > res[1]["score"]


def test_similar_unknown_key_returns_empty():
    assert similar(Cache(), "nope") == []
