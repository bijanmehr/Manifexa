from manifexa.store.slug import slugify, make_id


def test_slugify_basic():
    assert slugify("Noam Shazeer") == "noam-shazeer"


def test_slugify_strips_punctuation_and_collapses_runs():
    assert slugify("Attention Is All You Need!") == "attention-is-all-you-need"
    assert slugify("Character.AI") == "character-ai"
    assert slugify("  Hello,   World  ") == "hello-world"


def test_make_id_combines_type_and_title():
    assert make_id("person", "Noam Shazeer") == "person/noam-shazeer"
    assert make_id("paper", "Attention Is All You Need") == "paper/attention-is-all-you-need"
