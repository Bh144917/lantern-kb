from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    home: Path
    ollama_host: str
    chat_model: str
    embed_model: str

    @staticmethod
    def load(home: Path | None = None) -> Settings:
        if home is None:
            env_home = os.environ.get("LANTERN_HOME")
            home = Path(env_home) if env_home else Path.cwd() / ".lantern"
        return Settings(
            home=Path(home),
            ollama_host=os.environ.get("LANTERN_OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/"),
            chat_model=os.environ.get("LANTERN_CHAT_MODEL", "qwen2.5:7b"),
            embed_model=os.environ.get("LANTERN_EMBED_MODEL", "nomic-embed-text"),
        )
