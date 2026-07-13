from manifexa.eminexa.clean import normalize, dedup_works


def test_normalize_unescapes_and_collapses():
    assert normalize("Computer Science &#x0026;  Technology") == "computer science & technology"
    assert normalize("  The  Robotics   Institute\n") == "the robotics institute"


def test_dedup_prefers_doi_and_merges_title_variants():
    works = [
        {"id": "W1", "title": "Split over n resource sharing", "doi": None, "publication_year": 2026, "authorships": [], "topics": []},
        {"id": "W2", "title": "Split over n resource sharing", "doi": "10.48550/arxiv.2604.26374", "publication_year": 2026, "authorships": [], "topics": []},
        {"id": "W3", "title": "A totally different paper", "doi": None, "publication_year": 2025, "authorships": [], "topics": []},
    ]
    out = dedup_works(works)
    ids = sorted(w["id"] for w in out)
    assert ids == ["W2", "W3"]          # W1/W2 are the same paper; the DOI-bearing W2 wins


def test_dedup_clusters_same_doi_across_title_variants():
    works = [
        {"id": "W1", "title": "Deep RL for Swarms", "doi": "10.1/x", "publication_year": 2024, "authorships": [], "topics": []},
        {"id": "W2", "title": "Deep RL for Swarms (extended)", "doi": "10.1/x", "publication_year": 2024, "authorships": [], "topics": []},
    ]
    assert len(dedup_works(works)) == 1     # same DOI ⇒ one paper regardless of title
