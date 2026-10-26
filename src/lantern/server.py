from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from lantern import __version__
from lantern.answer import ask, display_path
from lantern.config import Settings
from lantern.ingest import ingest_path
from lantern.ollama import Ollama, model_ready
from lantern.parsers import SUPPORTED_EXTENSIONS
from lantern.store import Store

LIBRARY_RE = re.compile(r"^[A-Za-z0-9_\-\u4e00-\u9fff]{1,40}$")
MAX_UPLOAD_BYTES = 20_000_000


class IngestRequest(BaseModel):
    path: str
    library: str | None = "default"
    embed: bool = True


class AskRequest(BaseModel):
    question: str
    library: str | None = "default"
    use_llm: bool = True
    limit: int = Field(default=6, ge=1, le=12)


def create_app(home: Path | None = None) -> FastAPI:
    settings = Settings.load(home)
    store = Store(settings.home)
    ollama = Ollama(settings.ollama_host, settings.chat_model, settings.embed_model)
    app = FastAPI(
        title="Lantern",
        version=__version__,
        description="Local-first knowledge base. Ask your own folders.",
    )
    app.state.settings = settings
    app.state.store = store
    app.state.ollama = ollama
    page = Path(__file__).resolve().parent / "web" / "index.html"

    @app.middleware("http")
    async def reject_cross_site(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse(status_code=403, content={"detail": "cross-site-request"})
            if request.headers.get("x-lantern-request") != "1":
                return JSONResponse(status_code=403, content={"detail": "cross-site-request"})
        return await call_next(request)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(page)

    @app.get("/api/health")
    def health() -> dict:
        counts = store.counts()
        ollama_health = ollama.health()
        models = ollama_health.get("models") or []
        reachable = bool(ollama_health.get("ok"))
        return {
            "version": __version__,
            "home": str(settings.home),
            "documents": counts["documents"],
            "chunks": counts["chunks"],
            "vectors": counts["vectors"],
            "ollama": {
                "ok": reachable,
                "chat_ready": reachable and model_ready(models, settings.chat_model),
                "embed_ready": reachable and model_ready(models, settings.embed_model),
                "chat_model": settings.chat_model,
                "embed_model": settings.embed_model,
                "models": models,
            },
        }

    @app.get("/api/documents")
    def documents() -> dict:
        rows = []
        for row in store.list_documents():
            rows.append(
                {
                    "id": row["id"],
                    "library": row["library"],
                    "path": row["path"],
                    "display_path": display_path(row["path"], settings.home),
                    "title": row["title"],
                    "bytes": row["bytes"],
                    "chunks": row["chunks"],
                    "updated_at": row["updated_at"],
                }
            )
        return {"documents": rows}

    @app.delete("/api/documents/{document_id}")
    def delete_document(document_id: int) -> dict:
        if not store.delete_document(document_id):
            raise HTTPException(status_code=404, detail="document-not-found")
        return {"deleted": document_id}

    @app.post("/api/ingest")
    def ingest(body: IngestRequest) -> dict:
        library = _library(body.library)
        if not body.path.strip():
            raise HTTPException(status_code=400, detail="path-required")
        try:
            report = ingest_path(store, Path(body.path), library, ollama, embed=body.embed)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="path-not-found") from None
        except OSError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return report.as_dict()

    @app.post("/api/examples")
    def ingest_examples() -> dict:
        examples = Path.cwd() / "examples"
        if not examples.is_dir():
            raise HTTPException(status_code=404, detail="examples-not-found")
        report = ingest_path(store, examples, "default", ollama, embed=True)
        return report.as_dict()

    @app.post("/api/upload")
    async def upload(
        library: str = Form("default"),
        files: list[UploadFile] = File(...),
    ) -> dict:
        library_name = _library(library)
        destination = settings.home / "uploads" / library_name
        destination.mkdir(parents=True, exist_ok=True)
        saved: list[Path] = []
        for upload_file in files:
            name = Path(upload_file.filename or "file").name
            if not name or name in {".", ".."}:
                continue
            target = _unique_target(destination, name)
            data = await _read_limited(upload_file, MAX_UPLOAD_BYTES)
            target.write_bytes(data)
            saved.append(target)
        if not saved:
            raise HTTPException(status_code=400, detail="no-files")
        indexed = 0
        updated = 0
        unchanged = 0
        skipped = 0
        errors: list[str] = []
        for path in saved:
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                skipped += 1
                errors.append(f"{path.name}: 不支持的类型")
                continue
            report = ingest_path(store, path, library_name, ollama=None, embed=False)
            indexed += report.indexed
            updated += report.updated
            unchanged += report.unchanged
            skipped += report.skipped
            errors.extend(report.errors)
        embedded, embed_note = (0, "")
        if indexed or updated:
            from lantern.ingest import embed_pending

            embedded, embed_note = embed_pending(store, ollama)
        return {
            "library": library_name,
            "indexed": indexed,
            "updated": updated,
            "unchanged": unchanged,
            "skipped": skipped,
            "embedded": embedded,
            "embed_note": embed_note,
            "errors": errors,
        }

    @app.post("/api/ask")
    def ask_question(body: AskRequest) -> dict:
        library_name = None if body.library in (None, "", "*") else _library(body.library)
        try:
            return ask(
                store,
                body.question,
                library_name,
                ollama,
                limit=body.limit,
                use_llm=body.use_llm,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


async def _read_limited(upload_file: UploadFile, limit: int) -> bytes:
    blocks: list[bytes] = []
    total = 0
    while True:
        block = await upload_file.read(1024 * 1024)
        if not block:
            break
        total += len(block)
        if total > limit:
            name = Path(upload_file.filename or "file").name
            raise HTTPException(status_code=400, detail=f"{name} is larger than 20MB")
        blocks.append(block)
    return b"".join(blocks)


def _library(value: object) -> str:
    if value is None or value == "":
        return "default"
    if not isinstance(value, str) or not LIBRARY_RE.fullmatch(value):
        raise HTTPException(status_code=400, detail="invalid-library")
    return value


def _unique_target(directory: Path, name: str) -> Path:
    target = directory / name
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    for number in range(2, 1000):
        candidate = directory / f"{stem}-{number}{suffix}"
        if not candidate.exists():
            return candidate
    raise HTTPException(status_code=400, detail="could not name the upload")
