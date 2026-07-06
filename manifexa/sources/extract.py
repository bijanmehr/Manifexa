"""AI extraction — turn pasted text into candidate entities + relationships.

Captures the private/informal knowledge no database has: paste an abstract,
notes, or an email and an LLM pulls out the people, papers, labs and the links
between them, as candidates you approve. The extractor is injected so the
parsing/storage logic is tested offline; the live call uses the Anthropic SDK.
"""
from __future__ import annotations

from ..store.slug import make_id

# JSON schema the model must return (structured output).
EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["person", "paper", "lab", "book", "note", "concept", "topic"]},
                    "title": {"type": "string"},
                },
                "required": ["type", "title"],
                "additionalProperties": False,
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "rel": {"type": "string"},
                },
                "required": ["source", "target", "rel"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["entities", "edges"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You extract a knowledge graph from research text. Identify people, papers, "
    "labs, books, and concepts, and the relationships between them (authored, "
    "cites, member_of, advised, related, etc.). Return only entities actually "
    "mentioned. Edge source/target must exactly match an entity title."
)


def extract_into_cache(extractor, cache, text: str) -> dict:
    """Run the extractor over ``text`` and store the result as candidates."""
    result = extractor.extract(text)
    key_of: dict[str, str] = {}
    for e in result.get("entities", []):
        key = make_id(e["type"], e["title"])
        key_of[e["title"]] = key
        cache.upsert_node(key, e["type"], e["title"], {"source": "extracted"}, source="extracted")

    stored_edges = 0
    for ed in result.get("edges", []):
        src = key_of.get(ed.get("source"))
        dst = key_of.get(ed.get("target"))
        if src and dst:
            cache.upsert_edge(src, dst, ed.get("rel", "related"), source="extracted")
            stored_edges += 1

    return {"entities": len(key_of), "edges": stored_edges}


class AnthropicExtractor:
    """Live extractor using the Anthropic Messages API with structured output."""

    def __init__(self, model: str = "claude-opus-4-8", client=None) -> None:
        self.model = model
        self._client = client

    def _ensure(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def extract(self, text: str) -> dict:
        import json

        response = self._ensure().messages.create(
            model=self.model,
            max_tokens=4000,
            system=_SYSTEM,
            messages=[{"role": "user", "content": f"Extract the knowledge graph from:\n\n{text}"}],
            output_config={"format": {"type": "json_schema", "schema": EXTRACTION_SCHEMA}},
        )
        payload = next(b.text for b in response.content if b.type == "text")
        return json.loads(payload)
