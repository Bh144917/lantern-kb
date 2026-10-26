# Lantern

[![test](https://github.com/Bh144917/lantern-kb/actions/workflows/test.yml/badge.svg)](https://github.com/Bh144917/lantern-kb/actions/workflows/test.yml)

Ask your own folders. The files stay on this machine.

Lantern indexes notes, PDFs, and code, then answers with the passage it used. It does not need an API key. If [Ollama](https://ollama.com) is running, a local model writes the reply from those passages. If it is not, Lantern still answers by quoting the closest lines.

```text
lantern ingest ./notes
lantern ask "默认端口是多少"
```

## Start

Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
lantern ingest ./examples
lantern ask "默认端口是多少"
lantern serve
```

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\lantern ingest .\examples
.\.venv\Scripts\lantern ask "默认端口是多少"
.\.venv\Scripts\lantern serve
```

Open http://127.0.0.1:8787 and ask again. The example button on the desk indexes `./examples`, so start the server from this directory.

`8787` in the answer comes from `examples/handbook.md`, and the citation under the answer points at that file. That is the whole product: a question, a quotation, and the path back to the original.

## Add a model later

Full-text search works before any model is installed. To let a local model write the answer:

```bash
ollama pull nomic-embed-text
ollama pull qwen2.5:7b
lantern ingest ./notes
```

The second ingest fills in vectors. Questions then go to `qwen2.5:7b` with the retrieved passages. If the model is missing or Ollama is stopped, Lantern goes back to quoting the source instead of failing the question.

| Variable | Default | Role |
| --- | --- | --- |
| `LANTERN_HOME` | `./.lantern` | database and uploads |
| `LANTERN_OLLAMA_HOST` | `http://127.0.0.1:11434` | local model server |
| `LANTERN_CHAT_MODEL` | `qwen2.5:7b` | used only when Ollama is up |
| `LANTERN_EMBED_MODEL` | `nomic-embed-text` | optional vectors |

## Commands

```text
lantern ingest ./notes --library default
lantern ingest ./notes --no-embed
lantern ask "上次的决定是什么"
lantern ask "what did we decide" --extractive
lantern ask "search every library" --library "*"
lantern status
lantern serve --host 127.0.0.1 --port 8787
```

`--home` sets the data directory and can sit before or after the command:

```text
lantern --home D:\lantern-data ingest .\notes
lantern ingest .\notes --home D:\lantern-data
```

The server reads any path you give it and binds to `127.0.0.1` unless you change `--host`. Do not expose it on a shared network; there is no login.

Indexed types: Markdown, plain text, HTML, PDF, and common source files. `node_modules`, `.git`, virtualenvs, and hidden files are skipped. A text file over 2MB is skipped. Re-running ingest does nothing when the file bytes have not changed.

## How a question is answered

1. Chinese and English terms are taken out of the question. Glue such as “什么” and “多少” is removed first.
2. SQLite FTS5 trigram search finds candidate passages. Terms shorter than 3 characters use a substring search instead.
3. If embeddings for the configured model exist, they are merged with the keyword hits.
4. The answer is either a quotation marked `[1]`, or an Ollama reply that was told to use only those passages.
5. The original path, heading, and line stay attached either way.

## HTTP

| | |
| --- | --- |
| `GET /api/health` | index counts and whether Ollama responded |
| `GET /api/documents` | indexed files |
| `POST /api/ingest` | `{"path": "D:\\notes", "embed": true}` |
| `POST /api/examples` | index `./examples` |
| `POST /api/upload` | multipart files |
| `POST /api/ask` | `{"question": "默认端口是多少"}` |
| `DELETE /api/documents/{id}` | remove one file |

Interactive API docs are at http://127.0.0.1:8787/docs while the server is running.

## Docker

Ollama on the host stays reachable at `host.docker.internal`.

```bash
docker compose up --build
```

The index is kept in the `lantern-data` volume. To index a host folder, add it to `docker-compose.yml` and pass that container path in the desk form:

```yaml
volumes:
  - lantern-data:/data
  - D:\notes:/notes:ro
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## 中文

Lantern 把一个文件夹做成可以提问的本地资料库。原文留在这台电脑上，不需要 API key。没装 Ollama 时，它用 SQLite 全文检索，并把最相关的原句连同文件路径一起返回。装了 Ollama 之后，本机模型只根据检索到的段落写回答；模型不可用时自动退回引用，提问不会失败。

适合自己的笔记、项目文档、论文 PDF 和代码目录。先索引，再提问，回答下面始终有出处。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\lantern ingest .\examples
.\.venv\Scripts\lantern ask "默认端口是多少"
.\.venv\Scripts\lantern serve
```

浏览器打开 http://127.0.0.1:8787 。数据在当前目录的 `.lantern` 里。默认只监听本机。

## License

MIT
