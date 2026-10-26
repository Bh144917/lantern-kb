from __future__ import annotations

import re
from dataclasses import dataclass

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass(frozen=True)
class Piece:
    heading: str
    text: str
    line_start: int


def chunk_document(text: str, size: int = 900, overlap: int = 140) -> list[Piece]:
    if overlap >= size:
        overlap = size // 5
    pieces: list[Piece] = []
    for heading, body, line_start in _sections(text):
        for part in _pack(body, size, overlap):
            pieces.append(Piece(heading=heading, text=part, line_start=line_start))
    return pieces


def _sections(text: str) -> list[tuple[str, str, int]]:
    sections: list[tuple[str, list[str], int]] = []
    heading = ""
    buf: list[str] = []
    start = 1
    heading_marks_start = False
    for line_no, line in enumerate(text.splitlines(), 1):
        match = HEADING_RE.match(line)
        if match:
            if buf:
                sections.append((heading, buf, start))
                buf = []
            heading = match.group(2).strip()
            start = line_no
            heading_marks_start = True
            continue
        if not buf and not heading_marks_start:
            start = line_no
        buf.append(line)
    if buf:
        sections.append((heading, buf, start))

    rendered: list[tuple[str, str, int]] = []
    for section_heading, lines, line_start in sections:
        body = "\n".join(lines).strip()
        if body:
            rendered.append((section_heading, body, line_start))
    if not rendered and text.strip():
        return [("", text.strip(), 1)]
    return rendered


def _pack(text: str, size: int, overlap: int) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        return []
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > size:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_hard_wrap(paragraph, size, overlap))
            continue
        if not current:
            current = paragraph
            continue
        if len(current) + 2 + len(paragraph) <= size:
            current = current + "\n\n" + paragraph
            continue
        chunks.append(current)
        tail = current[-overlap:].strip() if overlap else ""
        candidate = (tail + "\n\n" + paragraph).strip() if tail else paragraph
        current = candidate if len(candidate) <= size else paragraph
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk.strip()]


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
