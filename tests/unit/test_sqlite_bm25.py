"""SQLite FTS5 BM25 后端单测。"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from types import SimpleNamespace

import pytest

from linkrag_eval.compute.protocol import Bm25Tokens
from linkrag_eval.store import sqlite_bm25
from linkrag_eval.store.sqlite_bm25 import (
    SQLiteBm25Point,
    SQLiteBm25Store,
    SQLiteBm25Tokenizer,
    _fts_or_query,
    inspect_sqlite_bm25_identity,
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
    with sqlite3.connect(store.path) as con:
        assert con.execute("SELECT COUNT(*) FROM bm25_fts").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM bm25_chunk_rows").fetchone()[0] == 1


async def test_sqlite_bm25_identity_reports_metadata_without_reading_text(tmp_path, monkeypatch) -> None:
    path = tmp_path / "bm25.sqlite3"
    store = SQLiteBm25Store(path, coarse_weight=2.0, fine_weight=1.0)
    await store.upsert_chunks(
        [
            SQLiteBm25Point(
                chunk_id="c2",
                doc_id=12,
                user_id=990001,
                dataset_id=992001,
                chunk_type="text",
                tokens=Bm25Tokens(coarse="二", fine="二"),
            ),
            SQLiteBm25Point(
                chunk_id="c1",
                doc_id=11,
                user_id=990001,
                dataset_id=992000,
                chunk_type="text",
                tokens=Bm25Tokens(coarse="一", fine="一"),
            ),
        ]
    )

    connect = sqlite3.connect

    def metadata_only_connect(*args, **kwargs):
        con = connect(*args, **kwargs)

        def authorize(action, table, column, database, trigger):
            if action == sqlite3.SQLITE_READ and table == "bm25_fts" and column in {"coarse", "fine"}:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        con.set_authorizer(authorize)
        return con

    monkeypatch.setattr(sqlite_bm25.sqlite3, "connect", metadata_only_connect)
    first = await store.identity()
    second = inspect_sqlite_bm25_identity(path, coarse_weight=2.0, fine_weight=1.0)

    assert first["backend"] == "sqlite_fts5"
    assert first["schema_version"] == 2
    assert first["chunk_count"] == 2
    assert first["dataset_counts"] == {"992000": 1, "992001": 1}
    assert first["path"] == str(path.resolve())
    assert first["coarse_weight"] == 2.0
    assert first["fine_weight"] == 1.0
    assert set(first) == {
        "backend", "path", "exists", "schema_version", "chunk_count", "dataset_counts",
        "coarse_weight", "fine_weight", "file_size",
    }
    assert first == second


def test_sqlite_bm25_identity_reports_missing_sidecar(tmp_path) -> None:
    identity = inspect_sqlite_bm25_identity(tmp_path / "missing.sqlite3")
    assert identity["exists"] is False
    assert identity["chunk_count"] == 0
    assert identity["schema_version"] is None


def _point(chunk_id: str, text: str, *, doc_id: int = 10) -> SQLiteBm25Point:
    return SQLiteBm25Point(
        chunk_id=chunk_id,
        doc_id=doc_id,
        user_id=990001,
        dataset_id=990101,
        chunk_type="text",
        tokens=local_bm25_tokens(text),
    )


async def test_upsert_duplicate_ids_in_one_batch_keeps_last_value(tmp_path) -> None:
    store = SQLiteBm25Store(tmp_path / "bm25.sqlite3")
    await store.upsert_chunks([_point("c1", "old"), _point("c1", "new"), _point("c1", "new")])
    with sqlite3.connect(store.path) as con:
        rows = con.execute(
            "SELECT f.chunk_id, f.coarse FROM bm25_fts f "
            "JOIN bm25_chunk_rows m ON m.fts_rowid = f.rowid AND m.chunk_id = f.chunk_id"
        ).fetchall()
        assert rows == [("c1", "new")]
        assert con.execute("SELECT COUNT(*) FROM bm25_fts").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM bm25_chunk_rows").fetchone()[0] == 1


async def test_v1_upgrade_preserves_rows_and_scores_then_updates_by_id(tmp_path) -> None:
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as con:
        con.executescript(
            """
            CREATE VIRTUAL TABLE bm25_fts USING fts5(
                chunk_id UNINDEXED, doc_id UNINDEXED, user_id UNINDEXED,
                dataset_id UNINDEXED, chunk_type UNINDEXED, coarse, fine,
                tokenize='unicode61'
            );
            CREATE TABLE bm25_meta(version INTEGER NOT NULL);
            INSERT INTO bm25_meta(version) VALUES (1);
            """
        )
        con.executemany(
            "INSERT INTO bm25_fts(rowid, chunk_id, doc_id, user_id, dataset_id, "
            "chunk_type, coarse, fine) VALUES (?, ?, 10, 990001, 990101, 'text', ?, ?)",
            [(7, "c1", "old shared", "old shared"),
             (15, "c1", "old", "old"), (23, "c2", "shared", "shared")],
        )
        before = con.execute("SELECT rowid, * FROM bm25_fts ORDER BY rowid").fetchall()
        scored_before = con.execute(
            "SELECT chunk_id, doc_id, -bm25(bm25_fts, 2, 1) FROM bm25_fts "
            "WHERE bm25_fts MATCH 'shared' AND dataset_id = 990101 "
            "ORDER BY bm25(bm25_fts, 2, 1) ASC"
        ).fetchall()

    store = SQLiteBm25Store(path)
    await store.ensure_collection()
    await store.ensure_collection()  # 再次打开不重复回填。
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT rowid, * FROM bm25_fts ORDER BY rowid").fetchall() == before
        assert con.execute(
            "SELECT fts_rowid, chunk_id FROM bm25_chunk_rows ORDER BY fts_rowid"
        ).fetchall() == [(7, "c1"), (15, "c1"), (23, "c2")]
        assert con.execute("SELECT version FROM bm25_meta").fetchall() == [(2,)]
    hits = await store.recall_topk_chunks(
        SimpleNamespace(dataset_id=990101, doc_id=None, tokens=["shared"], top_k=5)
    )
    assert [(hit.chunk_id, hit.doc_id, hit.score) for hit in hits] == scored_before

    await store.upsert_chunks([_point("c1", "new")])
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT chunk_id FROM bm25_fts ORDER BY rowid").fetchall() == [
            ("c2",), ("c1",)
        ]
        assert con.execute("SELECT rowid, * FROM bm25_fts WHERE rowid = 23").fetchall() == before[-1:]
        assert con.execute("SELECT COUNT(*) FROM bm25_chunk_rows").fetchone()[0] == 2


async def test_existing_upsert_uses_id_index_and_rowid_without_fts_id_scan(tmp_path, monkeypatch) -> None:
    store = SQLiteBm25Store(tmp_path / "bm25.sqlite3")
    await store.upsert_chunks([_point(f"c{i}", f"term{i}") for i in range(64)])
    connect = sqlite3.connect
    statements = []

    def indexed_only_connect(*args, **kwargs):
        con = connect(*args, **kwargs)

        def authorize(action, table, column, database, trigger):
            if action == sqlite3.SQLITE_READ and table == "bm25_fts" and column == "chunk_id":
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        con.set_authorizer(authorize)
        con.set_trace_callback(statements.append)
        return con

    monkeypatch.setattr(sqlite_bm25.sqlite3, "connect", indexed_only_connect)
    await store.upsert_chunks([_point("c32", "replacement")])
    assert "DELETE FROM bm25_fts WHERE rowid = 33" in statements
    with connect(store.path) as con:
        plan = con.execute(
            "EXPLAIN QUERY PLAN SELECT fts_rowid FROM bm25_chunk_rows WHERE chunk_id = ?", ("c32",)
        ).fetchall()
        assert any("USING COVERING INDEX bm25_chunk_rows_chunk_id" in row[3] for row in plan)
        assert con.execute("SELECT COUNT(*) FROM bm25_fts").fetchone()[0] == 64
        assert con.execute("SELECT COUNT(*) FROM bm25_chunk_rows").fetchone()[0] == 64


async def test_failed_upsert_rolls_back_fts_and_id_mapping_together(tmp_path) -> None:
    store = SQLiteBm25Store(tmp_path / "bm25.sqlite3")
    await store.upsert_chunks([_point("c1", "old")])
    with pytest.raises(ValueError):
        await store.upsert_chunks([_point("c1", "new"), _point("c2", "bad", doc_id="invalid")])
    with sqlite3.connect(store.path) as con:
        assert con.execute("SELECT chunk_id, coarse FROM bm25_fts").fetchall() == [("c1", "old")]
        assert con.execute(
            "SELECT m.chunk_id FROM bm25_chunk_rows m JOIN bm25_fts f ON f.rowid = m.fts_rowid"
        ).fetchall() == [("c1",)]


async def test_fetch_indexed_rows_does_not_create_or_upgrade_database(tmp_path) -> None:
    path = tmp_path / "missing" / "bm25.sqlite3"
    store = SQLiteBm25Store(path)
    assert await store.fetch_indexed_rows(dataset_id=990101, chunk_ids=["c1"], user_id=990001) == {}
    assert not path.parent.exists()
    legacy = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(legacy) as con:
        con.execute("CREATE TABLE bm25_meta(version INTEGER NOT NULL)")
        con.execute("INSERT INTO bm25_meta VALUES (1)")
    with pytest.raises(ValueError, match="ensure_collection"):
        await SQLiteBm25Store(legacy).fetch_indexed_rows(
            dataset_id=990101, chunk_ids=["c1"], user_id=990001
        )
    with pytest.raises(ValueError, match="ensure_collection"):
        await SQLiteBm25Store(legacy).verify_dataset_count(
            dataset_id=990101, user_id=990001, expected_count=0
        )
    with sqlite3.connect(legacy) as con:
        assert con.execute("SELECT version FROM bm25_meta").fetchall() == [(1,)]
        assert con.execute(
            "SELECT name FROM sqlite_master WHERE name = 'bm25_chunk_rows'"
        ).fetchall() == []


async def test_fetch_indexed_rows_matches_dataset_user_and_chunk(tmp_path) -> None:
    store = SQLiteBm25Store(tmp_path / "bm25.sqlite3")
    await store.upsert_chunks([
        _point("c1", "target", doc_id=11),
        replace(_point("c2", "foreign dataset"), dataset_id=990102),
        replace(_point("c3", "foreign user"), user_id=990002),
    ])
    with sqlite3.connect(store.path) as con:
        cursor = con.execute(
            "INSERT INTO bm25_fts(chunk_id, doc_id, user_id, dataset_id, chunk_type, coarse, fine) "
            "VALUES ('c1', 99, 990002, 990101, 'text', 'other', 'other')"
        )
        con.execute("INSERT INTO bm25_chunk_rows VALUES (?, 'c1')", (cursor.lastrowid,))
    assert await store.fetch_indexed_rows(
        dataset_id=990101, chunk_ids=["c1", "c2", "c3", "absent", "c1"], user_id=990001
    ) == {"c1": 11}
    assert await store.fetch_indexed_rows(
        dataset_id=990101, chunk_ids=["c1"], user_id=990002
    ) == {"c1": 99}


async def test_fetch_indexed_rows_rejects_ambiguous_doc_ids(tmp_path) -> None:
    store = SQLiteBm25Store(tmp_path / "bm25.sqlite3")
    await store.upsert_chunks([_point("c1", "target")])
    with sqlite3.connect(store.path) as con:
        cursor = con.execute(
            "INSERT INTO bm25_fts(chunk_id, doc_id, user_id, dataset_id, chunk_type, coarse, fine) "
            "VALUES ('c1', 99, 990001, 990101, 'text', 'other', 'other')"
        )
        con.execute("INSERT INTO bm25_chunk_rows VALUES (?, 'c1')", (cursor.lastrowid,))
    with pytest.raises(ValueError, match="多个 doc_id"):
        await store.fetch_indexed_rows(dataset_id=990101, chunk_ids=["c1"], user_id=990001)


async def test_fetch_indexed_rows_batches_ids_and_reads_fts_by_rowid(tmp_path, monkeypatch) -> None:
    store = SQLiteBm25Store(tmp_path / "bm25.sqlite3")
    await store.upsert_chunks([_point(f"c{i}", f"term{i}", doc_id=i) for i in range(300)])
    connect = sqlite3.connect
    statements = []

    def read_only_connect(database, *args, **kwargs):
        assert str(database).endswith("?mode=ro")
        assert kwargs["uri"] is True
        con = connect(database, *args, **kwargs)
        con.set_trace_callback(statements.append)
        return con

    monkeypatch.setattr(sqlite_bm25.sqlite3, "connect", read_only_connect)
    result = await store.fetch_indexed_rows(
        dataset_id=990101, chunk_ids=[f"c{i}" for i in range(300)], user_id=990001
    )
    assert result == {f"c{i}": i for i in range(300)}
    lookups = [sql for sql in statements if "SELECT m.chunk_id, f.doc_id" in sql]
    assert len(lookups) == 2
    with connect(store.path) as con:
        for sql in lookups:
            plan = con.execute("EXPLAIN QUERY PLAN " + sql).fetchall()
            assert any("USING COVERING INDEX bm25_chunk_rows_chunk_id" in row[3] for row in plan)
            assert any("VIRTUAL TABLE INDEX 0:=" in row[3] for row in plan)


async def test_verify_dataset_count_is_read_only_and_does_not_read_text(tmp_path, monkeypatch) -> None:
    store = SQLiteBm25Store(tmp_path / "bm25.sqlite3")
    await store.upsert_chunks([_point("c1", "one"), _point("c2", "two")])
    connect = sqlite3.connect

    def read_only_connect(database, *args, **kwargs):
        assert str(database).endswith("?mode=ro") and kwargs["uri"] is True
        con = connect(database, *args, **kwargs)

        def authorize(action, table, column, database, trigger):
            if action == sqlite3.SQLITE_READ and table == "bm25_fts" and column in {"coarse", "fine"}:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        con.set_authorizer(authorize)
        return con

    monkeypatch.setattr(sqlite_bm25.sqlite3, "connect", read_only_connect)
    assert await store.verify_dataset_count(dataset_id=990101, user_id=990001, expected_count=2) is None


@pytest.mark.parametrize("mutation", [
    "extra_foreign", "wrong_user", "wrong_dataset", "missing_fts",
    "missing_mapping", "wrong_mapping", "orphan_mapping", "wrong_count",
])
async def test_verify_dataset_count_rejects_wrong_scope_or_mapping(tmp_path, mutation) -> None:
    store = SQLiteBm25Store(tmp_path / "bm25.sqlite3")
    await store.upsert_chunks([_point("c1", "one"), _point("c2", "two")])
    with sqlite3.connect(store.path) as con:
        if mutation == "extra_foreign":
            cursor = con.execute(
                "INSERT INTO bm25_fts(chunk_id, doc_id, user_id, dataset_id, chunk_type, coarse, fine) "
                "VALUES ('foreign', 99, 990002, 990101, 'text', 'other', 'other')"
            )
            con.execute("INSERT INTO bm25_chunk_rows VALUES (?, 'foreign')", (cursor.lastrowid,))
        elif mutation == "wrong_user":
            con.execute("UPDATE bm25_fts SET user_id = 990002 WHERE rowid = 1")
        elif mutation == "wrong_dataset":
            con.execute("UPDATE bm25_fts SET dataset_id = 990102 WHERE rowid = 1")
        elif mutation == "missing_fts":
            con.execute("DELETE FROM bm25_fts WHERE rowid = 1")
        elif mutation == "missing_mapping":
            con.execute("DELETE FROM bm25_chunk_rows WHERE fts_rowid = 1")
        elif mutation == "wrong_mapping":
            con.execute("UPDATE bm25_chunk_rows SET chunk_id = 'wrong' WHERE fts_rowid = 1")
        elif mutation == "orphan_mapping":
            con.execute("INSERT INTO bm25_chunk_rows VALUES (999, 'absent')")
    with pytest.raises(ValueError, match="范围核对失败"):
        await store.verify_dataset_count(
            dataset_id=990101, user_id=990001, expected_count=3 if mutation == "wrong_count" else 2
        )


async def test_verify_dataset_count_missing_database_fails_without_creating_it(tmp_path) -> None:
    path = tmp_path / "missing" / "bm25.sqlite3"
    with pytest.raises(FileNotFoundError):
        await SQLiteBm25Store(path).verify_dataset_count(
            dataset_id=990101, user_id=990001, expected_count=0
        )
    assert not path.parent.exists()
