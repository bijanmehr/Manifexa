from manifexa import tui
from manifexa.app import App
import manifexa.eminexa as em


def test_aliases_route_to_existing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)          # so `save` writes into tmp, not the repo
    app = App(str(tmp_path))
    for line in ("near topic/x", "groups", "drop", "save", "load"):
        assert "unknown command" not in tui.dispatch(app, line)


def test_help_shows_clean_verbs():
    for verb in ("add", "who", "near", "groups", "bridges", "path", "map", "save", "drop", "expand"):
        assert verb in tui.HELP


def test_help_leads_with_eminexa():
    assert "Eminexa" in tui.HELP


def test_package_names_eminexa():
    assert "Eminexa" in (em.__doc__ or "")
