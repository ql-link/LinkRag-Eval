"""LinkRag-Eval:toLink-Rag 的独立评测/质检框架。

只通过产物级纯函数复用生产计算能力(见 compute/),自持存储(eval 前缀 Qdrant +
独立 Postgres),与生产物理隔离。依赖边界见 AGENTS.md 三 + .importlinter。
"""

__version__ = "0.1.0"
