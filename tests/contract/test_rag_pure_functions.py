"""rag 纯函数契约(防签名漂移)。

eval 对 rag 的依赖只剩 **chunk 切分** 与 **bm25 分词**(dense/sparse 已移到 eval llm 模块)。
只验这两处白名单纯函数存在且签名未变——轻量,不触发网络/模型推理。需 toLink-Rag 可 import,
故标 ``contract``;rag 不在环境时整文件跳过。
"""

from __future__ import annotations

import inspect

import pytest

pytest.importorskip("src", reason="需安装 toLink-Rag(pip install -e <path>)")


def test_chunk_dataclass_fields() -> None:
    from src.core.splitter.models import Chunk

    assert {"content", "start_line", "end_line"} <= set(Chunk.__dataclass_fields__)


def test_chunking_engine_aprocess_signature() -> None:
    from src.core.splitter.chunking_engine import ChunkingEngine

    params = inspect.signature(ChunkingEngine.aprocess).parameters
    assert "text" in params and "source_file" in params


def test_ragflow_tokenizer_contract() -> None:
    from src.core.preprocessor.ragflow_tokenizer import RagFlowTokenizer, TokenizedText

    assert hasattr(RagFlowTokenizer, "tokenize")
    assert {"coarse_tokens", "fine_tokens"} <= set(TokenizedText.__dataclass_fields__)
