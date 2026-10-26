from pathlib import Path

from fastapi.testclient import TestClient

from lantern.server import create_app
from tests.test_textutil import EXAMPLES


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("LANTERN_OLLAMA_HOST", "http://127.0.0.1:9")
    app = create_app(tmp_path / "home")
    return TestClient(app)


def test_health_and_ask_round_trip(tmp_path: Path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    health = client.get("/api/health")
    assert health.status_code == 200
    body = health.json()
    assert body["documents"] == 0
    assert body["ollama"]["ok"] is False

    missing = client.post("/api/ingest", json={"path": str(tmp_path / "missing")})
    assert missing.status_code == 404

    invalid = client.post("/api/ingest", json={"path": str(EXAMPLES), "library": "../x"})
    assert invalid.status_code == 400

    ingested = client.post("/api/ingest", json={"path": str(EXAMPLES), "embed": False})
    assert ingested.status_code == 200
    assert ingested.json()["indexed"] == 3

    answer = client.post("/api/ask", json={"question": "默认端口是多少", "use_llm": True})
    assert answer.status_code == 200
    payload = answer.json()
    assert payload["mode"] == "extractive"
    assert "8787" in payload["answer"]
    assert payload["note"] == "ollama-offline"

    empty = client.post("/api/ask", json={"question": "   "})
    assert empty.status_code == 400

    documents = client.get("/api/documents")
    assert len(documents.json()["documents"]) == 3
    client.app.state.store.close()


def test_upload_and_delete(tmp_path: Path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    uploaded = client.post(
        "/api/upload",
        data={"library": "default"},
        files={"files": ("note.md", "# 上传\n\n上传标记是 ZOOMKEEP。\n".encode("utf-8"), "text/markdown")},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["indexed"] == 1
    answer = client.post("/api/ask", json={"question": "ZOOMKEEP", "use_llm": False})
    assert "ZOOMKEEP" in answer.json()["answer"]

    document_id = client.get("/api/documents").json()["documents"][0]["id"]
    deleted = client.delete(f"/api/documents/{document_id}")
    assert deleted.status_code == 200
    assert client.get("/api/documents").json()["documents"] == []
    client.app.state.store.close()
