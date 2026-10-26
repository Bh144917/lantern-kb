from __future__ import annotations

from pathlib import Path

from lantern.ollama import Ollama
from lantern.retrieve import retrieve
from lantern.store import Store
from lantern.textutil import clip, coverage, keywords, looks_chinese, quantity_bonus, sentences

SYSTEM_ZH = (
    "你是 Lantern，只根据给定材料回答问题。"
    "材料没写到的内容，直接说不知道，不要补充材料以外的事实。"
    "回答使用问题的语言。引用材料时在句末标出编号，例如 [1]。"
)
SYSTEM_EN = (
    "You are Lantern. Answer only from the sources. "
    "If the sources do not contain the answer, say you don't know and do not add outside facts. "
    "Use the language of the question. Cite a source with its number, such as [1]."
)


def ask(
    store: Store,
    question: str,
    library: str | None = None,
    ollama: Ollama | None = None,
    *,
    limit: int = 6,
    use_llm: bool = True,
) -> dict:
    cleaned = question.strip()
    if not cleaned:
        raise ValueError("empty-question")
    if len(cleaned) > 2000:
        raise ValueError("question-too-long")
    limit = min(max(limit, 1), 12)
    hits = retrieve(store, cleaned, library, ollama if use_llm else None, limit=limit)
    citations = [_citation(index, hit, store.home) for index, hit in enumerate(hits, 1)]
    if not hits:
        return {
            "answer": "库里没有找到相关内容。" if looks_chinese(cleaned) else "Nothing in the library matches that.",
            "mode": "extractive",
            "model": None,
            "note": "no-hit",
            "citations": [],
        }

    note = ""
    mode = "extractive"
    model = None
    answer = _extractive(cleaned, hits)
    if use_llm and ollama is not None and ollama.health().get("ok"):
        generated, failure = ollama.chat(_system_prompt(cleaned), _user_prompt(cleaned, hits))
        if generated:
            answer = generated
            mode = "ollama"
            model = ollama.chat_model
        else:
            note = failure or "chat-failed"
    elif use_llm and ollama is not None:
        note = "ollama-offline"
    return {
        "answer": answer,
        "mode": mode,
        "model": model,
        "note": note,
        "citations": citations,
    }


def _extractive(question: str, hits: list) -> str:
    tokens = keywords(question)
    scored: list[tuple[float, int, str]] = []
    for index, hit in enumerate(hits, 1):
        blob_prefix = "\n".join(part for part in (hit.heading,) if part)
        source = f"{blob_prefix}\n{hit.text}" if blob_prefix else hit.text
        for sentence in sentences(source):
            score = coverage(sentence, tokens)
            if score <= 0:
                continue
            score += quantity_bonus(question, sentence)
            scored.append((score, index, sentence))
    if not scored:
        if looks_chinese(question):
            return "没有找到可以直接引用的句子。请看下面最接近的片段。"
        return "No sentence answers that directly. The closest passages are cited below."
    scored.sort(key=lambda item: (-item[0], item[1], len(item[2])))
    picked: list[str] = []
    seen: set[str] = set()
    for _score, index, sentence in scored:
        key = sentence.casefold()
        if key in seen:
            continue
        seen.add(key)
        picked.append(f"{sentence} [{index}]")
        if len(picked) >= 3:
            break
    return "\n".join(picked)


def _citation(index: int, hit, home: Path) -> dict:
    return {
        "n": index,
        "title": hit.title,
        "path": hit.path,
        "display_path": display_path(hit.path, home),
        "heading": hit.heading,
        "line_start": hit.line_start,
        "excerpt": clip(hit.text, 320),
        "score": round(hit.score, 4),
    }


def display_path(path: str, home: Path) -> str:
    resolved = Path(path).resolve()
    bases = [Path.cwd().resolve(), home.resolve()]
    for base in bases:
        try:
            return str(resolved.relative_to(base))
        except ValueError:
            continue
    return str(resolved)


def _system_prompt(question: str) -> str:
    return SYSTEM_ZH if looks_chinese(question) else SYSTEM_EN


def _user_prompt(question: str, hits: list) -> str:
    blocks = []
    for index, hit in enumerate(hits, 1):
        where = " · ".join(part for part in (hit.title, display_path(hit.path, Path.cwd()), hit.heading) if part)
        blocks.append(f"[{index}] {where}\n{hit.text[:1200]}")
    sources = "\n\n".join(blocks)
    if looks_chinese(question):
        return f"问题：{question}\n\n材料：\n{sources}"
    return f"Question: {question}\n\nSources:\n{sources}"
