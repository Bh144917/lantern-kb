from pathlib import Path

import pytest

from lantern.answer import ask
from lantern.ingest import ingest_path
from lantern.ollama import Ollama
from lantern.parsers import MAX_TEXT_BYTES
from lantern.store import Store
from tests.test_textutil import EXAMPLES


def _ollama() -> Ollama:
    return Ollama("http://127.0.0.1:9", "qwen2.5:7b", "nomic-embed-text")


@pytest.fixture
def store(tmp_path: Path):
    opened = Store(tmp_path / "home")
    yield opened
    opened.close()


def test_examples_answer_with_the_right_file(store: Store):
    report = ingest_path(store, EXAMPLES, "default", _ollama(), embed=False)
    assert report.indexed == 3
    assert report.errors == []

    port = ask(store, "默认端口是多少", "default", use_llm=False)
    assert port["mode"] == "extractive"
    assert "8787" in port["answer"]
    assert port["citations"][0]["path"].endswith("handbook.md")
    assert port["citations"][0]["heading"] == "服务"

    english = ask(store, "what is the default port", "default", use_llm=False)
    assert "8787" in english["answer"]
    assert english["citations"][0]["heading"] == "English"
    assert "\nEnglish [" not in english["answer"]

    model = ask(store, "嵌入模型默认叫什么", "default", use_llm=False)
    assert "nomic-embed-text" in model["answer"]
    assert model["citations"][0]["path"].endswith("ollama.md")

    skipped = ask(store, "索引时会跳过哪个目录", "default", use_llm=False)
    assert "node_modules" in skipped["answer"]
    assert skipped["citations"][0]["path"].endswith("sample.py")


def test_second_ingest_is_unchanged_until_the_file_changes(store: Store, tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    note = docs / "note.md"
    note.write_text("# 备忘\n\n会议室密码是 SILVER-19。\n", encoding="utf-8")
    first = ingest_path(store, docs, "default", embed=False)
    assert first.indexed == 1
    second = ingest_path(store, docs, "default", embed=False)
    assert second.unchanged == 1

    note.write_text("# 备忘\n\n会议室密码改成 COPPER-7。\n", encoding="utf-8")
    third = ingest_path(store, docs, "default", embed=False)
    assert third.updated == 1
    found = ask(store, "会议室密码", "default", use_llm=False)
    assert "COPPER-7" in found["answer"]
    assert "SILVER-19" not in found["answer"]


def test_node_modules_and_oversized_files_are_left_out(store: Store, tmp_path: Path):
    docs = tmp_path / "docs"
    hidden = docs / "node_modules"
    hidden.mkdir(parents=True)
    (hidden / "secret.md").write_text("密钥是 SECRETTOKEN。\n", encoding="utf-8")
    (docs / "keep.md").write_text("# 保留\n\n可见内容是 VISIBLE-1。\n", encoding="utf-8")
    (docs / "big.txt").write_text("A" * (MAX_TEXT_BYTES + 1), encoding="utf-8")
    report = ingest_path(store, docs, "default", embed=False)
    assert report.indexed == 1
    assert any("big.txt" in error for error in report.errors)
    found = ask(store, "SECRETTOKEN", "default", use_llm=False)
    assert found["citations"] == []
    visible = ask(store, "VISIBLE-1", "default", use_llm=False)
    assert "VISIBLE-1" in visible["answer"]


def test_html_script_is_not_indexed(store: Store, tmp_path: Path):
    page = tmp_path / "page.html"
    page.write_text(
        "<html><body><h1>采购</h1><p>供应商编码是 HARBOR-42。</p><script>alert(1)</script></body></html>",
        encoding="utf-8",
    )
    ingest_path(store, page, "default", embed=False)
    found = ask(store, "供应商编码", "default", use_llm=False)
    assert "HARBOR-42" in found["answer"]
    assert "alert" not in found["answer"]
    assert all("alert" not in citation["excerpt"] for citation in found["citations"])


def test_punctuation_in_the_question_does_not_crash(store: Store):
    ingest_path(store, EXAMPLES, "default", embed=False)
    found = ask(store, '端口?"', "default", use_llm=False)
    assert "8787" in found["answer"] or found["citations"]


def test_delete_document_removes_it_from_search(store: Store, tmp_path: Path):
    note = tmp_path / "only.md"
    note.write_text("# 唯一\n\n删除标记是 GONE-55。\n", encoding="utf-8")
    ingest_path(store, note, "default", embed=False)
    document_id = store.list_documents()[0]["id"]
    assert store.delete_document(document_id) is True
    assert store.delete_document(document_id) is False
    found = ask(store, "GONE-55", "default", use_llm=False)
    assert found["citations"] == []


def test_fts_index_finds_the_port_phrase(store: Store):
    ingest_path(store, EXAMPLES, "default", embed=False)
    assert store.search_fts("default", '"默认端口"', limit=5)


def test_natural_questions_still_find_the_example_answers(store: Store):
    ingest_path(store, EXAMPLES, "default", embed=False)

    port = ask(store, "这个端口是多少", "default", use_llm=False)
    assert "8787" in port["answer"]

    numbered = ask(store, "端口号是多少", "default", use_llm=False)
    assert "8787" in numbered["answer"]

    size = ask(store, "文件最大是多少", "default", use_llm=False)
    assert "2MB" in size["answer"].splitlines()[0]


def test_short_term_does_not_stop_at_the_oldest_chunks(store: Store, tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    for number in range(25):
        (docs / f"noise-{number:02d}.md").write_text(
            f"# 噪声{number}\n\n这里只是提到端口，没有编号。\n",
            encoding="utf-8",
        )
    ingest_path(store, docs, "default", embed=False)
    real = tmp_path / "real.md"
    real.write_text("# 真实\n\n服务端口是 8787。\n", encoding="utf-8")
    ingest_path(store, real, "default", embed=False)

    found = ask(store, "端口是多少", "default", use_llm=False)
    assert "8787" in found["answer"]


def test_python_comment_remains_searchable_text(store: Store, tmp_path: Path):
    note = tmp_path / "secret.py"
    note.write_text("# 密钥 TOKEN-1\nvalue = 1\n", encoding="utf-8")
    ingest_path(store, note, "default", embed=False)
    found = ask(store, "TOKEN-1", "default", use_llm=False)
    assert "TOKEN-1" in found["citations"][0]["excerpt"]
    assert found["citations"][0]["title"] == "secret"


def test_citation_line_survives_leading_blank_lines(store: Store, tmp_path: Path):
    note = tmp_path / "pad.md"
    note.write_text("\n\n# 标题\n\n正文在第五行，标记 PAD-5。\n", encoding="utf-8")
    ingest_path(store, note, "default", embed=False)
    found = ask(store, "PAD-5", "default", use_llm=False)
    assert found["citations"][0]["line_start"] == 3
