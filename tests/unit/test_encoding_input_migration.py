"""0004 对临时旧库和空库的真实迁移，不接触用户存储。"""

from __future__ import annotations

import sqlite3

import pytest

from linkrag_eval.runners.t2_workflow import migrate_corpus_database


def _legacy_database(path, extra_columns="") -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE eval_corpus_chunk (chunk_id TEXT PRIMARY KEY, content TEXT NOT NULL, "
            f"char_len INTEGER{extra_columns})"
        )
        connection.execute(
            "INSERT INTO eval_corpus_chunk(chunk_id, content, char_len) VALUES ('c1', '  原文🙂  ', 7)"
        )
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES ('0003')")


@pytest.mark.parametrize("already_present", [False, True])
def test_upgrade_keeps_original_content_and_unknown_lengths(tmp_path, already_present):
    path = tmp_path / "legacy.sqlite3"
    columns = ", dense_input_chars INTEGER, sparse_input_chars INTEGER" if already_present else ""
    _legacy_database(path, columns)
    migrate_corpus_database(f"sqlite+aiosqlite:///{path}")
    migrate_corpus_database(f"sqlite+aiosqlite:///{path}")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == ("0004",)
        assert connection.execute(
            "SELECT content, char_len, dense_input_chars, sparse_input_chars FROM eval_corpus_chunk"
        ).fetchone() == ("  原文🙂  ", 7, None, None)
        definitions = {row[1]: row for row in connection.execute("PRAGMA table_info(eval_corpus_chunk)")}
        for name in ("dense_input_chars", "sparse_input_chars"):
            assert definitions[name][2:5] == ("INTEGER", 0, None)


@pytest.mark.parametrize("definition", ["TEXT", "INTEGER NOT NULL DEFAULT 0", "INTEGER DEFAULT 0"])
def test_existing_incompatible_column_is_rejected_before_other_columns_are_added(tmp_path, definition):
    path = tmp_path / "invalid.sqlite3"
    _legacy_database(path, f", dense_input_chars {definition}")
    with pytest.raises(ValueError, match="类型、可空性或默认值不一致"):
        migrate_corpus_database(f"sqlite+aiosqlite:///{path}")
    with sqlite3.connect(path) as connection:
        names = {row[1] for row in connection.execute("PRAGMA table_info(eval_corpus_chunk)")}
        assert "sparse_input_chars" not in names
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == ("0003",)
        assert connection.execute("SELECT content FROM eval_corpus_chunk").fetchone() == ("  原文🙂  ",)


def test_empty_database_current_metadata_and_migration_agree(tmp_path):
    path = tmp_path / "new.sqlite3"
    migrate_corpus_database(f"sqlite+aiosqlite:///{path}")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == ("0004",)
        definitions = {row[1]: row for row in connection.execute("PRAGMA table_info(eval_corpus_chunk)")}
        assert definitions["dense_input_chars"][2:5] == ("INTEGER", 0, None)
        assert definitions["sparse_input_chars"][2:5] == ("INTEGER", 0, None)
