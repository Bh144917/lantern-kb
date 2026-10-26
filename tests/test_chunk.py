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


def test_long_paragraph_stays_within_the_chunk_size():
    text = "甲" * 2500
    pieces = chunk_document(text, size=900, overlap=140)
    assert len(pieces) >= 3
    assert all(len(piece.text) <= 900 for piece in pieces)
    assert pieces[0].text[-80:] in (pieces[1].text[:200] + pieces[0].text[-80:])
    assert pieces[0].text[-60:] in pieces[1].text
