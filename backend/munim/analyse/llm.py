"""The local model that plans and writes. It only ever talks to a server on this machine."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from munim.ask.llm import LLMError

DEFAULT_BASE = "http://localhost:11434/v1"
DEFAULT_MODEL = "qwen2.5:14b"
_LOCAL = ("http://localhost", "http://127.0.0.1", "http://[::1]")


class AnalyseConfigError(ValueError):
    """Analyse is set to a server that is not on this machine. Amounts would leave it, so refuse."""


class LocalChat:
    local = True

    def __init__(self, base_url: str = DEFAULT_BASE, model: str = DEFAULT_MODEL, timeout: float = 300.0, opener=None):
        base_url = base_url.rstrip("/")
        if not base_url.startswith(_LOCAL):
            raise AnalyseConfigError(
                f"Analyse sends your amounts to its model, so it only talks to a server on this machine. "
                f"{base_url} is not local."
            )
        self.base_url = base_url
        self.name = model
        self.timeout = timeout  # a 14B model may need a while to load the first time
        self._open = opener or urllib.request.urlopen

    @classmethod
    def from_env(cls) -> LocalChat:
        return cls(
            os.environ.get("MUNIM_ANALYSE_BASE_URL") or DEFAULT_BASE,
            os.environ.get("MUNIM_ANALYSE_MODEL") or DEFAULT_MODEL,
        )

    def chat(self, system: str, user: str, *, as_json: bool = False, max_tokens: int = 700) -> str:
        body = {
            "model": self.name,
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if as_json:
            body["response_format"] = {"type": "json_object"}
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._open(request, timeout=self.timeout) as response:
                payload = json.loads(response.read())
            return payload["choices"][0]["message"]["content"] or ""
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            hint = f" Pull it with `ollama pull {self.name}`." if exc.code == 404 else ""
            raise LLMError(f"{self.name} answered HTTP {exc.code}: {detail}.{hint}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise LLMError(f"Could not reach Ollama at {self.base_url}. Start it with `ollama serve`.") from exc
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("Ollama sent an unexpected reply.") from exc

    def status(self) -> dict:
        """Is Ollama up, and is the model pulled? Uses Ollama's own /api/tags."""
        root = self.base_url.removesuffix("/v1")
        try:
            with self._open(urllib.request.Request(f"{root}/api/tags"), timeout=3) as response:
                names = {m.get("name") for m in json.loads(response.read()).get("models", [])}
        except Exception:  # noqa: BLE001 - any failure means "not reachable" here
            return {"reachable": False, "has_model": False}
        wanted = self.name if ":" in self.name else f"{self.name}:latest"
        return {"reachable": True, "has_model": wanted in names}
