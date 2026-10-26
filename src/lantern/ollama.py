from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


class Ollama:
    def __init__(self, host: str, chat_model: str, embed_model: str):
        self.host = host.rstrip("/")
        self.chat_model = chat_model
        self.embed_model = embed_model
        self._health: dict | None = None
        self._health_at = 0.0

    def health(self, ttl: float = 5.0) -> dict:
        now = time.time()
        if self._health is not None and now - self._health_at < ttl:
            return self._health
        try:
            payload = self._request("GET", "/api/tags", None, timeout=0.8)
            names = [item.get("name", "") for item in payload.get("models", []) if isinstance(item, dict)]
            result = {"ok": True, "models": names}
        except Exception as exc:
            result = {"ok": False, "models": [], "error": exc.__class__.__name__}
        self._health = result
        self._health_at = now
        return result

    def embed(self, texts: list[str]) -> tuple[list[list[float]] | None, str]:
        if not texts:
            return [], ""
        try:
            payload = self._request(
                "POST",
                "/api/embed",
                {"model": self.embed_model, "input": texts},
                timeout=90,
            )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:240]
            code = "embed-model-missing" if exc.code == 404 or "not found" in detail.lower() else "embed-failed"
            return None, code
        except Exception:
            return None, "ollama-offline"
        vectors = payload.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            return None, "embed-model-missing"
        return vectors, ""

    def chat(self, system: str, user: str) -> tuple[str | None, str]:
        try:
            payload = self._request(
                "POST",
                "/api/chat",
                {
                    "model": self.chat_model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "options": {"temperature": 0.1},
                },
                timeout=180,
            )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:240]
            code = "chat-model-missing" if exc.code == 404 or "not found" in detail.lower() else "chat-failed"
            return None, code
        except Exception:
            return None, "ollama-offline"
        message = payload.get("message") or {}
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            return None, "chat-empty"
        return content.strip(), ""

    def _request(self, method: str, path: str, body: dict | None, timeout: float) -> dict:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self.host + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError:
            raise
        if not raw:
            return {}
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("unexpected ollama response")
        return parsed
