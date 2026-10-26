from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from lantern.chunk import chunk_document
from lantern.ollama import Ollama
from lantern.parsers import SUPPORTED_EXTENSIONS, ParseError, read_document
from lantern.store import Store, file_sha256

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".lantern",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".idea",
    ".pytest_cache",
    ".mypy_cache",
    "site-packages",
}
EMBED_BATCH = 8


@dataclass
class IngestReport:
    library: str
    indexed: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    embedded: int = 0
    embed_note: str = ""
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "library": self.library,
            "indexed": self.indexed,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "skipped": self.skipped,
            "embedded": self.embedded,
            "embed_note": self.embed_note,
            "errors": self.errors,
        }


def ingest_path(
    store: Store,
    root: Path,
    library: str,
    ollama: Ollama | None = None,
    *,
    embed: bool = True,
) -> IngestReport:
    root = root.expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(str(root))
    if not root.is_file() and not root.is_dir():
        raise FileNotFoundError(str(root))
    report = IngestReport(library=library)
    for path in _iter_files(root):
        _ingest_file(store, path, library, report)
    if embed and ollama is not None and (report.indexed or report.updated or store.counts()["chunks"]):
        embedded, note = embed_pending(store, ollama)
        report.embedded = embedded
        report.embed_note = note
    return report


def _ingest_file(store: Store, path: Path, library: str, report: IngestReport) -> None:
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        report.skipped += 1
        return
    try:
        parsed = read_document(path)
        pieces = chunk_document(parsed.text, headings=parsed.headings)
        if not pieces:
            report.skipped += 1
            return
        state = store.write_document(
            library=library,
            path=str(path.resolve()),
            title=parsed.title,
            sha256=file_sha256(path),
            nbytes=path.stat().st_size,
            pieces=pieces,
        )
    except ParseError as exc:
        report.skipped += 1
        report.errors.append(f"{path.name}: {exc}")
        return
    except OSError as exc:
        report.skipped += 1
        report.errors.append(f"{path.name}: {exc}")
        return
    if state == "indexed":
        report.indexed += 1
    elif state == "updated":
        report.updated += 1
    else:
        report.unchanged += 1


def embed_pending(store: Store, ollama: Ollama) -> tuple[int, str]:
    if not ollama.health().get("ok"):
        return 0, "ollama-offline"
    done = 0
    while done < 2000:
        batch = store.chunks_without_embeddings(ollama.embed_model, EMBED_BATCH)
        if not batch:
            return done, ""
        vectors, note = ollama.embed([text for _, text in batch])
        if vectors is None or len(vectors) != len(batch):
            return done, note or "embed-model-missing"
        store.save_embeddings(ollama.embed_model, [(chunk_id, vector) for (chunk_id, _), vector in zip(batch, vectors)])
        done += len(batch)
    if store.chunks_without_embeddings(ollama.embed_model, 1):
        return done, "embed-incomplete"
    return done, ""


def _iter_files(root: Path):
    if root.is_file():
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
        for filename in filenames:
            if filename.startswith("."):
                continue
            path = Path(dirpath) / filename
            if path.is_file():
                yield path
