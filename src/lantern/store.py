from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from pathlib import Path

from lantern.chunk import Piece

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    library TEXT NOT NULL,
    path TEXT NOT NULL,
    title TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(library, path)
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL,
    library TEXT NOT NULL,
    path TEXT NOT NULL,
    title TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    heading TEXT NOT NULL,
    line_start INTEGER NOT NULL,
    text TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    library UNINDEXED,
    path,
    title,
    heading,
    text,
    tokenize = "trigram case_sensitive 0"
);

CREATE TABLE IF NOT EXISTS embeddings (
    chunk_id INTEGER PRIMARY KEY,
    model TEXT NOT NULL,
    dim INTEGER NOT NULL,
    vector BLOB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_library ON chunks(library);
"""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class Store:
    def __init__(self, home: Path):
        self.home = Path(home)
        self.home.mkdir(parents=True, exist_ok=True)
        self.db_path = self.home / "lantern.db"
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA busy_timeout = 5000")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def counts(self) -> dict[str, int]:
        with self._lock:
            documents = self.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            chunks = self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            vectors = self.conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        return {"documents": documents, "chunks": chunks, "vectors": vectors}

    def list_documents(self) -> list[sqlite3.Row]:
        with self._lock:
            return list(
                self.conn.execute(
                    """
                    SELECT d.id, d.library, d.path, d.title, d.bytes, d.updated_at,
                           (SELECT COUNT(*) FROM chunks c WHERE c.document_id = d.id) AS chunks
                    FROM documents d
                    ORDER BY d.updated_at DESC, d.path
                    """
                )
            )

    def write_document(
        self,
        *,
        library: str,
        path: str,
        title: str,
        sha256: str,
        nbytes: int,
        pieces: list[Piece],
    ) -> str:
        with self._lock:
            try:
                existing = self.conn.execute(
                    "SELECT id, sha256 FROM documents WHERE library = ? AND path = ?",
                    (library, path),
                ).fetchone()
                if existing and existing["sha256"] == sha256:
                    return "unchanged"
                if existing:
                    self._delete_document_locked(int(existing["id"]))
                    state = "updated"
                else:
                    state = "indexed"
                now = time.time()
                cursor = self.conn.execute(
                    """
                    INSERT INTO documents (library, path, title, sha256, bytes, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (library, path, title, sha256, nbytes, now),
                )
                document_id = int(cursor.lastrowid)
                for ordinal, piece in enumerate(pieces):
                    chunk_cursor = self.conn.execute(
                        """
                        INSERT INTO chunks (
                            document_id, library, path, title, ordinal, heading, line_start, text
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            document_id,
                            library,
                            path,
                            title,
                            ordinal,
                            piece.heading,
                            piece.line_start,
                            piece.text,
                        ),
                    )
                    chunk_id = int(chunk_cursor.lastrowid)
                    self.conn.execute(
                        """
                        INSERT INTO chunks_fts (rowid, library, path, title, heading, text)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (chunk_id, library, path, title, piece.heading, piece.text),
                    )
                self.conn.commit()
                return state
            except Exception:
                self.conn.rollback()
                raise

    def delete_document(self, document_id: int) -> bool:
        with self._lock:
            row = self.conn.execute("SELECT id FROM documents WHERE id = ?", (document_id,)).fetchone()
            if row is None:
                return False
            self._delete_document_locked(document_id)
            self.conn.commit()
            return True

    def _delete_document_locked(self, document_id: int) -> None:
        ids = [
            int(row[0])
            for row in self.conn.execute("SELECT id FROM chunks WHERE document_id = ?", (document_id,))
        ]
        for chunk_id in ids:
            self.conn.execute("DELETE FROM embeddings WHERE chunk_id = ?", (chunk_id,))
            self.conn.execute("DELETE FROM chunks_fts WHERE rowid = ?", (chunk_id,))
        self.conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
        self.conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))

    def search_fts(self, library: str | None, match: str, limit: int) -> list[int]:
        sql = """
            SELECT c.id AS id
            FROM chunks_fts
            JOIN chunks c ON c.id = chunks_fts.rowid
            WHERE chunks_fts MATCH ?
        """
        params: list[object] = [match]
        if library:
            sql += " AND c.library = ?"
            params.append(library)
        sql += " ORDER BY bm25(chunks_fts) LIMIT ?"
        params.append(limit)
        with self._lock:
            try:
                rows = self.conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError:
                return []
        return [int(row["id"]) for row in rows]

    def search_like(self, library: str | None, needle: str, limit: int) -> list[int]:
        escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        sql = """
            SELECT id FROM chunks
            WHERE (text LIKE ? ESCAPE '\\' OR heading LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\')
        """
        params: list[object] = [pattern, pattern, pattern]
        if library:
            sql += " AND library = ?"
            params.append(library)
        sql += """
            ORDER BY
                CASE WHEN title LIKE ? ESCAPE '\\' OR heading LIKE ? ESCAPE '\\' THEN 1 ELSE 0 END DESC,
                CASE
                    WHEN text GLOB '*[0-9]*' OR heading GLOB '*[0-9]*' OR title GLOB '*[0-9]*' THEN 1
                    ELSE 0
                END DESC,
                id DESC
            LIMIT ?
        """
        params.extend([pattern, pattern, limit])
        with self._lock:
            rows = self.conn.execute(sql, params).fetchall()
        return [int(row["id"]) for row in rows]

    def get_chunks(self, ids: list[int]) -> dict[int, sqlite3.Row]:
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        with self._lock:
            rows = self.conn.execute(
                f"SELECT * FROM chunks WHERE id IN ({placeholders})",
                ids,
            ).fetchall()
        return {int(row["id"]): row for row in rows}

    def chunks_without_embeddings(self, model: str, limit: int) -> list[tuple[int, str]]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT c.id, c.title, c.heading, c.text
                FROM chunks c
                LEFT JOIN embeddings e ON e.chunk_id = c.id AND e.model = ?
                WHERE e.chunk_id IS NULL
                ORDER BY c.id
                LIMIT ?
                """,
                (model, limit),
            ).fetchall()
        payloads = []
        for row in rows:
            body = "\n".join(part for part in (row["title"], row["heading"], row["text"]) if part)
            payloads.append((int(row["id"]), body[:1800]))
        return payloads

    def save_embeddings(self, model: str, pairs: list[tuple[int, list[float]]]) -> None:
        if not pairs:
            return
        import struct

        with self._lock:
            for chunk_id, vector in pairs:
                blob = struct.pack(f"<{len(vector)}f", *[float(value) for value in vector])
                self.conn.execute(
                    """
                    INSERT INTO embeddings (chunk_id, model, dim, vector)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(chunk_id) DO UPDATE SET
                        model = excluded.model,
                        dim = excluded.dim,
                        vector = excluded.vector
                    """,
                    (chunk_id, model, len(vector), blob),
                )
            self.conn.commit()

    def load_embeddings(self, model: str, library: str | None) -> list[tuple[int, list[float]]]:
        import struct

        sql = """
            SELECT e.chunk_id, e.vector
            FROM embeddings e
            JOIN chunks c ON c.id = e.chunk_id
            WHERE e.model = ?
        """
        params: list[object] = [model]
        if library:
            sql += " AND c.library = ?"
            params.append(library)
        with self._lock:
            rows = self.conn.execute(sql, params).fetchall()
        loaded: list[tuple[int, list[float]]] = []
        for row in rows:
            blob = row["vector"]
            count = len(blob) // 4
            vector = list(struct.unpack(f"<{count}f", blob))
            loaded.append((int(row["chunk_id"]), vector))
        return loaded
