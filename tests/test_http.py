import urllib.error

import pytest

from manifexa.sources.http import get_json


class FakeResp:
    def __init__(self, data):
        self._d = data

    def read(self):
        return self._d

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_get_json_retries_transient_then_succeeds():
    calls = {"n": 0}

    def opener(req, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.HTTPError(req.full_url, 503, "busy", {}, None)
        return FakeResp(b'{"ok": true}')

    out = get_json("http://x", retries=3, backoff=0, _opener=opener)
    assert out == {"ok": True}
    assert calls["n"] == 3


def test_get_json_raises_after_exhausting_retries():
    def opener(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 503, "busy", {}, None)

    with pytest.raises(urllib.error.HTTPError):
        get_json("http://x", retries=2, backoff=0, _opener=opener)


def test_get_json_does_not_retry_404():
    calls = {"n": 0}

    def opener(req, timeout):
        calls["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 404, "nope", {}, None)

    with pytest.raises(urllib.error.HTTPError):
        get_json("http://x", retries=3, backoff=0, _opener=opener)
    assert calls["n"] == 1  # 404 is not transient — no retry
