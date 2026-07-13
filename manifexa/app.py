"""The application facade — one object that drives the whole loop.

Holds a single graph engine and keeps it in sync with the files: every write
(add / promote / edit / remove) rebuilds the derived graph, and reads query the
current engine. The engine is pluggable — NetworkX by default, Neo4j when
configured — and all access is serialised with a lock so the threaded web
server is safe. The OpenAlex client is injected so everything is testable.
"""
from __future__ import annotations

import threading
from pathlib import Path

from .discovery import core as discovery
from .discovery import semantic
from .graph.networkx_engine import NetworkXEngine
from .graph.sync import build_graph
from .promote import promote as _promote
from .sources.enrich import enrich_seed
from .store.cache import Cache
from .store.entity import Entity
from .store.slug import make_id
from .store.vault import Vault


def _node_fields(m: dict) -> list[list[str]]:
    """A person's full field list [[label, value], …] for the inspector — every
    cache-meta field worth auditing, in a stable, readable order."""
    out: list[list[str]] = []

    def add(label, val):
        if val in (None, "", [], {}):
            return
        out.append([label, val if isinstance(val, str) else str(val)])

    add("ORCID", m.get("orcid"))
    add("now", m.get("current_affiliation"))
    add("email", m.get("email_domain"))
    add("h-index", m.get("h_index"))
    add("works", m.get("works_count"))
    add("citations", m.get("cited_by_count"))
    add("papers (5y)", len(m.get("window_work_ids") or []) or None)
    if m.get("topics"):
        add("topics", ", ".join(m["topics"]))
    if m.get("affiliations"):
        add("affiliations (history)", " · ".join(m["affiliations"]))
    if m.get("aliases"):
        add("aliases", ", ".join(m["aliases"]))
    add("coauthors", len(m.get("coauthors") or []) or None)
    add("Scholar pubs", len(m.get("publications") or []) or None)
    add("Scholar", m.get("scholar_url"))
    add("OpenAlex", m.get("openalex"))
    add("source", m.get("source"))
    return out


def _year_window(today, years: int) -> tuple[int, str]:
    """(year, from_date) for the ``years``-year publication window ending at
    ``today``. The day is clamped to ≤28 so a leap day (Feb 29) never lands on a
    non-leap earlier year — the exact day of a publication-date floor is immaterial."""
    day = min(today.day, 28)
    return today.year, f"{today.year - years:04d}-{today.month:02d}-{day:02d}"


def _five_year_window(today) -> tuple[int, str]:
    return _year_window(today, 5)


class App:
    def __init__(self, home, client=None, engine=None, s2_client=None, crossref_client=None,
                 extractor=None, llm=None, clock=None, people_client=None, scholar_fetch=None) -> None:
        self.home = Path(home)
        self.home.mkdir(parents=True, exist_ok=True)
        self.vault = Vault(self.home / "vault")
        self.cache = Cache(self.home / "cache.db")
        self.client = client
        self.s2_client = s2_client
        self.crossref_client = crossref_client
        self.extractor = extractor
        self.llm = llm
        self._clock = clock                    # Eminexa: () -> (today_year, from_date)
        self._people_client = people_client    # Eminexa: injectable PeopleClient (tests)
        self._scholar_fetch = scholar_fetch    # Eminexa: injectable Scholar HTML fetcher (tests)
        self.engine = engine if engine is not None else NetworkXEngine()
        self._lock = threading.RLock()
        self.rebuild()

    def _ensure_client(self):
        if self.client is None:
            from .sources.openalex import OpenAlexClient, load_openalex_config

            # use the polite/authenticated pool (mailto + api_key) — far fewer 429s
            self.client = OpenAlexClient(**load_openalex_config())
        return self.client

    # --- graph lifecycle ---
    def rebuild(self):
        with self._lock:
            self.engine.clear()
            build_graph(self.vault, self.cache, self.engine)
        return self.engine

    def graph(self):
        return self.engine

    def reopen(self, home) -> None:
        """Switch this App to a different vault folder — close the current store,
        open (or create) the one at ``home``, and rebuild. Powers `vault <path>`."""
        with self._lock:
            for res in (self.engine, self.cache):
                try:
                    res.close()
                except Exception:
                    pass
            self.home = Path(home).expanduser()
            self.home.mkdir(parents=True, exist_ok=True)
            self.vault = Vault(self.home / "vault")
            self.cache = Cache(self.home / "cache.db")
            from .graph.factory import engine_from_env

            self.engine = engine_from_env(str(self.home))
            self.rebuild()

    # --- writes (each rebuilds the derived graph) ---
    def add(self, seed_id: str) -> dict:
        with self._lock:
            try:
                res = enrich_seed(self._ensure_client(), self.vault, self.cache, seed_id)
            except Exception:
                # Fallback: Crossref metadata-of-record (needs a DOI). No graph,
                # but the paper still lands in your vault.
                from .sources.crossref import CrossrefClient, crossref_work_to_entity

                client = self.crossref_client or CrossrefClient()
                entity = crossref_work_to_entity(client.get_work(seed_id))
                self.vault.write(entity)
                res = {"entity": entity.id, "nodes": 0, "edges": 0, "source": "crossref"}
            self.rebuild()
        return res

    # --- Eminexa: people network (people live in the cache, source="eminexa") ---
    def _people(self):
        if self._people_client is not None:
            return self._people_client
        from .eminexa.people import PeopleClient

        return PeopleClient(self._ensure_client())

    def _window_years(self) -> int:
        """The publication window in years (default 5), from this folder's config
        — set with the `window <n>` command."""
        from .tui import load_config

        try:
            n = int(load_config(self.home).get("window", 5))
        except (TypeError, ValueError):
            n = 5
        return n if 1 <= n <= 25 else 5

    def _window(self) -> tuple[int, str]:
        """(today_year, from_date) for the configured window. Injectable via
        `clock` so ingest is deterministic in tests."""
        if self._clock is not None:
            return self._clock()
        import datetime

        return _year_window(datetime.date.today(), self._window_years())

    def add_person(self, seed: str) -> dict:
        """Ingest a researcher (OpenAlex id / ORCID) + their coauthors into the
        people graph, then rebuild. Returns {person, coauthors, edges}."""
        from .eminexa.ingest import ingest_person

        with self._lock:
            year, from_date = self._window()
            res = ingest_person(self.cache, self._people(), seed, today_year=year,
                                from_date=from_date, fetch=self._scholar_fetch)
            self.rebuild()
        return res

    def person_view(self, author_id: str) -> dict | None:
        """A person's card data — their `meta` plus `title`/`key` for display.
        None if they're not in the people graph yet."""
        node = self.cache.get_node(author_id)
        if not node:
            return None
        return {**node["meta"], "title": node["title"], "key": node["key"]}

    def graph_data(self) -> dict:
        """The whole graph as ``{"nodes", "edges"}`` for the web view. Each node
        carries its ``role`` (seed / coauthor / curated), flat columns for the
        audit table (``aff``/``h``/``works``/``cites``/``ncoauth``/``topics``),
        and a full ``fields`` list [[label, value], …] for the inspector."""
        with self._lock:
            g = self.engine
            # community id per node (Louvain — the same_group inference) for color-by-cluster
            cluster_of: dict[str, int] = {}
            for i, c in enumerate(discovery.clusters(self.engine, min_size=2)):
                for mk in c["members"]:
                    cluster_of[mk] = i
            nodes = []
            for k in g.nodes():
                node = g.node(k) or {}
                cn = self.cache.get_node(k)
                m = (cn or {}).get("meta") or {}
                stub = bool(m.get("stub"))
                role = ("coauthor" if stub else "seed") if cn else (
                    "curated" if node.get("status") == "curated" else "node")
                aff = m.get("current_affiliation") or (m.get("affiliations") or [None])[0]
                nodes.append({
                    "key": k, "type": node.get("type"), "title": node.get("title") or k,
                    "status": node.get("status"), "role": role, "cluster": cluster_of.get(k, -1),
                    "aff": aff, "h": m.get("h_index"), "works": m.get("works_count"),
                    "cites": m.get("cited_by_count"), "ncoauth": len(m.get("coauthors") or []),
                    "topics": (m.get("topics") or [])[:6],
                    "pubs": (m.get("publications") or [])[:40],   # Scholar list, for the inspector
                    "fields": _node_fields(m) if not stub else [],
                })
            edges, seen = [], set()
            for k in g.nodes():
                for nbr, rel in g.neighbors_with_rel(k):
                    pair = tuple(sorted((k, nbr)))
                    if pair not in seen:
                        seen.add(pair)
                        edges.append({"src": pair[0], "dst": pair[1], "rel": rel})
            return {"nodes": nodes, "edges": edges}

    def export_html(self, path: str | None = None, title: str = "Eminexa · graph") -> str:
        """Render the whole graph to a self-contained interactive HTML web view —
        control panel, force-directed graph, per-node inspector, and audit table."""
        from .viz import graph_to_html

        html = graph_to_html(self.graph_data(), title=title)
        if path:
            Path(path).expanduser().write_text(html, encoding="utf-8")
        return html

    def promote(self, candidate_key: str, note: str = "") -> str:
        with self._lock:
            eid = _promote(self.vault, self.cache, candidate_key, note=note)
            self.rebuild()
        return eid

    def set_note(self, entity_id: str, body: str):
        with self._lock:
            entity = self.vault.read(entity_id)
            entity.body = body
            self.vault.write(entity)
            self.rebuild()
        return entity

    def remove(self, entity_id: str) -> None:
        with self._lock:
            self.vault.delete(entity_id)
            self.rebuild()

    # --- reads ---
    def around(self, entity_id: str, limit: int = 10) -> list[dict]:
        with self._lock:
            return discovery.around(self.engine, entity_id, limit=limit)

    def path(self, a: str, b: str):
        with self._lock:
            return discovery.find_path(self.engine, a, b)

    def bridges(self, limit: int = 5) -> list[dict]:
        with self._lock:
            return discovery.bridges(self.engine, limit=limit)

    def clusters(self, min_size: int = 2) -> list[dict]:
        with self._lock:
            return discovery.clusters(self.engine, min_size=min_size)

    def _openalex_alias(self) -> dict:
        alias = {}
        for e in self.vault.list():
            oa = e.meta.get("openalex")
            if oa:
                alias[oa] = e.id
        return alias

    def similar(self, entity_id: str, limit: int = 10) -> list[dict]:
        """Semantic neighbours by embedding — 'hidden literature'."""
        with self._lock:
            alias = self._openalex_alias()
            try:
                focal = self.vault.read(entity_id).meta.get("openalex") or entity_id
            except FileNotFoundError:
                focal = entity_id  # already a cache key (a candidate)
            out = []
            for r in semantic.similar(self.cache, focal, limit=limit):
                oa = r["key"]
                node = self.cache.get_node(oa)
                out.append({
                    "key": alias.get(oa, oa),
                    "title": node["title"] if node else oa,
                    "type": node["type"] if node else None,
                    "score": r["score"],
                })
            return out

    def embed(self) -> dict:
        """Fetch SPECTER2 embeddings (Semantic Scholar) for papers with a DOI —
        enables semantic similarity."""
        from .sources.semanticscholar import SemanticScholarClient, enrich_embeddings

        with self._lock:
            client = self.s2_client or SemanticScholarClient()
            return enrich_embeddings(client, self.vault, self.cache)

    def extract(self, text: str) -> dict:
        """Pull candidate entities + relationships out of pasted text (AI)."""
        from .sources.extract import AnthropicExtractor, extract_into_cache

        with self._lock:
            extractor = self.extractor or AnthropicExtractor()
            res = extract_into_cache(extractor, self.cache, text)
            self.rebuild()
        return res

    # --- LLM-powered graph ops (pluggable: Claude or a local model) ---
    def _provider(self):
        if self.llm is None:
            from .llm.provider import provider_from_env

            self.llm = provider_from_env()
        return self.llm

    def expand(self, key: str) -> dict:
        """LLM proposes new related entities + edges around ``key`` (candidates)."""
        from .llm import operations as ops

        with self._lock:
            res = ops.expand(self._provider(), self.engine, self.cache, key)
            self.rebuild()
        return res

    def complete(self, key: str) -> dict:
        """LLM infers likely missing edges among existing nodes (candidates)."""
        from .llm import operations as ops

        with self._lock:
            res = ops.complete(self._provider(), self.engine, self.cache, key)
            self.rebuild()
        return res

    def ask(self, query: str) -> list:
        """Natural-language search — the LLM ranks existing entities for the query."""
        from .llm import operations as ops

        with self._lock:
            return ops.ask(self._provider(), self.engine, query)

    def forget(self, source_prefix: str = "llm:") -> int:
        """Drop candidate nodes/edges from a source (default: all LLM proposals)
        and rebuild the graph. The vault (your curated truth) is untouched."""
        with self._lock:
            n = self.cache.delete_by_source(source_prefix)
            self.rebuild()
        return n

    def organize(self, key: str | None = None) -> dict:
        """LLM groups the graph (or one node's neighbourhood) into themes — a
        meaningful map. Returns summary + themes + leftover/untitled buckets."""
        from .llm import operations as ops

        with self._lock:
            keys = None
            if key:
                keys = [key] + [n for n, _ in self.engine.neighbors_with_rel(key)]
            return ops.organize(self._provider(), self.engine, keys)

    def export(self) -> dict:
        """The whole graph as plain JSON — for backup, sharing, or a static viewer."""
        with self._lock:
            g = self.engine
            nodes = [
                {"key": k, **{kk: vv for kk, vv in (g.node(k) or {}).items() if kk != "key"}}
                for k in g.nodes()
            ]
            edges, seen = [], set()
            for k in g.nodes():
                for nbr, rel in g.neighbors_with_rel(k):
                    pair = tuple(sorted((k, nbr)))
                    if pair not in seen:
                        seen.add(pair)
                        edges.append({"src": pair[0], "dst": pair[1], "rel": rel})
            return {"nodes": nodes, "edges": edges}

    def snapshot(self) -> dict:
        """The whole database (vault + cache) as one restorable JSON dict."""
        from .store.snapshot import dump

        with self._lock:
            return dump(self.vault, self.cache)

    def restore(self, data) -> dict:
        """Load a snapshot back into the vault + cache, then rebuild the graph."""
        from .store.snapshot import load

        with self._lock:
            stats = load(self.vault, self.cache, data)
            self.rebuild()
        return stats

    def create(self, type: str, title: str, body: str = "", **fields) -> str:
        """Create a curated entity by hand, validated against the type schema.
        Raises ``SchemaError`` on a hard violation (unknown type, missing
        required field, bad-typed value); missing recommended fields are allowed."""
        from .store import schema

        meta = {"type": type, "title": title, "status": "curated", **fields}
        entity = Entity(id=make_id(type, title), meta=meta, body=body)
        errs = schema.errors(schema.validate(entity))
        if errs:
            raise schema.SchemaError("; ".join(i.message for i in errs))
        with self._lock:
            self.vault.write(entity)
            self.rebuild()
        return entity.id

    def link(self, src: str, dst: str, rel: str = "related") -> tuple[str, str, str]:
        """Connect two entities with a curated edge, validated against the schema
        (the relation's target type must be allowed). Stored files-as-truth as a
        ``[[wikilink]]`` in ``src``'s frontmatter (so Obsidian shows it too), then
        materialised into the derived graph. Idempotent per target."""
        from .store import schema

        with self._lock:
            entity = self.vault.read(src)                       # src must be a curated file
            dst_type = (self.engine.node(dst) or {}).get("type") or (
                self.vault.read(dst).type if self.vault.exists(dst) else "")
            issue = schema.relation_ok(entity.type, rel, dst_type)
            if issue and issue.severity == "error":
                raise schema.SchemaError(issue.message)
            if not any(t == dst for _, t in entity.relations):
                links = [x for x in (entity.meta.get("links") or []) if isinstance(x, str)]
                links.append(f"{rel} :: [[{dst}]]")
                entity.meta["links"] = links
                self.vault.write(entity)
                self.rebuild()
            return (src, dst, rel)

    def link_many(self, src: str, targets, rel: str = "related") -> tuple[list, list]:
        """Link ``src`` to each of ``targets`` with a single write + rebuild.
        Best-effort: skips targets whose relation is invalid rather than aborting.
        Returns ``(linked, skipped)`` where skipped is ``[(dst, reason)]``."""
        from .store import schema

        with self._lock:
            entity = self.vault.read(src)
            already = {t for _, t in entity.relations}
            links = [x for x in (entity.meta.get("links") or []) if isinstance(x, str)]
            linked, skipped = [], []
            for dst in targets:
                if dst in already or dst in linked:
                    continue                                    # idempotent
                dst_type = (self.engine.node(dst) or {}).get("type") or (
                    self.vault.read(dst).type if self.vault.exists(dst) else "")
                issue = schema.relation_ok(entity.type, rel, dst_type)
                if issue and issue.severity == "error":
                    skipped.append((dst, issue.message))
                    continue
                links.append(f"{rel} :: [[{dst}]]")
                linked.append(dst)
            if linked:
                entity.meta["links"] = links
                self.vault.write(entity)
                self.rebuild()
            return linked, skipped

    def inspect(self, entity_id: str):
        """The full structured record for a node — attributes + relations + notes
        + schema issues — assembled from its file and the graph (a NodeView)."""
        from .store.node import build_view

        with self._lock:
            try:
                entity = self.vault.read(entity_id)
            except (FileNotFoundError, OSError):
                node = self.engine.node(entity_id)
                if not node:
                    raise
                entity = Entity(id=entity_id, meta={"type": node.get("type", ""),
                                                    "title": node.get("title", ""),
                                                    "status": node.get("status", "candidate")})
            return build_view(entity, self.engine)

    def source_search(self, query: str, limit: int = 8) -> list[dict]:
        """Search OpenAlex for papers to add (search-to-add)."""
        from .sources.openalex import normalize_openalex_id

        out = []
        for w in self._ensure_client().search_works(query, per_page=limit):
            out.append({
                "key": normalize_openalex_id(w["id"]),
                "title": w.get("title") or w.get("display_name") or "",
                "year": w.get("publication_year"),
                "type": "paper",
            })
        return out

    def open(self, entity_id: str):
        return self.vault.read(entity_id)

    def list(self) -> list:
        return self.vault.list()
