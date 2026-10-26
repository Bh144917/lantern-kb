# 连接本机模型

嵌入模型默认是 nomic-embed-text。先执行 ollama pull nomic-embed-text，再执行 ollama pull qwen2.5:7b。

对话模型默认是 qwen2.5:7b。模型不存在时，提问仍会返回原文句子。

LANTERN_OLLAMA_HOST 默认是 http://127.0.0.1:11434。
