"""SQLite FTS5 BM25 后端单测。"""

from __future__ import annotations

from types import SimpleNamespace

from linkrag_eval.compute.protocol import Bm25Tokens
from linkrag_eval.store.sqlite_bm25 import (
    SQLiteBm25Point,
    SQLiteBm25Store,
    SQLiteBm25Tokenizer,
    _fts_or_query,
    local_bm25_tokens,
)


def test_fts_or_query_escapes_and_dedupes() -> None:
    assert _fts_or_query(["BM25", "bm25", "检索"]) == '"bm25" OR "检索"'


def test_local_bm25_tokens_and_tokenizer() -> None:
    tokens = local_bm25_tokens("政策 A 7天")
    assert tokens.coarse == "政 策 a 7 天"
    tokenized = SQLiteBm25Tokenizer().tokenize("政策 A")
    assert tokenized.coarse_tokens == "政 策 a"
    assert tokenized.tokens == ["政", "策", "a"]


async def test_sqlite_bm25_upsert_and_search(tmp_path) -> None:
    store = SQLiteBm25Store(tmp_path / "bm25.sqlite3", coarse_weight=2.0, fine_weight=1.0)
    await store.ensure_collection()
    await store.upsert_chunks(
        [
            SQLiteBm25Point(
                chunk_id="c1",
                doc_id=10,
                user_id=990001,
                dataset_id=990101,
                chunk_type="text",
                tokens=Bm25Tokens(coarse="向量 检索 稠密", fine="向量 检索 稠密"),
            ),
            SQLiteBm25Point(
                chunk_id="c2",
                doc_id=11,
                user_id=990001,
                dataset_id=990101,
                chunk_type="text",
                tokens=Bm25Tokens(coarse="BM25 词法 检索", fine="BM25 词法 检索"),
            ),
            SQLiteBm25Point(
                chunk_id="other-dataset",
                doc_id=12,
                user_id=990001,
                dataset_id=990102,
                chunk_type="text",
                tokens=Bm25Tokens(coarse="BM25 检索", fine="BM25 检索"),
            ),
        ]
    )

    hits = await store.recall_topk_chunks(
        SimpleNamespace(dataset_id=990101, doc_id=None, tokens=["BM25", "检索"], top_k=5)
    )
    assert [h.chunk_id for h in hits] == ["c2", "c1"]
    assert all(h.score > 0 for h in hits)

    doc_hits = await store.recall_topk_chunks(
        SimpleNamespace(dataset_id=990101, doc_id=10, tokens=["检索"], top_k=5)
    )
    assert [h.chunk_id for h in doc_hits] == ["c1"]


async def test_sqlite_bm25_upsert_replaces_existing(tmp_path) -> None:
    store = SQLiteBm25Store(tmp_path / "bm25.sqlite3")
    point = SQLiteBm25Point(
        chunk_id="c1",
        doc_id=10,
        user_id=990001,
        dataset_id=990101,
        chunk_type="text",
        tokens=Bm25Tokens(coarse="旧 词", fine="旧 词"),
    )
    await store.upsert_chunks([point])
    await store.upsert_chunks([
        SQLiteBm25Point(
            chunk_id="c1",
            doc_id=10,
            user_id=990001,
            dataset_id=990101,
            chunk_type="text",
            tokens=Bm25Tokens(coarse="新 词", fine="新 词"),
        )
    ])

    old_hits = await store.recall_topk_chunks(
        SimpleNamespace(dataset_id=990101, doc_id=None, tokens=["旧"], top_k=5)
    )
    new_hits = await store.recall_topk_chunks(
        SimpleNamespace(dataset_id=990101, doc_id=None, tokens=["新"], top_k=5)
    )
    assert old_hits == []
    assert [h.chunk_id for h in new_hits] == ["c1"]
