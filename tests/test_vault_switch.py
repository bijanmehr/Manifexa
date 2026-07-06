"""Switching vault folders + the vault/tree views + the `manifexa <path>` shorthand."""
import os

from manifexa.app import App
from manifexa.cli import _rewrite_argv
from manifexa.tui import dispatch


def test_cli_vault_path_opens_that_folder_as_shell():
    assert _rewrite_argv(["~/manifexa_test"]) == ["--home", os.path.expanduser("~/manifexa_test"), "shell"]
    assert _rewrite_argv(["~/v", "--plain"]) == ["--home", os.path.expanduser("~/v"), "shell", "--plain"]
    assert _rewrite_argv(["./data"])[0] == "--home"
    # real subcommands and flags are left untouched
    assert _rewrite_argv(["list"]) == ["list"]
    assert _rewrite_argv(["add", "10.1/x"]) == ["add", "10.1/x"]
    assert _rewrite_argv(["--home", "/x", "shell"]) == ["--home", "/x", "shell"]


def test_reopen_switches_vault(tmp_path, monkeypatch):
    monkeypatch.setenv("MANIFEXA_ENGINE", "networkx")
    a = App(str(tmp_path / "v1"))
    a.create("person", "Ada Lovelace")
    a.reopen(str(tmp_path / "v2"))
    assert a.list() == []                                    # v2 is a fresh, empty vault
    a.create("paper", "On Engines")
    a.reopen(str(tmp_path / "v1"))
    assert [e.title for e in a.list()] == ["Ada Lovelace"]   # v1 kept its note


def test_vault_command_shows_folder_and_counts(tmp_path):
    a = App(str(tmp_path / "phd"))
    a.create("person", "Ada")
    a.create("paper", "P")
    out = dispatch(a, "vault")
    assert "phd" in out and "person" in out and "paper" in out


def test_tree_lists_files(tmp_path):
    a = App(str(tmp_path / "v"))
    a.create("person", "Ada Lovelace")
    assert "ada-lovelace" in dispatch(a, "tree")


def test_vault_switch_via_command(tmp_path, monkeypatch):
    monkeypatch.setenv("MANIFEXA_ENGINE", "networkx")
    a = App(str(tmp_path / "v1"))
    a.create("person", "Ada")
    out = dispatch(a, f"vault {tmp_path / 'v2'}")
    assert a.list() == []          # switched to the empty v2
    assert "v2" in out             # and the view shows the new vault
