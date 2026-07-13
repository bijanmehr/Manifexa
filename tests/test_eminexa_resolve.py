import pytest

from manifexa.eminexa.resolve import resolve_seed


class FakePC:
    def author_by_orcid(self, orcid):
        return {"id": "https://openalex.org/A9"} if orcid == "0000-0002-1243-7707" else None


def test_resolve_openalex_id_passthrough():
    assert resolve_seed(FakePC(), "A5081322765") == "A5081322765"


def test_resolve_orcid():
    assert resolve_seed(FakePC(), "0000-0002-1243-7707") == "A9"


def test_resolve_orcid_url():
    assert resolve_seed(FakePC(), "https://orcid.org/0000-0002-1243-7707") == "A9"


def test_resolve_lowercase_openalex_id_is_normalized():
    # the TUI gate accepts lowercase (re.I); resolution must too — not error out
    assert resolve_seed(FakePC(), "a5081322765") == "A5081322765"


def test_resolve_orcid_lowercase_checkchar_is_normalized():
    seen = {}

    class PC:
        def author_by_orcid(self, orcid):
            seen["orcid"] = orcid
            return {"id": "https://openalex.org/A9"}

    resolve_seed(PC(), "0000-0002-1243-770x")
    assert seen["orcid"] == "0000-0002-1243-770X"       # uppercased before the lookup


def test_resolve_unknown_orcid_raises():
    with pytest.raises(ValueError):
        resolve_seed(FakePC(), "0000-0000-0000-0000")


def test_resolve_scholar_url_is_deferred():
    with pytest.raises(ValueError, match="Scholar"):
        resolve_seed(FakePC(), "https://scholar.google.com/citations?user=abc")


def test_resolve_garbage_raises():
    with pytest.raises(ValueError):
        resolve_seed(FakePC(), "not-a-seed")
