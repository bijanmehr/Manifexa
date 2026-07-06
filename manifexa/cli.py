"""Manifexa CLI — drive the real machinery from the terminal.

    manifexa add <DOI|OpenAlex id>     seed + enrich
    manifexa around <entity-id>        surface hidden connections
    manifexa path <a> <b>              the chain between two nodes
    manifexa bridges                   the connectors in your graph
    manifexa open <entity-id>          print an entity
    manifexa list                      list curated entities
    manifexa                           interactive terminal REPL (also: manifexa shell)
    manifexa <vault-path>              open that folder as the vault (e.g. manifexa ~/research)

Data lives under --home (default $MANIFEXA_HOME or ~/.manifexa).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .app import App
from .graph.factory import engine_from_env


def _default_home() -> str:
    return os.environ.get("MANIFEXA_HOME", str(Path.home() / ".manifexa"))


_SUBCOMMANDS = {"list", "bridges", "clusters", "embed", "export", "import", "add",
                "around", "similar", "open", "new", "path", "promote", "shell", "manual"}


def _is_vault_path(s: str) -> bool:
    """A bare first argument that names a folder (not a flag or subcommand) means
    'open this vault' — e.g. ``manifexa ~/research``."""
    return (not s.startswith("-") and s not in _SUBCOMMANDS
            and ("/" in s or s.startswith("~") or s.startswith(".")
                 or os.path.isdir(os.path.expanduser(s))))


def _rewrite_argv(argv):
    """`manifexa <vault-path> [--plain]` → open that folder's shell."""
    if argv and _is_vault_path(argv[0]):
        return ["--home", os.path.expanduser(argv[0]), "shell", *argv[1:]]
    return argv


def _print_results(results):
    for r in results:
        print(f"  ▸ {r.get('title') or r['key']:<48}  {r.get('reason', '')}")
    if not results:
        print("  (nothing surfaced yet)")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    argv = _rewrite_argv(argv)          # `manifexa <vault-path>` opens that folder's shell
    parser = argparse.ArgumentParser(prog="manifexa", description="A personal research knowledge graph.")
    parser.add_argument("--home", default=_default_home())
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("list")
    sub.add_parser("bridges")
    sub.add_parser("clusters")
    sub.add_parser("embed")
    p = sub.add_parser("export"); p.add_argument("--out", default=None)
    p = sub.add_parser("import"); p.add_argument("path")
    p = sub.add_parser("add"); p.add_argument("seed")
    p = sub.add_parser("around"); p.add_argument("id")
    p = sub.add_parser("similar"); p.add_argument("id")
    p = sub.add_parser("open"); p.add_argument("id")
    p = sub.add_parser("new"); p.add_argument("type"); p.add_argument("title", nargs="+")
    p = sub.add_parser("path"); p.add_argument("a"); p.add_argument("b")
    p = sub.add_parser("promote"); p.add_argument("key"); p.add_argument("--note", default="")
    p = sub.add_parser("shell"); p.add_argument("--plain", action="store_true")
    sub.add_parser("manual")

    args = parser.parse_args(argv)
    if args.cmd == "manual":                     # static page — no engine/JVM needed
        from .tui import render_manual, Style, _supports_color

        print(render_manual(Style(_supports_color())))
        return 0

    app = App(args.home, engine=engine_from_env(args.home))

    if args.cmd == "list":
        for e in app.list():
            print(f"  {e.id:<44}  {e.title}")
    elif args.cmd == "add":
        res = app.add(args.seed)
        print(f"+ {res['entity']}  ·  {res['nodes']} nodes, {res['edges']} edges cached")
    elif args.cmd == "around":
        _print_results(app.around(args.id))
    elif args.cmd == "similar":
        _print_results([{**r, "reason": f"similarity {r['score']:.3f}"} for r in app.similar(args.id)])
    elif args.cmd == "bridges":
        _print_results([{**r, "reason": f"betweenness {r['score']:.3f}"} for r in app.bridges()])
    elif args.cmd == "clusters":
        for i, c in enumerate(app.clusters(), 1):
            preview = ", ".join(c["members"][:6]) + ("…" if c["size"] > 6 else "")
            print(f"  cluster {i} · {c['size']} nodes: {preview}")
    elif args.cmd == "embed":
        print(f"  embedded {app.embed()['embedded']} papers (Semantic Scholar)")
    elif args.cmd == "export":
        import json

        data = app.snapshot()
        if args.out:
            Path(args.out).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            c = data["counts"]
            print(f"  exported {c['entities']} entities, {c['cache_nodes']} candidates, {c['cache_edges']} edges → {args.out}")
        else:
            print(json.dumps(data, indent=2, ensure_ascii=False))
    elif args.cmd == "import":
        import json

        stats = app.restore(json.loads(Path(args.path).read_text(encoding="utf-8")))
        print(f"  imported {stats['entities']} entities, {stats['cache_nodes']} candidates, {stats['cache_edges']} edges")
    elif args.cmd == "path":
        chain = app.path(args.a, args.b)
        if not chain:
            print("  (no path found)")
        else:
            for s in chain:
                arrow = f"  → {s['rel_to_next']}" if s["rel_to_next"] else ""
                print(f"  {s.get('title') or s['key']}{arrow}")
    elif args.cmd == "open":
        e = app.open(args.id)
        print(e.to_markdown())
    elif args.cmd == "new":
        print("created →", app.create(args.type, " ".join(args.title)))
    elif args.cmd == "promote":
        print("promoted →", app.promote(args.key, note=args.note))
    elif args.cmd in ("shell", None):
        try:
            if getattr(args, "plain", False):
                from .tui import repl

                repl(app)
            else:
                from . import tui_app

                tui_app.run(app)  # split TUI; falls back to the plain shell if unavailable
        finally:
            try:
                app.engine.close()
            except Exception:
                pass
            # The embedded ArcadeDB JVM (and prompt_toolkit's loop) can leave
            # non-daemon threads that hang a normal exit — force the process to stop.
            os._exit(0)
    else:
        parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
