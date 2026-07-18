"""Golden V2 alt embedding 本地候选搜索。

优先使用可选 NumPy 做矩阵乘法;环境没有 NumPy 时退回纯 Python
按 dataset 分组 + heap topK。该模块不写 Qdrant,只服务候选池独立来源。
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Any, Sequence


try:  # pragma: no cover - 是否安装 NumPy 取决于运行环境,功能由 fallback 覆盖。
    import numpy as _np
except Exception:  # pragma: no cover
    _np = None


@dataclass(frozen=True)
class AltEmbeddingHit:
    chunk_id: str
    doc_id: int
    dataset_id: int
    score: float


class AltEmbeddingSearcher:
    """对已缓存/已编码的 alt embedding chunk 做本地 cosine topK。"""

    def __init__(self, *, embedder: Any, chunks: Sequence[Any], vectors: Sequence[Sequence[float]]) -> None:
        self._embedder = embedder
        self._chunks = list(chunks)
        if len(self._chunks) != len(vectors):
            raise ValueError(f"chunks/vectors 数量不符:{len(self._chunks)} != {len(vectors)}")
        self._numpy_ready = False
        self._vectors_by_dataset: dict[int, list[tuple[Any, list[float]]]] = {}
        if _np is not None and self._chunks:
            self._init_numpy(vectors)
        else:
            self._init_python(vectors)

    async def search(self, query: str, dataset_ids: list[int], top_n: int) -> list[AltEmbeddingHit]:
        if top_n <= 0:
            return []
        query_vec = await self._embedder.aembed_query(query)
        if self._numpy_ready:
            return self._search_numpy(query_vec, dataset_ids, top_n)
        return self._search_python(query_vec, dataset_ids, top_n)

    @property
    def backend(self) -> str:
        return "numpy" if self._numpy_ready else "python"

    def _init_numpy(self, vectors: Sequence[Sequence[float]]) -> None:
        matrix = _np.asarray(vectors, dtype=_np.float32)
        if matrix.ndim != 2:
            self._init_python(vectors)
            return
        norms = _np.linalg.norm(matrix, axis=1)
        norms[norms == 0] = 1.0
        self._matrix = matrix / norms[:, None]
        self._dataset_ids = _np.asarray([int(c.dataset_id) for c in self._chunks], dtype=_np.int64)
        self._numpy_ready = True

    def _init_python(self, vectors: Sequence[Sequence[float]]) -> None:
        self._numpy_ready = False
        grouped: dict[int, list[tuple[Any, list[float]]]] = {}
        for chunk, vec in zip(self._chunks, vectors):
            grouped.setdefault(int(chunk.dataset_id), []).append((chunk, _normalize_vector(vec)))
        self._vectors_by_dataset = grouped

    def _search_numpy(
        self,
        query_vec: Sequence[float],
        dataset_ids: list[int],
        top_n: int,
    ) -> list[AltEmbeddingHit]:
        q = _np.asarray(query_vec, dtype=_np.float32)
        norm = float(_np.linalg.norm(q))
        if norm <= 0:
            q = _np.zeros_like(q)
        else:
            q = q / norm
        allowed = set(int(x) for x in dataset_ids)
        if allowed:
            mask = _np.isin(self._dataset_ids, list(allowed))
            source_indices = _np.nonzero(mask)[0]
        else:
            source_indices = _np.arange(len(self._chunks))
        if source_indices.size == 0:
            return []
        scores = self._matrix[source_indices] @ q
        n = min(top_n, int(scores.shape[0]))
        if n <= 0:
            return []
        if scores.shape[0] > n:
            local = _np.argpartition(scores, -n)[-n:]
        else:
            local = _np.arange(scores.shape[0])
        ordered = sorted(
            ((int(source_indices[i]), float(scores[i])) for i in local),
            key=lambda item: (-item[1], str(self._chunks[item[0]].chunk_id)),
        )
        return [
            AltEmbeddingHit(
                chunk_id=str(self._chunks[i].chunk_id),
                doc_id=int(self._chunks[i].doc_id),
                dataset_id=int(self._chunks[i].dataset_id),
                score=score,
            )
            for i, score in ordered[:n]
        ]

    def _search_python(
        self,
        query_vec: Sequence[float],
        dataset_ids: list[int],
        top_n: int,
    ) -> list[AltEmbeddingHit]:
        q = _normalize_vector(query_vec)
        allowed = [int(x) for x in dataset_ids]
        if allowed:
            pools = [item for did in allowed for item in self._vectors_by_dataset.get(did, [])]
        else:
            pools = [item for group in self._vectors_by_dataset.values() for item in group]
        best = heapq.nsmallest(
            top_n,
            (
                (
                    -_dot(q, vec),
                    str(chunk.chunk_id),
                    chunk,
                )
                for chunk, vec in pools
            ),
        )
        return [
            AltEmbeddingHit(
                chunk_id=str(chunk.chunk_id),
                doc_id=int(chunk.doc_id),
                dataset_id=int(chunk.dataset_id),
                score=-neg_score,
            )
            for neg_score, _, chunk in best
        ]


def normalize_vector(values: Sequence[float]) -> list[float]:
    return _normalize_vector(values)


def _normalize_vector(values: Sequence[float]) -> list[float]:
    vec = [float(x) for x in values]
    norm = math.sqrt(sum(x * x for x in vec))
    if norm <= 0:
        return [0.0 for _ in vec]
    return [x / norm for x in vec]


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(left, right))
