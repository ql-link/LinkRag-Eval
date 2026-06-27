"""校验 EvalBase ORM 自洽:在内存 SQLite 上建表成功,关键字段到位。

只验 ORM 定义合法(dialect 无关),不连真 Postgres。
"""

from __future__ import annotations

from sqlalchemy import create_engine, inspect

from linkrag_eval.store.models import EvalBase


def _build() -> "inspect":
    engine = create_engine("sqlite://")  # 内存,仅建表
    EvalBase.metadata.create_all(engine)
    return inspect(engine)


def test_six_tables_created() -> None:
    tables = set(_build().get_table_names())
    assert {
        "eval_dataset",
        "eval_corpus_chunk",
        "eval_query",
        "eval_qrel",
        "eval_run",
        "eval_metric_result",
    } <= tables


def test_bm25_rename_and_fingerprint_present() -> None:
    insp = _build()
    chunk_cols = {c["name"] for c in insp.get_columns("eval_corpus_chunk")}
    assert "bm25_indexed" in chunk_cols
    assert "es_indexed" not in chunk_cols  # 已改名
    run_cols = {c["name"] for c in insp.get_columns("eval_run")}
    assert "computer_fingerprint" in run_cols
