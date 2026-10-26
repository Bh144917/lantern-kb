from __future__ import annotations

from dataclasses import dataclass

from lantern.ollama import Ollama
from lantern.store import Store
from lantern.textutil import coverage, fts_query, keywords


@dataclass(frozen=True)
class Hit:
    chunk_id: int
    library: str
    path: str
    title: str
    heading: str
    line_start: int
    text: str
    score: float


def retrieve(
    store: Store,
    question: str,
    library: str | None,
    ollama: Ollama | None = None,
    limit: int = 6,
) -> list[Hit]:
    tokens = keywords(question)
    if not tokens:
        compact = "".join(question.split())
        if len(compact) >= 2:
            tokens = [compact[:40]]
    if not tokens:
        return []

    fts_ids: list[int] = []
    match = fts_query(tokens)
    if match:
        fts_ids = store.search_fts(library, match, limit=40)

    probes = [token for token in tokens if len(token) < 3]
    if not fts_ids:
        probes = probes or tokens[:3]
    like_ids: list[int] = []
    seen_probes: set[str] = set()
    for probe in probes:
        key = probe.casefold()
        if key in seen_probes:
            continue
        seen_probes.add(key)
        like_ids.extend(store.search_like(library, probe, limit=20))

    vector_ids = _vector_ids(store, question, library, ollama) if ollama is not None else []
    fused = _rrf([_dedupe(fts_ids), _dedupe(like_ids), _dedupe(vector_ids)])
    if not fused:
        return []

    rows = store.get_chunks(list(fused))
    ranked: list[Hit] = []
    for chunk_id, fused_score in fused.items():
        row = rows.get(chunk_id)
        if row is None:
            continue
        text = str(row["text"])
        blob = "\n".join(part for part in (str(row["title"]), str(row["heading"]), text) if part)
        score = fused_score + coverage(blob, tokens)
        ranked.append(
            Hit(
                chunk_id=chunk_id,
                library=str(row["library"]),
                path=str(row["path"]),
                title=str(row["title"]),
                heading=str(row["heading"]),
                line_start=int(row["line_start"]),
                text=text,
                score=score,
            )
        )
    ranked.sort(key=lambda hit: hit.score, reverse=True)
    return ranked[:limit]


def _vector_ids(store: Store, question: str, library: str | None, ollama: Ollama) -> list[int]:
    if not ollama.health().get("ok"):
        return []
    loaded = store.load_embeddings(ollama.embed_model, library)
    if not loaded or len(loaded) > 4000:
        return []
    vectors, note = ollama.embed([question[:1800]])
    if not vectors or note:
        return []
    query_vector = vectors[0]
    scored: list[tuple[float, int]] = []
    for chunk_id, vector in loaded:
        if len(vector) != len(query_vector):
            continue
        scored.append((_cosine(query_vector, vector), chunk_id))
    scored.sort(reverse=True)
    return [chunk_id for score, chunk_id in scored[:30] if score > 0.2]


def _cosine(left: list[float], right: list[float]) -> float:
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right):
        dot += a * b
        left_norm += a * a
        right_norm += b * b
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / ((left_norm ** 0.5) * (right_norm ** 0.5))


def _rrf(rank_lists: list[list[int]], constant: int = 60) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranks in rank_lists:
        for index, chunk_id in enumerate(ranks):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (constant + index + 1)
    return scores


def _dedupe(ids: list[int]) -> list[int]:
    seen: set[int] = set()
    ordered: list[int] = []
    for chunk_id in ids:
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        ordered.append(chunk_id)
    return ordered
