from manifexa.eminexa.people import PeopleClient


class FakeOA:
    def __init__(self):
        self.calls = []

    def _get(self, path, params):          # mirrors OpenAlexClient._get
        self.calls.append((path, params))
        if path.startswith("authors/"):
            return {"id": "https://openalex.org/A1", "display_name": "X"}
        if path == "authors":
            return {"results": [{"id": "https://openalex.org/A1"}]}
        return {"results": [{"id": "https://openalex.org/W1", "title": "P"}]}


def test_get_author_and_works_and_orcid():
    pc = PeopleClient(FakeOA())
    assert pc.get_author("A1")["display_name"] == "X"
    works = pc.works_by_author("A1", from_date="2021-07-12")
    assert works[0]["id"].endswith("W1")
    assert pc.author_by_orcid("0000-0002-1243-7707")["id"].endswith("A1")


def test_search_works_passes_query_and_selects_authorships():
    oa = FakeOA()
    PeopleClient(oa).search_works("deep learning", per_page=1)
    path, params = next(c for c in oa.calls if c[0] == "works")
    assert params["search"] == "deep learning"
    assert "authorships" in params["select"]


def test_works_query_filters_by_author_and_date():
    oa = FakeOA()
    PeopleClient(oa).works_by_author("https://openalex.org/A1", from_date="2021-01-01")
    path, params = next(c for c in oa.calls if c[0] == "works")
    assert "author.id:A1" in params["filter"]
    assert "from_publication_date:2021-01-01" in params["filter"]


def test_retries_on_429_then_succeeds():
    import urllib.error

    class Flaky:
        def __init__(self):
            self.n = 0

        def _get(self, path, params):
            self.n += 1
            if self.n == 1:
                raise urllib.error.HTTPError(path, 429, "Too Many Requests", {}, None)
            return {"id": "https://openalex.org/A1", "display_name": "ok"}

    # tiny backoff so the test is fast
    import manifexa.eminexa.people as people
    people._BACKOFF_BASE = 0.01
    pc = PeopleClient(Flaky())
    assert pc.get_author("A1")["display_name"] == "ok"


def test_retry_honors_retry_after_header():
    import urllib.error
    import manifexa.eminexa.people as people
    people._BACKOFF_BASE = 0.001

    class Flaky:
        def __init__(self):
            self.n = 0

        def _get(self, path, params):
            self.n += 1
            if self.n == 1:
                raise urllib.error.HTTPError(path, 429, "Too Many", {"Retry-After": "0"}, None)
            return {"id": "https://openalex.org/A1", "display_name": "ok"}

    assert PeopleClient(Flaky()).get_author("A1")["display_name"] == "ok"
