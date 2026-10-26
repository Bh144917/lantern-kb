from pathlib import Path

from lantern.textutil import coverage, keywords

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def test_question_words_are_not_search_terms():
    terms = keywords("什么是默认端口")
    assert "默认端口" in terms
    assert "什么" not in terms


def test_long_chinese_question_keeps_the_useful_window():
    terms = keywords("如何配置嵌入模型")
    assert "嵌入模型" in terms


def test_shorter_form_of_a_word_is_still_searched():
    assert "端口" in keywords("这个端口是多少")
    assert "端口" in keywords("端口号是多少")
    assert "最大" in keywords("文件最大是多少")


def test_unit_matches_when_it_is_glued_to_a_number():
    assert coverage("单个文本文件超过 2MB 会跳过。", ["MB"]) > 0
    assert coverage("English breakfast", ["is"]) == 0


def test_examples_exist():
    assert (EXAMPLES / "handbook.md").is_file()
    assert (EXAMPLES / "ollama.md").is_file()
    assert (EXAMPLES / "sample.py").is_file()
