"""rag 纯函数契约(防签名漂移)。

eval 的产物计算仅复用 rag 的 **chunk 切分**，BM25 分词由 eval 的 SQLite FTS5 模块负责。
验证 chunk 接口存在且签名未变——轻量,不触发网络/模型推理。需 toLink-Rag 可 import,
故标 ``contract``；普通本地环境缺依赖时跳过，CI 设置 ``LINKRAG_EVAL_REQUIRE_RAG=1``
后会在收集前直接失败。
"""

from __future__ import annotations

import inspect

import pytest

pytest.importorskip("src.core", reason="需安装 toLink-Rag(pip install -e <path>)")
pytestmark = pytest.mark.contract


def test_chunk_dataclass_fields() -> None:
    from src.core.splitter.models import Chunk

    assert {"content", "start_line", "end_line"} <= set(Chunk.__dataclass_fields__)


def test_chunking_engine_aprocess_signature() -> None:
    from src.core.splitter.chunking_engine import ChunkingEngine

    params = inspect.signature(ChunkingEngine.aprocess).parameters
    assert "text" in params and "source_file" in params
