from manifexa.store.entity import Entity
from manifexa.store.vault import Vault


def test_write_then_read_roundtrips(tmp_path):
    vault = Vault(tmp_path)
    e = Entity(
        id="person/noam-shazeer",
        meta={"type": "person", "title": "Noam Shazeer", "status": "curated"},
        body="Notes.\n",
    )
    vault.write(e)
    got = vault.read("person/noam-shazeer")
    assert got.id == e.id
    assert got.meta == e.meta
    assert got.body == e.body


def test_write_creates_typed_subdirectory(tmp_path):
    vault = Vault(tmp_path)
    vault.write(Entity(id="paper/attention", meta={"type": "paper", "title": "Attention"}))
    assert (tmp_path / "paper" / "attention.md").exists()


def test_exists(tmp_path):
    vault = Vault(tmp_path)
    assert not vault.exists("lab/x")
    vault.write(Entity(id="lab/x", meta={"type": "lab", "title": "X"}))
    assert vault.exists("lab/x")


def test_list_returns_all_entities(tmp_path):
    vault = Vault(tmp_path)
    vault.write(Entity(id="person/a", meta={"type": "person", "title": "A"}))
    vault.write(Entity(id="paper/b", meta={"type": "paper", "title": "B"}))
    ids = sorted(e.id for e in vault.list())
    assert ids == ["paper/b", "person/a"]


def test_delete_removes_file(tmp_path):
    vault = Vault(tmp_path)
    vault.write(Entity(id="paper/x", meta={"type": "paper", "title": "X"}))
    assert vault.exists("paper/x")
    vault.delete("paper/x")
    assert not vault.exists("paper/x")


def test_delete_missing_is_silent(tmp_path):
    Vault(tmp_path).delete("paper/nope")  # must not raise
