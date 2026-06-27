"""EvalVectorIndexer 编排:注入 fake computer/store/repo,验证产物→点/行映射、id 确定性、bm25 mode。

不需 rag、不连 Qdrant/PG。
"""

from __future__ import annotations

from linkrag_eval.compute.protocol import DenseVec, SparseVec
from linkrag_eval.store.ids import eval_chunk_id
from linkrag_eval.store.indexer import EvalPassage, EvalVectorIndexer


class _FakeComputer:
    def __init__(self) -> None:
        self.sparse_called = False

    async def compute_dense(self, contents):
        return [DenseVec([float(len(c)), 0.1]) for c in contents]

    async def compute_sparse(self, contents):
        self.sparse_called = True
        return [SparseVec([1], [0.5]) for _ in contents]

    async def compute_chunks(self, text, *, source_file=None):  # 未用
        return []

    def compute_bm25_tokens(self, content):  # 未用
        raise NotImplementedError

    @property
    def dense_dim(self):
        return 2

    @property
    def fingerprint(self):
        return {}


class _FakeStore:
    def __init__(self) -> None:
        self.upserts: list[tuple] = []

    async def upsert(self, *, dataset_id, points):
        self.upserts.append((dataset_id, list(points)))


class _FakeRepo:
    def __init__(self) -> None:
        self.rows: list = []

    async def upsert_chunks(self, rows):
        self.rows = list(rows)
        return len(self.rows)


def _passages(n=2):
    return [EvalPassage(source_passage_id=f"p{i}", content=f"c{i}", doc_id=991310000 + i) for i in range(n)]


async def test_index_passages_maps_products() -> None:
    comp, store, repo = _FakeComputer(), _FakeStore(), _FakeRepo()
    idx = EvalVectorIndexer(computer=comp, vector_store=store, corpus_repo=repo)
    n = await idx.index_passages(990131, _passages(2))

    assert n == 2
    dataset_id, points = store.upserts[0]
    assert dataset_id == 990131
    # chunk_id 确定性
    assert points[0].chunk_id == eval_chunk_id(990131, 991310000, 0)
    assert points[0].sparse is not None  # 默认带 sparse
    # 语料行索引标记:dense/sparse=True,bm25(stub)=False
    assert repo.rows[0].dense_indexed is True
    assert repo.rows[0].sparse_indexed is True
    assert repo.rows[0].bm25_indexed is False


async def test_with_sparse_false_skips_sparse() -> None:
    comp, store, repo = _FakeComputer(), _FakeStore(), _FakeRepo()
    idx = EvalVectorIndexer(computer=comp, vector_store=store, corpus_repo=repo, with_sparse=False)
    await idx.index_passages(1, _passages(1))
    assert comp.sparse_called is False
    assert store.upserts[0][1][0].sparse is None
    assert repo.rows[0].sparse_indexed is False


async def test_bm25_mode_flags_row() -> None:
    comp, store, repo = _FakeComputer(), _FakeStore(), _FakeRepo()
    idx = EvalVectorIndexer(
        computer=comp, vector_store=store, corpus_repo=repo, bm25_mode="qdrant_bm25"
    )
    await idx.index_passages(1, _passages(1))
    assert repo.rows[0].bm25_indexed is True


async def test_empty_noop() -> None:
    comp, store, repo = _FakeComputer(), _FakeStore(), _FakeRepo()
    idx = EvalVectorIndexer(computer=comp, vector_store=store, corpus_repo=repo)
    assert await idx.index_passages(1, []) == 0
    assert store.upserts == []
