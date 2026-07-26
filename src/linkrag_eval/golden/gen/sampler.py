"""chunk 采样:只在冻结评测语料范围内(固定 dataset_ids),分层抽样。

分层按 (set_id, chunk_type) 桶轮转,避免集中在少数长文档;过滤过短 chunk 降"答不出"噪声。
cross_doc 组取同 doc 相邻 chunk_index。

**解耦改动**:源版 ``ChunkSampler`` 读生产 ``ChunkRecordDB``(经 AsyncSession 直查生产库);
这里改读 **eval 自有语料**(:class:`~linkrag_eval.store.corpus_repo.EvalCorpusRepo` 的
``eval_corpus_chunk``)。eval 语料无 ``user_id``(路由常量,装配时注入)、无 ``chunk_type``
(全文本,恒 "text")、``ordinal`` 即 ``chunk_index``。采样器把仓储行映射成满足
:class:`~linkrag_eval.golden.gen.generator.GenChunk` 的 :class:`SampledChunk`,喂给生成器。
纯函数 ``stratified_pick`` / ``group_adjacent`` 鸭子类型,搬迁不变。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Sequence

from linkrag_eval.models import QuestionType

if TYPE_CHECKING:
    from linkrag_eval.store.corpus_repo import CorpusChunkRow, EvalCorpusRepo

_MIN_CONTENT_CHARS = 50


@dataclass
class SampledChunk:
    """采样产物:满足 ``GenChunk`` 形状的语料 chunk(user_id 注入、chunk_type 恒 text)。"""

    chunk_id: str
    content: str
    user_id: int
    set_id: int          # = dataset_id
    doc_id: int
    chunk_index: int     # = eval_corpus_chunk.ordinal
    chunk_type: str = "text"


@dataclass
class SampleSpec:
    user_id: int                 # 冻结评测语料/租户(eval 路由常量)
    dataset_ids: list[int]
    n: int                       # 目标条数
    type_mix: dict[QuestionType, float] = field(
        default_factory=lambda: {
            QuestionType.KEYWORD: 0.35,
            QuestionType.PARAPHRASE: 0.30,
            QuestionType.LONGTAIL: 0.20,
            QuestionType.CROSS_DOC: 0.15,
        }
    )
    multi_chunk_size: int = 2    # cross_doc 时一组取几个
    min_content_chars: int = _MIN_CONTENT_CHARS
    seed: int = 20260613         # 确定性采样(可复现)

    def quota(self) -> dict[QuestionType, int]:
        """按配比折成条数;余数给占比最大的类型。"""
        total_weight = sum(self.type_mix.values()) or 1.0
        quota = {
            t: int(self.n * w / total_weight) for t, w in self.type_mix.items()
        }
        remainder = self.n - sum(quota.values())
        if remainder and quota:
            top = max(self.type_mix, key=lambda t: self.type_mix[t])
            quota[top] += remainder
        return quota


def stratified_pick(
    chunks: Sequence[SampledChunk], n: int, *, seed: int
) -> list[SampledChunk]:
    """按 (set_id, chunk_type) 分桶轮转抽样:每桶内打乱,轮流各出一个直到取满。"""
    buckets: dict[tuple, list] = {}
    for c in chunks:
        buckets.setdefault((c.set_id, c.chunk_type), []).append(c)
    rng = random.Random(seed)
    for bucket in buckets.values():
        bucket.sort(key=lambda c: c.chunk_id)
        rng.shuffle(bucket)
    picked: list = []
    keys = sorted(buckets, key=str)
    i = 0
    while len(picked) < n and any(buckets[k] for k in keys):
        key = keys[i % len(keys)]
        if buckets[key]:
            picked.append(buckets[key].pop())
        i += 1
    return picked


def group_adjacent(
    chunks: Sequence[SampledChunk], group_size: int
) -> list[list[SampledChunk]]:
    """同 doc_id 相邻 chunk_index 组队(cross_doc 候选)。"""
    by_doc: dict[int, list] = {}
    for c in chunks:
        if c.chunk_index is not None:
            by_doc.setdefault(c.doc_id, []).append(c)
    groups = []
    for doc_chunks in by_doc.values():
        doc_chunks.sort(key=lambda c: c.chunk_index)
        for i in range(0, len(doc_chunks) - group_size + 1, group_size):
            window = doc_chunks[i : i + group_size]
            # 必须真相邻(chunk_index 连续),避免跨缺口拼凑
            idxs = [c.chunk_index for c in window]
            if idxs == list(range(idxs[0], idxs[0] + group_size)):
                groups.append(window)
    return groups


def _to_sampled(row: "CorpusChunkRow", *, user_id: int) -> SampledChunk:
    return SampledChunk(
        chunk_id=row.chunk_id,
        content=row.content,
        user_id=user_id,
        set_id=row.dataset_id,
        doc_id=row.doc_id,
        chunk_index=row.ordinal,
    )


class ChunkSampler:
    """从 eval 语料(EvalCorpusRepo)分层采样,产 :class:`SampledChunk`。"""

    def __init__(self, repo: "EvalCorpusRepo", *, user_id: int):
        self.repo = repo
        self.user_id = user_id

    async def _fetch_active(self, spec: SampleSpec) -> list[SampledChunk]:
        rows = await self.repo.fetch_chunks_for_datasets(
            spec.dataset_ids, min_content_chars=spec.min_content_chars
        )
        return [_to_sampled(r, user_id=self.user_id) for r in rows]

    async def sample_single(self, spec: SampleSpec) -> list[SampledChunk]:
        """单 chunk 候选(单跳问题),分层抽样取 spec.n 个。"""
        return stratified_pick(await self._fetch_active(spec), spec.n, seed=spec.seed)

    async def sample_groups(self, spec: SampleSpec) -> list[list[SampledChunk]]:
        """相关 chunk 组(多跳/跨片段),同 doc 相邻 chunk_index。"""
        groups = group_adjacent(await self._fetch_active(spec), spec.multi_chunk_size)
        rng = random.Random(spec.seed)
        rng.shuffle(groups)
        return groups[: spec.n]
