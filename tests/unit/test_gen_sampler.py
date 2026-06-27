"""采样器单测:配额、分层轮转、相邻组队(搬迁自源 test_gen.py)+ ChunkSampler 读 eval 语料。

源版 FakeChunk(ChunkRecordDB 形)换成 eval ``SampledChunk``;ChunkSampler 用 fake repo
注入语料行,验证从 eval 语料到 SampledChunk 的映射与分层/组队链路。
"""

from __future__ import annotations

from linkrag_eval.golden.gen.sampler import (
    ChunkSampler,
    SampledChunk,
    SampleSpec,
    group_adjacent,
    stratified_pick,
)
from linkrag_eval.models import QuestionType
from linkrag_eval.store.corpus_repo import CorpusChunkRow


def chunk(cid: str, doc_id: int, set_id: int, *, chunk_index: int = 0) -> SampledChunk:
    return SampledChunk(
        chunk_id=cid, content="x" * 100, user_id=990001,
        set_id=set_id, doc_id=doc_id, chunk_index=chunk_index,
    )


class TestSampleSpec:
    def test_quota_sums_to_n(self):
        spec = SampleSpec(user_id=1, dataset_ids=[1], n=50)
        quota = spec.quota()
        assert sum(quota.values()) == 50
        assert quota[QuestionType.KEYWORD] >= quota[QuestionType.CROSS_DOC]


class TestStratifiedPick:
    def test_round_robin_across_buckets(self):
        chunks = [chunk(f"a{i}", 1, 1) for i in range(10)] + [
            chunk(f"b{i}", 2, 2) for i in range(10)
        ]
        picked = stratified_pick(chunks, 6, seed=1)
        sets = [c.set_id for c in picked]
        assert sets.count(1) == 3 and sets.count(2) == 3

    def test_deterministic_with_seed(self):
        chunks = [chunk(f"c{i}", 1, 1) for i in range(20)]
        p1 = [c.chunk_id for c in stratified_pick(chunks, 5, seed=7)]
        p2 = [c.chunk_id for c in stratified_pick(chunks, 5, seed=7)]
        assert p1 == p2

    def test_exhausts_small_buckets(self):
        chunks = [chunk("a0", 1, 1)] + [chunk(f"b{i}", 2, 2) for i in range(10)]
        picked = stratified_pick(chunks, 5, seed=1)
        assert len(picked) == 5


class TestGroupAdjacent:
    def test_groups_contiguous_index(self):
        chunks = [
            chunk("c0", 1, 1, chunk_index=0),
            chunk("c1", 1, 1, chunk_index=1),
            chunk("c3", 1, 1, chunk_index=3),  # 缺口:不与 c1 成组
            chunk("c4", 1, 1, chunk_index=4),
        ]
        groups = group_adjacent(chunks, 2)
        ids = [[c.chunk_id for c in g] for g in groups]
        assert ["c0", "c1"] in ids
        assert ["c3", "c4"] in ids
        assert all("c1" not in g or "c3" not in g for g in ids)


class _FakeRepo:
    """按 dataset_ids 回放预设 CorpusChunkRow,验证采样器的 eval 语料读路径。"""

    def __init__(self, rows: list[CorpusChunkRow]):
        self._rows = rows

    async def fetch_chunks_for_datasets(self, dataset_ids, *, min_content_chars=0):
        ids = set(dataset_ids)
        return [
            r for r in self._rows
            if r.dataset_id in ids and len((r.content or "").strip()) >= min_content_chars
        ]


def _row(cid: str, dataset_id: int, doc_id: int, *, ordinal: int = 0, content: str = "x" * 100):
    return CorpusChunkRow(
        chunk_id=cid, dataset_id=dataset_id, doc_id=doc_id,
        content=content, content_hash="h", ordinal=ordinal,
    )


class TestChunkSampler:
    async def test_maps_rows_injecting_user_id_and_index(self):
        repo = _FakeRepo([_row("c0", 5, 50, ordinal=3)])
        sampler = ChunkSampler(repo, user_id=990001)
        spec = SampleSpec(user_id=990001, dataset_ids=[5], n=1)
        [picked] = await sampler.sample_single(spec)
        assert picked.user_id == 990001        # 路由常量注入
        assert picked.set_id == 5              # dataset_id → set_id
        assert picked.chunk_index == 3         # ordinal → chunk_index
        assert picked.chunk_type == "text"

    async def test_min_content_filters_short(self):
        repo = _FakeRepo([_row("short", 5, 50, content="abc"), _row("ok", 5, 51)])
        sampler = ChunkSampler(repo, user_id=1)
        spec = SampleSpec(user_id=1, dataset_ids=[5], n=10, min_content_chars=50)
        picked = await sampler.sample_single(spec)
        assert [c.chunk_id for c in picked] == ["ok"]

    async def test_sample_groups_adjacent(self):
        rows = [_row(f"c{i}", 5, 50, ordinal=i) for i in range(4)]
        sampler = ChunkSampler(_FakeRepo(rows), user_id=1)
        spec = SampleSpec(user_id=1, dataset_ids=[5], n=10, multi_chunk_size=2)
        groups = await sampler.sample_groups(spec)
        assert all(len(g) == 2 for g in groups)
        assert sum(len(g) for g in groups) == 4
