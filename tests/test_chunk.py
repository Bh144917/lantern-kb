from lantern.chunk import chunk_document


def test_citation_line_stays_on_the_heading():
    pieces = chunk_document("# 标题\n\n正文在下一行。\n")
    assert pieces[0].heading == "标题"
    assert pieces[0].line_start == 1


def test_headings_become_separate_pieces():
    text = "# 服务\n\n默认端口是 8787。\n\n# 模型\n\n可以使用本机模型。\n"
    pieces = chunk_document(text, size=80, overlap=10)
    headings = {piece.heading for piece in pieces}
    assert headings == {"服务", "模型"}


def test_leading_blank_lines_keep_the_heading_line():
    pieces = chunk_document("\n\n# 标题\n\n正文在第五行。\n")
    assert pieces[0].line_start == 3
    assert pieces[0].heading == "标题"


def test_later_paragraph_gets_its_own_line():
    text = "# 标题\n\n" + ("甲" * 200) + "\n\n" + ("乙" * 80) + "\n"
    pieces = chunk_document(text, size=180, overlap=20)
    later = [piece for piece in pieces if piece.text.startswith("乙")]
    assert later
    assert later[0].line_start == 5


def test_fenced_code_is_not_a_heading():
    text = "说明\n\n```python\n# 配置项 TOKEN-9\nx = 1\n```\n\n后文。\n"
    pieces = chunk_document(text)
    assert all(piece.heading != "配置项 TOKEN-9" for piece in pieces)
    assert any("TOKEN-9" in piece.text for piece in pieces)


def test_source_comments_stay_in_the_text_when_headings_are_off():
    pieces = chunk_document("# 密钥 TOKEN-1\nvalue = 1\n", headings=False)
    assert pieces[0].heading == ""
    assert "TOKEN-1" in pieces[0].text
    assert "value = 1" in pieces[0].text


def test_long_paragraph_stays_within_the_chunk_size():
    text = "甲" * 2500
    pieces = chunk_document(text, size=900, overlap=140)
    assert len(pieces) >= 3
    assert all(len(piece.text) <= 900 for piece in pieces)
    assert pieces[0].text[-80:] in (pieces[1].text[:200] + pieces[0].text[-80:])
    assert pieces[0].text[-60:] in pieces[1].text
