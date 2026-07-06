from manifexa.store.entity import Entity


def test_from_markdown_reads_core_fields():
    text = "---\ntype: person\ntitle: Noam Shazeer\nstatus: curated\n---\n\nNotes here.\n"
    e = Entity.from_markdown("person/noam-shazeer", text)
    assert e.id == "person/noam-shazeer"
    assert e.type == "person"
    assert e.title == "Noam Shazeer"
    assert e.status == "curated"
    assert e.body == "Notes here.\n"


def test_status_defaults_to_candidate():
    e = Entity.from_markdown("paper/x", "---\ntype: paper\ntitle: X\n---\n\n")
    assert e.status == "candidate"


def test_to_markdown_roundtrips():
    text = "---\ntype: paper\ntitle: Attention\nstatus: curated\n---\n\nThe paper.\n"
    e = Entity.from_markdown("paper/attention", text)
    e2 = Entity.from_markdown("paper/attention", e.to_markdown())
    assert e2.meta == e.meta
    assert e2.body == e.body


def test_links_collects_wikilinks_from_meta_and_body_deduped():
    text = (
        "---\n"
        "type: person\n"
        "title: Noam Shazeer\n"
        'affiliations: ["[[Google Brain]]", "[[Character.AI]]"]\n'
        "---\n\n"
        "Bridges [[Your NLP Lab]] and [[Google Brain]].\n"
    )
    e = Entity.from_markdown("person/noam-shazeer", text)
    assert e.links == ["Google Brain", "Character.AI", "Your NLP Lab"]
