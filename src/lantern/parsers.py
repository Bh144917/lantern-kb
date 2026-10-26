from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

TEXT_EXTENSIONS = {
    ".md",
    ".markdown",
    ".txt",
    ".rst",
    ".text",
    ".csv",
    ".tsv",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".log",
    ".xml",
    ".css",
    ".scss",
}
CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".vue",
    ".mjs",
    ".cjs",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cs",
    ".php",
    ".rb",
    ".swift",
    ".sql",
    ".sh",
    ".bash",
    ".ps1",
    ".lua",
    ".dart",
    ".scala",
}
HTML_EXTENSIONS = {".html", ".htm"}
PDF_EXTENSIONS = {".pdf"}
HEADING_EXTENSIONS = {".md", ".markdown", ".txt", ".text", ".rst"} | PDF_EXTENSIONS
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | CODE_EXTENSIONS | HTML_EXTENSIONS | PDF_EXTENSIONS
MAX_TEXT_BYTES = 2_000_000
MAX_PDF_BYTES = 20_000_000

_TITLE_RE = re.compile(r"^#\s+(.+?)\s*$", re.M)
_SCRIPT_RE = re.compile(r"(?is)<(script|style).*?>.*?</\1>")
_BREAK_RE = re.compile(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>")
_TAG_RE = re.compile(r"<[^>]+>")


class ParseError(Exception):
    pass


@dataclass(frozen=True)
class ParsedDocument:
    title: str
    text: str
    headings: bool = True


def read_document(path: Path) -> ParsedDocument:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ParseError(f"unsupported type {suffix or 'file'}")
    limit = MAX_PDF_BYTES if suffix in PDF_EXTENSIONS else MAX_TEXT_BYTES
    size = path.stat().st_size
    if size > limit:
        megabytes = limit // 1_000_000
        raise ParseError(f"超过 {megabytes}MB，已跳过")
    if suffix in PDF_EXTENSIONS:
        text = _read_pdf(path)
    else:
        raw = _read_text(path)
        text = _html_to_text(raw) if suffix in HTML_EXTENSIONS else raw
    if "\x00" in text:
        raise ParseError("看起来是二进制文件，已跳过")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        raise ParseError("没有可提取的文本")
    # Keep leading blank lines so citation numbers match the file.
    text = text.rstrip()
    headings = suffix in HEADING_EXTENSIONS
    return ParsedDocument(title=_title(path, text, headings), text=text, headings=headings)


def _title(path: Path, text: str, headings: bool) -> str:
    if headings:
        match = _TITLE_RE.search(text)
        if match:
            return match.group(1).strip()[:120]
    return path.stem[:120]


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _html_to_text(raw: str) -> str:
    cleaned = _SCRIPT_RE.sub(" ", raw)
    cleaned = _BREAK_RE.sub("\n", cleaned)
    cleaned = _TAG_RE.sub(" ", cleaned)
    return html.unescape(cleaned)


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ParseError("没有安装 pypdf") from exc
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise ParseError(f"无法打开 PDF（{exc}）") from exc
    pages: list[str] = []
    for index, page in enumerate(reader.pages, 1):
        try:
            extracted = page.extract_text() or ""
        except Exception:
            extracted = ""
        extracted = extracted.strip()
        if extracted:
            pages.append(f"## Page {index}\n\n{extracted}")
    return "\n\n".join(pages)
