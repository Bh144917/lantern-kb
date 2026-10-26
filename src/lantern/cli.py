from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lantern import __version__
from lantern.answer import ask
from lantern.config import Settings
from lantern.ingest import ingest_path
from lantern.ollama import Ollama, model_ready
from lantern.store import Store


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="lantern",
        description="Ask your own folders. Files stay on this machine.",
    )
    parser.add_argument("--home", type=Path, default=None, help="data directory, default ./.lantern")
    parser.add_argument("--version", action="version", version=f"lantern {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--home",
        type=Path,
        default=argparse.SUPPRESS,
        help="data directory, default ./.lantern",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ingest_parser = sub.add_parser("ingest", parents=[common], help="index a file or directory")
    ingest_parser.add_argument("path", type=Path)
    ingest_parser.add_argument("--library", default="default")
    ingest_parser.add_argument("--no-embed", action="store_true", help="skip Ollama embeddings")

    ask_parser = sub.add_parser("ask", parents=[common], help="ask the indexed library")
    ask_parser.add_argument("question")
    ask_parser.add_argument("--library", default="default")
    ask_parser.add_argument("--limit", type=int, default=6)
    ask_parser.add_argument("--extractive", action="store_true", help="quote the source, do not call Ollama")

    serve_parser = sub.add_parser("serve", parents=[common], help="open the local reading desk")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8787)

    sub.add_parser("status", parents=[common], help="show index and Ollama status")

    args = parser.parse_args(argv)
    if args.command == "serve":
        return _serve(Settings.load(args.home), args.host, args.port)

    settings = Settings.load(args.home)
    store = Store(settings.home)
    ollama = Ollama(settings.ollama_host, settings.chat_model, settings.embed_model)
    try:
        if args.command == "ingest":
            return _ingest(store, ollama, args)
        if args.command == "ask":
            return _ask(store, ollama, args)
        if args.command == "status":
            return _status(store, ollama, settings)
    finally:
        store.close()
    return 2


def _ingest(store: Store, ollama: Ollama, args: argparse.Namespace) -> int:
    try:
        report = ingest_path(
            store,
            args.path,
            args.library,
            ollama,
            embed=not args.no_embed,
        )
    except FileNotFoundError:
        print(f"Path not found: {args.path}", file=sys.stderr)
        return 1
    print(
        f"library {report.library}: indexed {report.indexed}, updated {report.updated}, "
        f"unchanged {report.unchanged}, skipped {report.skipped}, embedded {report.embedded}"
    )
    if report.embed_note:
        print(f"embeddings: {report.embed_note}")
    for error in report.errors:
        print(error)
    stored = report.indexed + report.updated + report.unchanged
    if stored == 0 and (report.errors or report.skipped):
        return 1
    return 0


def _ask(store: Store, ollama: Ollama, args: argparse.Namespace) -> int:
    try:
        result = ask(
            store,
            args.question,
            None if args.library == "*" else args.library,
            ollama,
            limit=args.limit,
            use_llm=not args.extractive,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(result["answer"])
    if result["citations"]:
        print()
    for citation in result["citations"]:
        place = citation["display_path"]
        if citation["line_start"]:
            place += f":{citation['line_start']}"
        heading = f" · {citation['heading']}" if citation["heading"] else ""
        print(f"[{citation['n']}] {place}{heading}")
        print(f"    {citation['excerpt']}")
    return 0


def _status(store: Store, ollama: Ollama, settings: Settings) -> int:
    counts = store.counts()
    health = ollama.health()
    print(f"home: {settings.home}")
    print(f"documents: {counts['documents']}")
    print(f"chunks: {counts['chunks']}")
    print(f"vectors: {counts['vectors']}")
    if health.get("ok"):
        models = health.get("models") or []
        chat_ok = model_ready(models, settings.chat_model)
        embed_ok = model_ready(models, settings.embed_model)
        if chat_ok and embed_ok:
            print(f"ollama: connected, chat {settings.chat_model}, embed {settings.embed_model}")
        else:
            missing = []
            if not chat_ok:
                missing.append(settings.chat_model)
            if not embed_ok:
                missing.append(settings.embed_model)
            print(f"ollama: connected, missing {', '.join(missing)}")
    else:
        print("ollama: not connected, answers will quote the original text")
    return 0


def _serve(settings: Settings, host: str, port: int) -> int:
    import uvicorn

    from lantern.server import create_app

    if host not in {"127.0.0.1", "localhost", "::1"}:
        print("Listening beyond localhost. Do this only on a network you trust.", file=sys.stderr)
    print(f"Lantern is at http://{host}:{port}")
    uvicorn.run(create_app(settings.home), host=host, port=port, log_level="info")
    return 0


def _utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except Exception:
            continue


if __name__ == "__main__":
    raise SystemExit(main())
