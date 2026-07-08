# Manifexa — Obsidian plugin (personal)

A note generator for your research vault. Turns a DOI into a fully-filled paper
note and stubs out its authors + topics, so a single command populates a
connected, navigable graph. Self-contained: it talks only to OpenAlex and your
local balthar (Ollama) tunnel, and writes plain Markdown. The manifexa engine
still curates the graph DB from those same files, separately.

## Install (manual — it's a personal plugin, not in the store)

Copy this folder into your vault's plugins directory as `manifexa`:

```
cp -r obsidian-plugin  ~/manifexa_test/vault/.obsidian/plugins/manifexa
```

(`main.js` and `manifest.json` must sit directly in `.obsidian/plugins/manifexa/`.)

Then in Obsidian: **Settings → Community plugins → turn off Restricted mode →
enable "Manifexa"**. Reload if it doesn't appear.

## Use

- **Add paper by DOI** — command palette (`Cmd-P`) or the graph ribbon icon.
  Paste a DOI / arXiv-DOI URL / OpenAlex id → it writes:
  - `paper/<slug>.md` — title, authors, year, venue, topics, abstract;
  - `person/<slug>.md` for each author, `topic/<slug>.md` for each topic
    (stubs with `aliases`, so the `[[wikilinks]]` resolve).
- **Suggest related (via balthar)** — on an open note, asks your local LLM for
  adjacent topics/papers.

## Settings

Folders (`paper` / `person` / `topic`), an optional OpenAlex `mailto`, and the
balthar URL + model (default `http://localhost:11435`, `qwen3-coder-next:q8_0`).
For balthar, bring the tunnel up first: `ssh -fN -L 11435:localhost:11434 balthar`.

## Notes

- It never overwrites an existing note — safe to re-run.
- Everything it writes is plain Markdown the manifexa engine reads; nothing is
  locked to this plugin.
