from manifexa.eminexa.node import build_person_node

AUTHOR = {
    "id": "https://openalex.org/A5081322765",
    "display_name": "Jan Blumenkamp",
    "display_name_alternatives": ["Blumenkamp, Jan"],
    "orcid": "https://orcid.org/0000-0002-1243-7707",
    "works_count": 24, "cited_by_count": 60,
    "summary_stats": {"h_index": 3},
}
WORKS = [
    {"id": "https://openalex.org/W1", "title": "Paper A", "doi": None, "publication_year": 2025,
     "topics": [{"display_name": "RL in Robotics"}],
     "authorships": [
        {"author": {"id": "https://openalex.org/A5081322765", "display_name": "Jan Blumenkamp"},
         "raw_affiliation_strings": ["Dept of CS, University of Cambridge"], "institutions": []},
        {"author": {"id": "https://openalex.org/A5066624177", "display_name": "Amanda Prorok"},
         "institutions": []}]},
]


def test_build_person_node_shape():
    node = build_person_node(AUTHOR, WORKS, today_year=2026)
    assert node["key"] == "A5081322765"
    assert node["type"] == "person"
    assert node["title"] == "Jan Blumenkamp"
    m = node["meta"]
    assert m["openalex"] == "A5081322765"
    assert m["orcid"] == "0000-0002-1243-7707"
    assert m["h_index"] == 3
    assert m["window_work_ids"] == ["W1"]
    assert "RL in Robotics" in m["topics"]
    assert m["source"] == "eminexa"
    assert any(c["id"] == "A5066624177" and c["name"] == "Amanda Prorok" for c in m["coauthors"])
    # the author's own affiliation string is captured, not a coauthor edge to self
    assert "Dept of CS, University of Cambridge" in m["affiliations"]
    assert all(c["id"] != "A5081322765" for c in m["coauthors"])   # never a self-coauthor


def test_coauthor_counts_and_recency():
    works = [
        {"id": "https://openalex.org/W1", "title": "A", "doi": None, "publication_year": 2023, "topics": [],
         "authorships": [{"author": {"id": "https://openalex.org/A1", "display_name": "Seed"}},
                         {"author": {"id": "https://openalex.org/A2", "display_name": "Co"}}]},
        {"id": "https://openalex.org/W2", "title": "B", "doi": None, "publication_year": 2025, "topics": [],
         "authorships": [{"author": {"id": "https://openalex.org/A1", "display_name": "Seed"}},
                         {"author": {"id": "https://openalex.org/A2", "display_name": "Co"}}]},
    ]
    m = build_person_node({"id": "A1", "display_name": "Seed"}, works, today_year=2026)["meta"]
    co = next(c for c in m["coauthors"] if c["id"] == "A2")
    assert co["n_shared"] == 2
    assert co["last_year"] == 2025
