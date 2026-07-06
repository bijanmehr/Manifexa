# Manifexa

```

               • • •• •    ••
           •   ••• •• ••• •••••
      ••••••··· ············••••    •
       •••······················•••• •
    ••••·······            ·······••••
  •••• ·····                  · · ·•••
  •• • · · · M A N I F E X A  · · · • •
    •• ·····                  · · ·••• •
    ••••·······            ·······••••
    ••• ••·······················••
         ••••·· ·············••• •••
           • ••••• •• •••••• ••
            • •    •• •• •

```

> **a personal research knowledge graph — it surfaces the connections you'd never think to search for**

Seed it by hand one thing at a time, let automation grow it around your seeds
(OpenAlex, Semantic Scholar, Crossref, or AI extraction), and mine it for the
people, papers, and links you'd never find by normal searching. Your data is
plain Markdown you own — the vault is Obsidian-compatible.

**You drive it from your terminal** — no browser, no server:

```bash
pip install -e ".[tui,arcadedb]"    # then:
manifexa                            # interactive split-pane TUI ( /commands · ASCII viz )
manifexa shell --plain              # simple scrolling shell
manifexa manual                     # the manual page + a system diagram
```

Type `help` or `manual` inside for everything.

## What it does

- **Files are the source of truth** — one Markdown + frontmatter file per entity
  under `<vault>/vault/` (`person/…md`, `paper/…md`, …), Obsidian-compatible. A
  SQLite `cache.db` holds candidates + embeddings. Both are yours to git / grep / edit.
- **The graph is derived** — rebuilt from your files into an **embedded ArcadeDB**
  (`graph.arcadedb/`, in-process — no server, no Docker) on every change, so it never
  needs backing up. Delete it and it regenerates.
- **Discovery is pulled** — `around` (hidden people), `similar` (hidden literature,
  via SPECTER2 embeddings), `path` (indirect chains), `bridges`, and `clusters`
  (emerging communities) — on demand, never a feed.
- **Capture is flexible** — `add` by DOI / OpenAlex id, `new` any entity by hand, or
  `extract` pasted text. Sources: OpenAlex + Semantic Scholar (embeddings) + Crossref.
- **LLM-powered (optional, pluggable)** — `expand` / `complete` / `ask` via Claude or a
  local Ollama model (`MANIFEXA_LLM=claude|ollama`); output is always candidates.
- **Vaults** — `vault <path>` switches between folders; `tree` lists what's inside.

## Engines

Pluggable behind one `GraphEngine` interface, chosen by `MANIFEXA_ENGINE`:

- **`arcadedb`** *(default)* — embedded, in-process, Cypher + vector, on-disk. No daemon.
- **`networkx`** — pure-Python, in-memory, zero-config fallback.
- **`neo4j`** — set `NEO4J_URI` to use a running Neo4j server.

Discovery is identical on any engine.

## Develop

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[tui,arcadedb,ai,dev]"
python -m pytest                        # all green
```

Everything runs offline: the network sources (OpenAlex, Semantic Scholar) and the
LLM providers are injected, so their logic is tested against fakes / recorded
fixtures — the suite needs no keys and no servers.
