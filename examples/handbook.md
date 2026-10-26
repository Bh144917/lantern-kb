# Lantern 使用说明

Lantern 是放在你自己电脑上的知识库。文件夹里的原文不会上传，也不需要 API key。

## 服务

Lantern 的 Web 服务默认端口是 8787，只绑定 127.0.0.1。

数据目录默认叫 .lantern，数据库文件是 lantern.db。

## 没有模型时

没有连接 Ollama 时，Lantern 使用 SQLite 全文索引，并从原文抽出最相关的句子。

支持 Markdown、纯文本、HTML、常见源代码和 PDF。单个文本文件超过 2MB 会跳过。

## English

The default web port is 8787 and the server binds to 127.0.0.1 only.
Your notes stay on this computer. An API key is not required.
The database file is lantern.db inside the .lantern directory.
