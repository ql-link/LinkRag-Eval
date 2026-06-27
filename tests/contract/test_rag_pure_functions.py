"""rag 纯函数契约(防签名漂移)。

只验"白名单纯函数存在且签名未变"——轻量,不触发网络/模型推理。输出形状的重契约
(真调 embed/tokenize 断言维度)属活栈,放 integration。需 toLink-Rag 可 import,
故标 ``contract``;rag 不在环境时整文件跳过。
"""

from __future__ import annotations

import inspect

import pytest

pytest.importorskip("src", reason="需安装 toLink-Rag(pip install -e <path>)")


def test_chunk_embedding_pipeline_factory_signature() -> None:
    from src.core.splitter.factory import create_chunk_embedding_pipeline

    sig = inspect.signature(create_chunk_embedding_pipeline)
    assert len(sig.parameters) == 0  # 系统级,无入参


def test_aembed_chunks_signature() -> None:
    from src.core.splitter.embedding_pipeline import ChunkEmbeddingPipeline

    assert hasattr(ChunkEmbeddingPipeline, "aembed_chunks")
    params = inspect.signature(ChunkEmbeddingPipeline.aembed_chunks).parameters
    assert "chunks" in params


def test_chunk_dataclass_fields() -> None:
    from src.core.splitter.models import Chunk, EmbeddedChunk

    assert {"content", "start_line", "end_line"} <= set(Chunk.__dataclass_fields__)
    assert {"chunk", "embedding"} <= set(EmbeddedChunk.__dataclass_fields__)


def test_chunking_engine_aprocess_signature() -> None:
    from src.core.splitter.chunking_engine import ChunkingEngine

    params = inspect.signature(ChunkingEngine.aprocess).parameters
    assert "text" in params and "source_file" in params


def test_ragflow_tokenizer_contract() -> None:
    from src.core.preprocessor.ragflow_tokenizer import RagFlowTokenizer, TokenizedText

    assert hasattr(RagFlowTokenizer, "tokenize")
    assert {"coarse_tokens", "fine_tokens"} <= set(TokenizedText.__dataclass_fields__)


def test_sparse_service_has_vectorize_texts() -> None:
    from src.core.encoding.sparse.pipeline import SparseVectorService

    params = inspect.signature(SparseVectorService.vectorize_texts).parameters
    assert "texts" in params
