from pathlib import Path

from fastapi.testclient import TestClient

from lantern.ollama import model_ready
from lantern.server import create_app
from tests.test_textutil import EXAMPLES


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("LANTERN_OLLAMA_HOST", "http://127.0.0.1:9")
    app = create_app(tmp_path / "home")
    return TestClient(app)


def _post(client: TestClient, url: str, **kwargs):
    headers = {"X-Lantern-Request": "1", **kwargs.pop("headers", {})}
    return client.post(url, headers=headers, **kwargs)


def _delete(client: TestClient, url: str):
    return client.delete(url, headers={"X-Lantern-Request": "1"})


def test_health_and_ask_round_trip(tmp_path: Path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    health = client.get("/api/health")
    assert health.status_code == 200
    body = health.json()
    assert body["documents"] == 0
    assert body["ollama"]["ok"] is False
    assert body["ollama"]["chat_ready"] is False

    missing = _post(client, "/api/ingest", json={"path": str(tmp_path / "missing")})
    assert missing.status_code == 404

    invalid = _post(client, "/api/ingest", json={"path": str(EXAMPLES), "library": "../x"})
    assert invalid.status_code == 400

    ingested = _post(client, "/api/ingest", json={"path": str(EXAMPLES), "embed": False})
    assert ingested.status_code == 200
    assert ingested.json()["indexed"] == 3

    answer = _post(client, "/api/ask", json={"question": "默认端口是多少", "use_llm": True})
    assert answer.status_code == 200
    payload = answer.json()
    assert payload["mode"] == "extractive"
    assert "8787" in payload["answer"]
    assert payload["note"] == "ollama-offline"

    empty = _post(client, "/api/ask", json={"question": "   "})
    assert empty.status_code == 400

    documents = client.get("/api/documents")
    assert len(documents.json()["documents"]) == 3
    client.app.state.store.close()


def test_model_ready_accepts_a_latest_tag():
    assert model_ready(["qwen2.5:7b"], "qwen2.5:7b")
    assert model_ready(["nomic-embed-text:latest"], "nomic-embed-text")
    assert model_ready(["llama3:8b"], "qwen2.5:7b") is False


def test_ask_searches_every_library_when_asked(tmp_path: Path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    note = tmp_path / "note.md"
    note.write_text("# 笔记\n\n另一库的标记是 OTHER-LIB。\n", encoding="utf-8")
    saved = _post(client, "/api/ingest", json={"path": str(note), "library": "notes", "embed": False})
    assert saved.status_code == 200
    missed = _post(client, "/api/ask", json={"question": "OTHER-LIB", "use_llm": False})
    assert missed.json()["citations"] == []
    found = _post(client, "/api/ask", json={"question": "OTHER-LIB", "library": "*", "use_llm": False})
    assert "OTHER-LIB" in found.json()["answer"]
    client.app.state.store.close()


def test_upload_and_delete(tmp_path: Path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    denied = client.post(
        "/api/upload",
        data={"library": "default"},
        files={"files": ("note.md", b"# nope\n", "text/markdown")},
    )
    assert denied.status_code == 403

    uploaded = _post(
        client,
        "/api/upload",
        data={"library": "default"},
        files={"files": ("note.md", "# 上传\n\n上传标记是 ZOOMKEEP。\n".encode("utf-8"), "text/markdown")},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["indexed"] == 1
    answer = _post(client, "/api/ask", json={"question": "ZOOMKEEP", "use_llm": False})
    assert "ZOOMKEEP" in answer.json()["answer"]

    rejected = _post(
        client,
        "/api/upload",
        data={"library": "default"},
        files={"files": ("sheet.docx", b"not-a-real-docx", "application/octet-stream")},
    )
    assert rejected.status_code == 200
    body = rejected.json()
    assert body["indexed"] == 0
    assert any("不支持的类型" in error for error in body["errors"])

    document_id = client.get("/api/documents").json()["documents"][0]["id"]
    deleted = _delete(client, f"/api/documents/{document_id}")
    assert deleted.status_code == 200
    assert client.get("/api/documents").json()["documents"] == []
    client.app.state.store.close()
