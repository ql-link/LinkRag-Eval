"""EvalVectorIndexer 编排:注入 fake computer/store/repo,验证产物→点/行映射、id 确定性、bm25 mode。

不需 rag、不连真实存储。
"""

from __future__ import annotations

import pytest

from linkrag_eval.compute.protocol import Bm25Tokens, DenseVec, SparseVec
from linkrag_eval.compute.rag_adapter import RagProductComputer
from linkrag_eval.store.corpus_repo import EvalCorpusRepo
from linkrag_eval.store.engine import close_eval_engines
from linkrag_eval.store.ids import eval_chunk_id
from linkrag_eval.store.indexer import EvalPassage, EvalVectorIndexer


class _FakeComputer:
    def __init__(self) -> None:
        self.sparse_called = False

    async def compute_dense(self, contents):
        return [DenseVec([float(len(c)), 0.1], input_chars=len(c)) for c in contents]

    async def compute_sparse(self, contents):
        self.sparse_called = True
        return [SparseVec([1], [0.5], input_chars=len(c)) for c in contents]

    async def compute_chunks(self, text, *, source_file=None):  # 未用
        return []

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
        self.pending: list = []

    async def mark_chunks_pending(self, *, dataset_id, chunk_ids):
        self.pending.append((dataset_id, list(chunk_ids)))
        return 0

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
    assert points[0].bm25_tokens is None
    # 语料行索引标记:dense/sparse=True,bm25(stub)=False
    assert repo.rows[0].dense_indexed is True
    assert repo.rows[0].sparse_indexed is True
    assert repo.rows[0].bm25_indexed is False
    assert repo.rows[0].dense_input_chars == len(_passages()[0].content)
    assert repo.rows[0].sparse_input_chars == len(_passages()[0].content)
    assert repo.pending == [(990131, [row.chunk_id for row in repo.rows])]


async def test_with_sparse_false_skips_sparse() -> None:
    comp, store, repo = _FakeComputer(), _FakeStore(), _FakeRepo()
    idx = EvalVectorIndexer(computer=comp, vector_store=store, corpus_repo=repo, with_sparse=False)
    await idx.index_passages(1, _passages(1))
    assert comp.sparse_called is False
    assert store.upserts[0][1][0].sparse is None
    assert repo.rows[0].sparse_indexed is False


async def test_sqlite_bm25_mode_flags_row() -> None:
    comp, store, repo = _FakeComputer(), _FakeStore(), _FakeRepo()
    idx = EvalVectorIndexer(
        computer=comp, vector_store=store, corpus_repo=repo, bm25_mode="sqlite_fts5"
    )
    await idx.index_passages(1, _passages(1))
    assert repo.rows[0].bm25_indexed is True
    assert store.upserts[0][1][0].bm25_tokens == Bm25Tokens(coarse="c0", fine="c0")


async def test_empty_noop() -> None:
    comp, store, repo = _FakeComputer(), _FakeStore(), _FakeRepo()
    idx = EvalVectorIndexer(computer=comp, vector_store=store, corpus_repo=repo)
    assert await idx.index_passages(1, []) == 0
    assert store.upserts == []


async def test_product_metadata_preserves_per_item_lengths_and_original_full_text() -> None:
    texts = ["  前缀🙂\t尾部词  ", "abc尾巴"]
    dense_products = [DenseVec([0.1, 0.2], input_chars=4), DenseVec([0.3, 0.4], input_chars=5)]
    sparse_products = [SparseVec([1], [0.5], input_chars=3), SparseVec([2], [0.7], input_chars=2)]

    class Dense:
        dim = 2
        model_name = "dense"
        input_length_policy = "prefix_on_length_error"

        async def aembed(self, _):
            raise AssertionError("产物计算必须使用带元数据接口")

        async def aembed_with_metadata(self, contents):
            assert contents == texts
            return dense_products

    class Sparse:
        model_name = "sparse"
        input_length_policy = "prefix_on_length_error"

        async def aencode(self, contents):
            assert contents == texts
            return sparse_products

    computer = RagProductComputer(dense_encoder=Dense(), sparse_encoder=Sparse())
    store, repo = _FakeStore(), _FakeRepo()
    indexer = EvalVectorIndexer(
        computer=computer, vector_store=store, corpus_repo=repo, bm25_mode="sqlite_fts5"
    )
    passages = [EvalPassage(f"pid{i}", text, 10 + i) for i, text in enumerate(texts)]
    await indexer.index_passages(123, passages)

    assert [(row.dense_input_chars, row.sparse_input_chars) for row in repo.rows] == [(4, 3), (5, 2)]
    assert [row.content for row in repo.rows] == texts
    assert [row.char_len for row in repo.rows] == [len(text) for text in texts]
    assert [row.source_passage_id for row in repo.rows] == ["pid0", "pid1"]
    points = store.upserts[0][1]
    assert [point.dense for point in points] == [product.values for product in dense_products]
    assert [point.sparse for point in points] == sparse_products
    assert "尾" in points[0].bm25_tokens.coarse
    assert computer.fingerprint["dense_input_length_policy"] == "prefix_on_length_error"
    assert computer.fingerprint["sparse_input_length_policy"] == "prefix_on_length_error"


@pytest.mark.parametrize("bad_length", [-1, 0, 100, True, 1.5])
async def test_invalid_receipt_rejected_before_any_storage_write(bad_length) -> None:
    class InvalidComputer(_FakeComputer):
        async def compute_dense(self, contents):
            return [DenseVec([1.0, 0.1], input_chars=bad_length) for _ in contents]

    store, repo = _FakeStore(), _FakeRepo()
    indexer = EvalVectorIndexer(computer=InvalidComputer(), vector_store=store, corpus_repo=repo)
    with pytest.raises(ValueError, match="编码输入长度"):
        await indexer.index_passages(1, _passages(1))
    assert store.upserts == []
    assert repo.pending == []


@pytest.mark.parametrize("content,input_chars", [("", 0), ("原文🙂", None)])
async def test_empty_known_length_and_unknown_length_remain_distinct(content, input_chars) -> None:
    class ReceiptComputer(_FakeComputer):
        async def compute_dense(self, contents):
            return [DenseVec([1.0, 0.1], input_chars=input_chars) for _ in contents]

        async def compute_sparse(self, contents):
            return [SparseVec([1], [0.5], input_chars=input_chars) for _ in contents]

    store, repo = _FakeStore(), _FakeRepo()
    indexer = EvalVectorIndexer(
        computer=ReceiptComputer(), vector_store=store, corpus_repo=repo, bm25_mode="sqlite_fts5"
    )
    await indexer.index_passages(1, [EvalPassage("pid", content, 10)])
    [row] = repo.rows
    assert row.content == content
    assert row.char_len == len(content)
    assert row.dense_input_chars == row.sparse_input_chars == input_chars


async def test_sql_failure_after_vector_write_cannot_leave_old_completed_receipts(tmp_path, monkeypatch):
    repo = EvalCorpusRepo(url=f"sqlite+aiosqlite:///{tmp_path / 'corpus.sqlite3'}")
    await repo.init_schema()
    store = _FakeStore()
    indexer = EvalVectorIndexer(
        computer=_FakeComputer(), vector_store=store, corpus_repo=repo, bm25_mode="sqlite_fts5"
    )
    passages = _passages(1)
    try:
        await indexer.index_passages(123, passages)
        original_upsert = repo.upsert_chunks

        async def fail_upsert(_):
            raise RuntimeError("SQL提交失败")

        monkeypatch.setattr(repo, "upsert_chunks", fail_upsert)
        with pytest.raises(RuntimeError, match="SQL提交失败"):
            await indexer.index_passages(123, passages)
        assert len(store.upserts) == 2  # 新向量写入已完成，SQL 仍不得保留旧成功标记。
        [row] = await repo.fetch_ingest_rows(123, [eval_chunk_id(123, passages[0].doc_id, 0)])
        assert row.content == passages[0].content
        assert not row.dense_indexed and not row.sparse_indexed and not row.bm25_indexed
        assert row.dense_input_chars is None and row.sparse_input_chars is None
        assert (await repo.summarize_encoding_inputs(dataset_id=123))["completed_rows"] == 0

        monkeypatch.setattr(repo, "upsert_chunks", original_upsert)
        await indexer.index_passages(123, passages)
        await indexer.index_passages(123, passages)
        summary = await repo.summarize_encoding_inputs(dataset_id=123)
        assert summary["total_rows"] == summary["completed_rows"] == 1
        assert summary["both_routes_unchanged"] == 1
        assert summary["affected_status_unknown"] == 0
    finally:
        await close_eval_engines()
