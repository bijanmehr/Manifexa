# Manifexa People-Network Graph — Design

**Date:** 2026-07-12
**Status:** design approved, ready for implementation plan
**Repurposes:** the (currently empty) ArcadeDB graph engine at `~/.manifexa/graph.arcadedb`

## 1. Goal

Turn the *people* behind papers into a graph: **persons are nodes**, connected by
**coauthorship** and **group membership**, so we can find relevant people, see who
works with whom, and surface hidden connections. The vault (Obsidian) stays the
interface for notes; this is a separate engine capability.

## 2. What we learned (validated on real people)

Every architectural decision below was tested live against OpenAlex/ORCID/Scholar
for Hamann, Blumenkamp, Prorok, Schäfer, Notomista. The load-bearing findings:

- **OpenAlex is reliable for the *accumulated* record** — the coauthorship network,
  topics, works, and the *historical* trail of published affiliations — and free.
- **OpenAlex is NOT reliable for the *leading edge*** — current institution, latest
  paper, and lab:
  - *Current affiliation:* Schäfer moved to Microsoft; OpenAlex still says TU Munich
    (he hasn't published from Microsoft yet). `last_known_institutions` was right for
    Prorok, garbage for Notomista ("Robotics Research (US)"), wrong for Schäfer.
  - *Latest paper:* placeholder `YYYY-01-01` dates, 6-month indexing lag, and
    `publication_date ≠ created_date` mean "latest" is approximate, never guaranteed.
  - *Lab / research group:* **no API has it.** OpenAlex only registers big institutes
    (`type=facility`, e.g. Max Planck); GRASP Lab, CMU Robotics Institute, the Prorok
    Lab, Hamann's swarm group all collapse into the parent university. ORCID gives
    department at best. Confirmed three ways.
- **`raw_affiliation_strings` (which the engine currently discards) do name groups** —
  but only the group a person is a *member* of (GRASP, EPFL DISAL, Edinburgh
  "Autonomous Agents Research Group"). A **PI writes their department, not their own
  lab's name** (Prorok → "Dept of CS, Cambridge").
- **The web fixes the leading edge.** A plain web search surfaces a person's Google
  Scholar profile with current affiliation + verified-email domain (Schäfer →
  "microsoft.com") + latest work + homepage — the exact facts OpenAlex misses.
- **OpenAlex → Scholar is not a deterministic link.** OpenAlex stores only ORCID (no
  Scholar id); ORCID lists a homepage sometimes, Scholar rarely. So the link is a
  **search-and-verify** step (deterministic only via Wikidata P1960 for notable
  people). **Accepted risk:** some people resolve to "unresolved."
- **Disambiguation is the #1 hazard** and it bit us live (three "Lukas Schäfer"s; auto-
  pick grabbed a materials scientist; OpenAlex itself mis-tagged topics across them).
- **Duplicate work records are real** (arXiv + repo mirror + Zenodo supplement) and
  **inflate coauthor counts** unless deduped first.
- **OpenAlex rate-limits** — we hit repeated 429s; the stored API key does *not* lift
  them. Any pipeline must throttle (≤10 req/s, backoff).

## 3. Architecture — three layers

| layer | source | gives | reliability |
| --- | --- | --- | --- |
| **network backbone** | OpenAlex | coauthored graph, topics, history | high, deterministic |
| **current snapshot** | web search → Scholar/homepage, *verified* | current affiliation, latest work, lab | good, needs verify |
| **extraction** | balthar/qwen (local) | structured facts from fetched web text | off the critical path |

**Principle:** balthar is a *text refiner over data we already fetched*, never a
retriever and never on the critical path. The structural graph (backbone) builds fully
without balthar or the web.

## 4. Person node schema (locked)

```
person
  # identity
  openalex_id        # node key (e.g. A5081322765)
  name               # display_name
  aliases            # display_name_alternatives + raw_author_names (for dedup)
  orcid              # when present (the only external id OpenAlex reliably gives)
  # prominence (lifetime, cheap seniority signal — h=3 student vs h=17 PI)
  works_count
  cited_by_count
  h_index
  # 5-year history (derived from window works, NOT lifetime author fields)
  window_work_ids    # last-5y papers, deduped; full records live in the cache
  topics             # aggregated from window works (sharper than lifetime topics)
  affiliations       # institution(s) seen in the window (historical/published)
  # coauthors are edges, not a field (see §6)
  # current snapshot (web, verified — may be unresolved)
  current_affiliation   {value, source_url, confidence}
  scholar_url           {value, source_url} | unresolved
  homepage
  current_lab           {value, source_url, confidence, inferred|verified} | unresolved
  # provenance
  status = "network"
  source, fetched_at, stub?     # stub = fetched as a coauthor, not yet expanded
```

Heavy detail (per-year counts, embeddings, raw affiliation strings) stays in the
SQLite cache `meta` blob; the ArcadeDB vertex stays small and queryable.

## 5. Node scope (boundary)

Seed people (from the vault / chosen) **and their direct coauthors** become full
nodes. Everyone past that stays a **stub** (id + name) until explicitly expanded.
Fetching full profiles for every 2-hop coauthor explodes (220 coauthors for Hamann
alone); expansion is on demand.

## 6. Edges — exactly two reasons

Two people are related iff they **share a paper** or are **in the same group**; nothing
else (same-institution-alone and same-topic-alone are deliberately NOT edges — they
hairball). Edge *type* encodes the *reason*, so the graph is legible.

- **`coauthored`** — share ≥1 deduped paper. Store facts (`work_ids`, `n_shared`,
  `last_year`) as attributes. **No weight in v1** — the Newman×recency formula is
  deferred; the raw facts are kept so it is computable later with no re-fetch.
- **`same_group`** — same lab. Two provenances, both marked:
  - *inferred:* Louvain community over the `coauthored` graph — **reuses the existing
    `discovery/core.py:clusters()` (seed=42, deterministic)**. A hypothesis, labeled as
    such (never presented as "affiliated to X").
  - *verified:* extracted from a fetched Scholar/homepage/affiliation-string, with a
    `source_url`. This is the only "factual lab" path.

## 7. Build pipeline

**Phase 1 — Ingest + clean (the real work).** The cleaning ORDER is non-negotiable
(computing coauthor facts on duplicate records is permanently wrong):

1. **Normalize strings** — HTML-unescape, NFKC-fold, collapse whitespace, casefold for
   match-keys, keep a display copy; `doi_norm`.
2. **Dedup works** into canonical clusters — DOI when present, else
   (norm_title, first-author surname, year±1). *The critical guard.*
3. **Resolve authors** — hard-merge on shared ORCID; else name-key + corroboration
   (shared coauthor / affiliation / topic) to dodge the "Y. Wang" trap. **WARN on
   suspected over-merges; never auto-split.**
4. **Canonicalize affiliations** to institution ids; raw strings are display-only.
5. **Write person nodes.**

**Phase 2 — Connect.** Draw `coauthored` edges over deduped papers; derive
`same_group` from `clusters()`.

**Phase 3 — Web enrichment (optional, targeted, deferred — see §9).** For chosen
people: web-search → Scholar/homepage → balthar extract → verify against the OpenAlex
fingerprint (coauthor overlap / ORCID) → store current-snapshot fields with provenance,
or mark `unresolved`.

## 8. Persistence & reuse

- Nodes/edges tagged `status:"network"`. **Amend `app.py` (`clear()` at line ~51)** so a
  vault sync does not wipe the people-graph — the blanket `DELETE FROM Entity` must
  spare `status:"network"`. Mandatory.
- Weights/window are relative to "now" → recompute on refresh; keep **stable canonical
  ids** for idempotency. Nodes persist; derived weights recompute (reconciles
  "persistent graph" with "rebuildable").
- **Reused for free:** once people + `coauthored` edges exist, `discovery/core.py`
  (`clusters`, `bridges`, `find_path`, `around`) — already wired into the CLI and TUI —
  lights up on the people-graph with no new code.
- **Rate limiting:** add a polite throttle (≤10 req/s + backoff) to the OpenAlex client;
  it currently has none.

## 9. v1 scope vs deferred

**v1 (this implementation plan) — the free, deterministic graph:**
person nodes (identity + prominence + 5y history) · the Phase-1 cleaning pipeline ·
`coauthored` edges (facts, no weight) · `same_group` via `clusters()` · persistence
guard · rate limiting · `raw_affiliation_strings` **captured** (stop discarding them).
*Optional within v1, off the critical path:* balthar extracts a member-lab name from
those strings where one is present (e.g. "GRASP Laboratory") — the graph builds fine
without it.

**Deferred (data kept so each is cheap later):**
- edge **weights** (Newman × recency: `Σ 1/(n_p−1)·0.5^(age/3)`, T=50, H=3)
- extra edge types: `same_institution`, `same_topic`, `advised_by`
- **latent link prediction** (similar-but-never-coauthored, embeddings + Adamic-Adar)
- **autonomous web pipeline** — the Phase-3 current-snapshot layer. Documented stack:
  **Tavily** (1,000 credits/mo, renewing, ~$0) → **trafilatura** (local clean) →
  **balthar** extract (verbatim-span check, drop hallucinations) → provenance (member
  counts only if on a fetched page *and* in the OpenAlex coauthor set). **Claude
  web-search** = paid escalation (~$5–15/mo) for cases balthar can't disambiguate.
  **Wikidata P1960** = deterministic Scholar link when a Wikidata entry exists.
  Until it's automated, current-snapshot/PI-lab lookups are done interactively/targeted
  (per person you care about), not in bulk.

## 10. Risks (accepted)

- **OpenAlex→Scholar is not guaranteed** — search-and-verify with an explicit
  `unresolved` state. *Accepted.*
- **Current affiliation / latest paper / lab are web-only** and inherit web noise +
  self-reported staleness; every such fact carries a `source_url` and is never confused
  with an OpenAlex fact.
- **Disambiguation** — lock identity (ORCID / institution / coauthor overlap) before
  trusting any downstream fact; over-merges are WARNed, not auto-split.
- **Tuning-free** — deferred weights (T=50, H=3) have no ground truth; sanity-check by
  eye when enabled.
- **Free-tier durability** — keep search behind one interface so a vendor terms change
  is a config swap, not a rewrite.
