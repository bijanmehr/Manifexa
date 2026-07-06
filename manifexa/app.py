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


class App:
    def __init__(self, home, client=None, engine=None, s2_client=None, crossref_client=None, extractor=None, llm=None) -> None:
        self.home = Path(home)
        self.home.mkdir(parents=True, exist_ok=True)
        self.vault = Vault(self.home / "vault")
        self.cache = Cache(self.home / "cache.db")
        self.client = client
        self.s2_client = s2_client
        self.crossref_client = crossref_client
        self.extractor = extractor
        self.llm = llm
        self.engine = engine if engine is not None else NetworkXEngine()
        self._lock = threading.RLock()
        self.rebuild()

    def _ensure_client(self):
        if self.client is None:
            from .sources.openalex import OpenAlexClient

            self.client = OpenAlexClient()
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
