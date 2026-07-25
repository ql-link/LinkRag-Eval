from __future__ import annotations

from sqlalchemy import create_engine, insert, select

from linkrag_eval.store.database_migration import sync_database
from linkrag_eval.store.models import EvalBase, EvalDatasetDB, EvalQrelDB


def test_sync_database_preserves_rows_and_auto_ids(tmp_path) -> None:
    source_path = tmp_path / "source.sqlite3"
    source = create_engine(f"sqlite:///{source_path}")
    EvalBase.metadata.create_all(source)
    with source.begin() as conn:
        conn.execute(
            insert(EvalDatasetDB),
            [{"dataset_id": 9, "name": "dataset", "source_type": "opensource"}],
        )
        conn.execute(
            insert(EvalQrelDB),
            [
                {
                    "id": 7,
                    "query_id": "q1",
                    "reference_id": "c1",
                    "reference_kind": "chunk",
                    "grade": 2,
                }
            ],
        )
    source.dispose()

    target_path = tmp_path / "target.sqlite3"
    report = sync_database(f"sqlite:///{source_path}", target_path)

    assert report["counts"]["eval_dataset"] == 1
    assert report["counts"]["eval_qrel"] == 1
    target = create_engine(f"sqlite:///{target_path}")
    with target.connect() as conn:
        assert conn.execute(select(EvalQrelDB.id)).scalar_one() == 7
