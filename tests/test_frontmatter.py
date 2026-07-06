from manifexa.store.frontmatter import parse_frontmatter, serialize_frontmatter


def test_parse_splits_yaml_and_body():
    text = "---\ntype: person\ntitle: Noam Shazeer\n---\n\nKeeps reappearing.\n"
    meta, body = parse_frontmatter(text)
    assert meta == {"type": "person", "title": "Noam Shazeer"}
    assert body == "Keeps reappearing.\n"


def test_parse_without_frontmatter_returns_empty_meta_and_full_body():
    text = "just some notes, no frontmatter\n"
    meta, body = parse_frontmatter(text)
    assert meta == {}
    assert body == "just some notes, no frontmatter\n"


def test_parse_empty_frontmatter_block():
    text = "---\n---\nbody only\n"
    meta, body = parse_frontmatter(text)
    assert meta == {}
    assert body == "body only\n"


def test_serialize_then_parse_roundtrips():
    meta = {"type": "paper", "title": "Attention Is All You Need", "year": 2017}
    body = "The foundational transformer paper.\n"
    text = serialize_frontmatter(meta, body)
    meta2, body2 = parse_frontmatter(text)
    assert meta2 == meta
    assert body2 == body


def test_serialize_starts_with_fence():
    text = serialize_frontmatter({"type": "lab"}, "notes")
    assert text.startswith("---\n")
