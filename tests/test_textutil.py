from pathlib import Path

from lantern.textutil import keywords

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def test_question_words_are_not_search_terms():
    terms = keywords("什么是默认端口")
    assert "默认端口" in terms
    assert "什么" not in terms


def test_long_chinese_question_keeps_the_useful_window():
    terms = keywords("如何配置嵌入模型")
    assert "嵌入模型" in terms


def test_examples_exist():
    assert (EXAMPLES / "handbook.md").is_file()
    assert (EXAMPLES / "ollama.md").is_file()
    assert (EXAMPLES / "sample.py").is_file()
