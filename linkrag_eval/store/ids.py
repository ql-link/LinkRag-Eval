"""确定性 id 与 hash(搬迁源仓库口径,纯函数,零依赖)。

``chunk_id`` 用 uuid5:同输入恒等 → 冻结语料 re-ingest 不变 → qrels 不失效;dense/sparse/bm25
三路与 qrels 共用同一 id。必须是合法 Qdrant point id(UUID),故用 uuid5 而非可读串。
"""

from __future__ import annotations

import hashlib
import uuid


def content_hash(content: str) -> str:
    """sha256(content),与生产 ChunkDraftFactory 同口径。"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def eval_chunk_key(dataset_id: int, doc_id: int, ordinal: int) -> str:
    """人类可读的确定性命名键(uuid5 种子;也便于排障对照)。"""
    return f"eval-{dataset_id}-{doc_id}-{ordinal}"


def eval_chunk_id(dataset_id: int, doc_id: int, ordinal: int) -> str:
    """确定性 chunk_id:对 :func:`eval_chunk_key` 取 uuid5。"""
    return str(
        uuid.uuid5(uuid.NAMESPACE_DNS, f"tolink-eval:{eval_chunk_key(dataset_id, doc_id, ordinal)}")
    )
