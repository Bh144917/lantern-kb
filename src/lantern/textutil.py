from __future__ import annotations

import re

# Longer phrases first. These are question glue, not search terms.
QUESTION_PHRASES = (
    "可不可以",
    "能不能",
    "是不是",
    "有没有",
    "为什么",
    "什么",
    "怎么",
    "如何",
    "哪些",
    "哪个",
    "哪种",
    "多少",
    "为何",
    "是否",
    "请问",
    "一下",
)

STOP_CHARS = set("的了吗呢啊吧与及在被把将而又并也都很最这那你我它叫是")
LATIN_RE = re.compile(r"[A-Za-z0-9_]{2,}")
CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
SENTENCE_RE = re.compile(r"[^。！？!?\n]+[。！？!?]?")
FTS_UNSAFE = re.compile(r"[\"*^():]")


def keywords(query: str, limit: int = 12) -> list[str]:
    """Pull the terms that should actually hit a document.

    Chinese questions are not split by a dictionary. Glue words are removed,
    then long phrases also contribute 3- and 4-character windows so a query
    still matches when the source sentence uses a shorter form.
    """
    text = query.strip()
    for phrase in QUESTION_PHRASES:
        text = text.replace(phrase, " ")

    found: list[str] = []
    seen: set[str] = set()

    def add(token: str) -> None:
        token = token.strip()
        if len(token) < 2:
            return
        key = token.casefold()
        if key in seen:
            return
        seen.add(key)
        found.append(token)

    for match in LATIN_RE.finditer(text):
        add(match.group(0))

    for match in CJK_RUN_RE.finditer(text):
        parts = _split_cjk(match.group(0))
        for part in parts:
            for piece in _cjk_pieces(part):
                add(piece)

    found.sort(key=len, reverse=True)
    return found[:limit]


def _split_cjk(run: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    for char in run:
        if char in STOP_CHARS:
            if buf:
                parts.append("".join(buf))
                buf = []
        else:
            buf.append(char)
    if buf:
        parts.append("".join(buf))
    return parts or ([run] if len(run) >= 2 else [])


def _cjk_pieces(part: str) -> list[str]:
    if len(part) <= 4:
        return [part]
    pieces = [part]
    for size in (4, 3):
        step = 2 if len(part) > 6 else 1
        for index in range(0, len(part) - size + 1, step):
            pieces.append(part[index : index + size])
    return pieces


def fts_query(tokens: list[str]) -> str | None:
    atoms: list[str] = []
    for token in tokens:
        cleaned = FTS_UNSAFE.sub("", token).strip()
        if len(cleaned) < 3:
            continue
        atoms.append('"' + cleaned + '"')
        if len(atoms) >= 8:
            break
    if not atoms:
        return None
    return " OR ".join(atoms)


def sentences(text: str) -> list[str]:
    parts = [part.strip() for part in SENTENCE_RE.findall(text)]
    parts = [part for part in parts if len(part) >= 6]
    if parts:
        return parts
    stripped = text.strip()
    return [stripped] if stripped else []


def coverage(text: str, tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    haystack = text.casefold()
    got = 0
    total = 0
    for token in tokens:
        folded = token.casefold()
        weight = len(folded)
        total += weight
        if _contains(haystack, folded):
            got += weight
    return got / total if total else 0.0


def _contains(haystack: str, token: str) -> bool:
    # Latin tokens must match a whole word. "is" is inside "English", but it is not a hit.
    if re.fullmatch(r"[a-z0-9_]+", token):
        return re.search(rf"(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])", haystack) is not None
    return token in haystack


def clip(text: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def looks_chinese(text: str) -> bool:
    cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    return cjk >= 2
