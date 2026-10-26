from __future__ import annotations

import re
from dataclasses import dataclass

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")


@dataclass(frozen=True)
class Piece:
    heading: str
    text: str
    line_start: int


def chunk_document(
    text: str,
    size: int = 900,
    overlap: int = 140,
    *,
    headings: bool = True,
) -> list[Piece]:
    if overlap >= size:
        overlap = size // 5
    pieces: list[Piece] = []
    for heading, lines, heading_line in _sections(text, headings):
        packed = _pack(_paragraphs(lines), size, overlap)
        for index, (line_no, part) in enumerate(packed):
            if index == 0 and heading:
                line_no = heading_line or line_no
            pieces.append(Piece(heading=heading, text=part, line_start=line_no))
    if not pieces and text.strip():
        line = next((number for number, row in enumerate(text.splitlines(), 1) if row.strip()), 1)
        return [Piece("", text.strip(), line)]
    return pieces


def _sections(text: str, headings: bool) -> list[tuple[str, list[tuple[int, str]], int]]:
    sections: list[tuple[str, list[tuple[int, str]], int]] = []
    heading = ""
    heading_line = 0
    buf: list[tuple[int, str]] = []
    in_fence = False

    def flush() -> None:
        nonlocal buf
        if any(line.strip() for _, line in buf):
            sections.append((heading, buf, heading_line))
        buf = []

    for line_no, line in enumerate(text.splitlines(), 1):
        if headings and FENCE_RE.match(line):
            in_fence = not in_fence
            buf.append((line_no, line))
            continue
        match = HEADING_RE.match(line) if headings and not in_fence else None
        if match:
            flush()
            heading = match.group(2).strip()
            heading_line = line_no
            continue
        buf.append((line_no, line))
    flush()
    return sections


def _paragraphs(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    paragraphs: list[tuple[int, str]] = []
    buf: list[str] = []
    start = 0

    def flush() -> None:
        nonlocal buf, start
        if buf:
            body = "\n".join(buf).strip()
            if body:
                paragraphs.append((start, body))
        buf = []
        start = 0

    for line_no, line in lines:
        if not line.strip():
            flush()
            continue
        if not buf:
            start = line_no
        buf.append(line)
    flush()
    return paragraphs


def _pack(paragraphs: list[tuple[int, str]], size: int, overlap: int) -> list[tuple[int, str]]:
    if not paragraphs:
        return []
    chunks: list[tuple[int, str]] = []
    current = ""
    current_line = 0
    for line_no, paragraph in paragraphs:
        if len(paragraph) > size:
            if current:
                chunks.append((current_line, current))
                current = ""
            for piece in _hard_wrap(paragraph, size, overlap):
                chunks.append((line_no, piece))
            continue
        if not current:
            current = paragraph
            current_line = line_no
            continue
        if len(current) + 2 + len(paragraph) <= size:
            current = current + "\n\n" + paragraph
            continue
        chunks.append((current_line, current))
        tail = current[-overlap:].strip() if overlap else ""
        candidate = (tail + "\n\n" + paragraph).strip() if tail else paragraph
        current = candidate if len(candidate) <= size else paragraph
        current_line = line_no
    if current:
        chunks.append((current_line, current))
    return [(line_no, chunk) for line_no, chunk in chunks if chunk.strip()]


def _hard_wrap(text: str, size: int, overlap: int) -> list[str]:
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= len(text):
            break
        next_start = end - overlap
        if next_start <= start:
            next_start = end
        start = next_start
    return pieces
