"""召回 factory 显式管理自己创建的客户端；不连接模型或向量服务。"""

from __future__ import annotations

import asyncio

import pytest

from linkrag_eval.config import EvalSettings
from linkrag_eval.retrieval import recall_factory


@pytest.mark.parametrize("outcome", [
    "success", "body_error", "cancelled", "assembly_error", "sparse_builder_error",
])
async def test_owned_clients_closed_on_all_exits(monkeypatch, outcome):
    import qdrant_client

    from linkrag_eval.llm import dense_client, sparse_client

    settings = EvalSettings(_env_file=None)
    events = []
    clients = {}
    entered = asyncio.Event()

    class Encoder:
        def __init__(self, name):
            self.name = name
            clients[name] = self
            events.append(f"create-{name}")

        async def aclose(self):
            events.append(f"close-{self.name}")

    class Qdrant:
        def __init__(self, **kwargs):
            assert kwargs == {"url": settings.qdrant_host, "api_key": None, "trust_env": False}
            clients["qdrant"] = self
            events.append("create-qdrant")

        async def close(self):
            events.append("close-qdrant")

    def dense_builder(actual):
        assert actual is settings
        return Encoder("dense")

    def sparse_builder(actual):
        assert actual is settings
        if outcome == "sparse_builder_error":
            raise ValueError("sparse build failure")
        return Encoder("sparse")

    pipeline = object()

    def build(**kwargs):
        assert kwargs == {
            "settings": settings, "dense_encoder": clients["dense"],
            "sparse_encoder": clients["sparse"], "qdrant_client": clients["qdrant"],
        }
        events.append("assemble")
        if outcome == "assembly_error":
            raise ValueError("pipeline build failure")
        return pipeline

    monkeypatch.setattr(dense_client, "build_dense_embedder", dense_builder)
    monkeypatch.setattr(sparse_client, "build_sparse_encoder", sparse_builder)
    monkeypatch.setattr(qdrant_client, "AsyncQdrantClient", Qdrant)
    monkeypatch.setattr(recall_factory, "build_eval_recall_pipeline", build)

    async def use_pipeline():
        async with recall_factory.open_eval_recall_pipeline(settings=settings) as actual:
            assert actual is pipeline
            entered.set()
            if outcome == "body_error":
                raise OSError("candidate output failure")
            if outcome == "cancelled":
                await asyncio.Event().wait()

    task = asyncio.create_task(use_pipeline())
    if outcome == "cancelled":
        await asyncio.wait_for(entered.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    elif outcome in {"assembly_error", "sparse_builder_error"}:
        with pytest.raises(ValueError, match="build failure"):
            await task
    elif outcome == "body_error":
        with pytest.raises(OSError, match="candidate output failure"):
            await task
    else:
        await task
    if outcome == "sparse_builder_error":
        assert events == ["create-dense", "close-dense"]
    else:
        assert events == [
            "create-dense", "create-sparse", "create-qdrant", "assemble",
            "close-qdrant", "close-sparse", "close-dense",
        ]
