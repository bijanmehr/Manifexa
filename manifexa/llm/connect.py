"""LLM auto-connect — make the plain ``manifexa <vault>`` launch ready to talk to
a configured model (e.g. a remote Ollama box reached over an SSH tunnel).

Config precedence: explicit ``cfg`` (tests) › environment (``MANIFEXA_LLM`` /
``OLLAMA_HOST`` / ``MANIFEXA_LLM_MODEL``) › a machine-local file at
``~/.manifexa/llm.json`` (never committed — it may name a private host). A
``tunnel`` block ``{"ssh", "local_port", "remote_port"}`` is brought up on demand
(``ssh -fN -L``). If the endpoint still can't be reached we return an *offline*
provider whose every call raises a clear error — so LLM commands fail loudly
with a fixable message instead of a cryptic connection reset.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
from pathlib import Path

_CONFIG_PATH = Path.home() / ".manifexa" / "llm.json"


class _OfflineProvider:
    """Stands in when the configured model is unreachable — names the box and
    tells you how to fix it, on any call."""

    name = "offline"

    def __init__(self, who: str) -> None:
        self.who = who

    def generate(self, *args, **kwargs):
        raise RuntimeError(
            f"LLM offline — can't reach {self.who}. Bring up the tunnel "
            f"(./run-balthar.sh, or  ssh -fN -L 11435:localhost:11434 {self.who}) and retry.")


def _load_file() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _from_env(env) -> dict:
    out = {}
    if env.get("MANIFEXA_LLM"):
        out["provider"] = env["MANIFEXA_LLM"]
    if env.get("OLLAMA_HOST"):
        out["host"] = env["OLLAMA_HOST"]
    if env.get("MANIFEXA_LLM_MODEL"):
        out["model"] = env["MANIFEXA_LLM_MODEL"]
    return out


def _reachable(base_url: str, timeout: float = 3.0) -> bool:
    import urllib.request

    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/api/tags", timeout=timeout) as r:
            return getattr(r, "status", 200) == 200
    except Exception:
        return False


def _bring_up_tunnel(t: dict) -> None:
    ssh = t.get("ssh")
    local, remote = int(t.get("local_port", 11435)), int(t.get("remote_port", 11434))
    if not ssh:
        return
    try:                                              # already forwarded?
        with socket.create_connection(("127.0.0.1", local), timeout=1):
            return
    except OSError:
        pass
    try:                                              # BatchMode → fail fast instead of prompting
        subprocess.run(["ssh", "-fN", "-o", "ConnectTimeout=6", "-o", "BatchMode=yes",
                        "-L", f"{local}:localhost:{remote}", ssh], timeout=20, check=False)
    except Exception:
        pass


def ensure_llm(cfg: dict | None = None, reach=_reachable, bring_up=_bring_up_tunnel):
    """Resolve and health-check the configured LLM. Returns ``(provider, status)``
    — ``(None, "")`` when no LLM is configured, an :class:`OllamaProvider` /
    ``AnthropicProvider`` when reachable, or an offline provider + a fixable error
    message when the box is down."""
    conf = dict(cfg) if cfg is not None else {**_load_file(), **_from_env(os.environ)}
    provider = (conf.get("provider") or "").lower()
    if provider not in ("ollama", "local", "claude"):
        return None, ""
    if provider == "claude":
        from .provider import AnthropicProvider

        return AnthropicProvider(model=conf.get("model", "claude-opus-4-8")), "· LLM ready: claude"

    host = conf.get("host", "http://localhost:11434")
    model = conf.get("model", "llama3.1")
    tunnel = conf.get("tunnel")
    who = (tunnel or {}).get("ssh") or host
    if tunnel and not reach(host):
        bring_up(tunnel)
    if not reach(host):
        return _OfflineProvider(who), (
            f"⚠ LLM offline — can't reach {who} (is it up and the SSH tunnel established?). "
            f"LLM commands (ask · expand · complete · map ai) will error until it is.")
    from .provider import OllamaProvider

    return OllamaProvider(model=model, host=host), f"· LLM ready: {model} @ {who}"
