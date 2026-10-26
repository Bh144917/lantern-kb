from pathlib import Path

from lantern.cli import main
from tests.test_textutil import EXAMPLES


def test_cli_ingest_and_ask(tmp_path: Path, capsys):
    home = tmp_path / "home"
    assert main(["--home", str(home), "ingest", str(EXAMPLES), "--no-embed"]) == 0
    assert main(["--home", str(home), "ask", "默认端口是多少", "--extractive"]) == 0
    captured = capsys.readouterr()
    assert "8787" in captured.out
    assert "handbook.md" in captured.out


def test_cli_home_flag_after_the_command(tmp_path: Path, capsys):
    home = tmp_path / "home"
    note = tmp_path / "note.md"
    note.write_text("# 旗标\n\n旗标内容是 FLAG-8。\n", encoding="utf-8")
    assert main(["ingest", str(note), "--home", str(home), "--no-embed"]) == 0
    assert main(["ask", "旗标内容", "--home", str(home), "--extractive"]) == 0
    assert "FLAG-8" in capsys.readouterr().out


def test_missing_path_returns_one(tmp_path: Path):
    assert main(["ingest", str(tmp_path / "nope"), "--home", str(tmp_path / "home")]) == 1
