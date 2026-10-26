"""示例代码，用来确认源码文件也能被索引。"""


def ignored_directory():
    """索引目录时会跳过 node_modules。"""
    return "node_modules"
