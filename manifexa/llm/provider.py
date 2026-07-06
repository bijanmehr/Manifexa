"""Pluggable LLM provider — Claude or a local model, one interface.

Every LLM-powered operation (expand / complete / ask) is written once against
``generate(prompt, system, schema)``; the provider is picked by ``MANIFEXA_LLM``
(``claude`` | ``ollama``). With a ``schema`` the provider returns parsed JSON
(structured output); without one it returns text. No new dependencies — Claude
uses the Anthropic SDK you already have, local uses Ollama over stdlib HTTP.
"""
from __future__ import annotations

import json
import os


class AnthropicProvider:
    """Claude via the Anthropic Messages API (structured output when a schema is given)."""

    name = "claude"

    def __init__(self, model: str = "claude-opus-4-8", client=None) -> None:
        self.model = model
        self._client = client

    def _ensure(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def generate(self, prompt: str, system: str | None = None, schema: dict | None = None):
        kw = {"model": self.model, "max_tokens": 4000,
              "messages": [{"role": "user", "content": prompt}]}
        if system:
            kw["system"] = system
        if schema:
            kw["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
        resp = self._ensure().messages.create(**kw)
        text = next(b.text for b in resp.content if b.type == "text")
        return json.loads(text) if schema else text


class OllamaProvider:
    """A local model via Ollama's HTTP API (``format`` carries the JSON schema)."""

    name = "local"

    def __init__(self, model: str | None = None, host: str | None = None) -> None:
        self.model = model or os.environ.get("MANIFEXA_LLM_MODEL", "llama3.1")
        self.host = (host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")

    def generate(self, prompt: str, system: str | None = None, schema: dict | None = None):
        import urllib.request

        body = {"model": self.model, "prompt": prompt, "stream": False}
        if system:
            body["system"] = system
        if schema:
            body["format"] = schema            # Ollama constrains output to this JSON schema
        req = urllib.request.Request(
            self.host + "/api/generate",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=180) as r:
            out = json.loads(r.read().decode("utf-8"))["response"]
        return json.loads(out) if schema else out


def provider_from_env():
    choice = os.environ.get("MANIFEXA_LLM", "claude").lower()
    if choice in ("ollama", "local"):
        return OllamaProvider()
    return AnthropicProvider()
