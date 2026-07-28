"""Golden V2 Spark corpus export:chunk_records → collection/manifest。"""

from __future__ import annotations

import json

import pytest

from linkrag_eval.golden.corpus_io import load_manifest, read_tsv_collection
from linkrag_eval.golden_v2 import export_spark_corpus
from linkrag_eval.store.ids import content_hash, eval_chunk_id


def _write_chunks(path, rows) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_export_spark_corpus_writes_ingest_inputs(tmp_path) -> None:
    chunks = tmp_path / "chunk_records.jsonl"
    text = "政策 A 的办理时限为 7 个工作日。"
    _write_chunks(
        chunks,
        [
            {
                "dataset_id": 990901,
                "doc_id": 990901001,
                "ordinal": 2,
                "content": text,
                "chunk_id": eval_chunk_id(990901, 990901001, 2),
                "content_hash": content_hash(text),
            }
        ],
    )

    report = export_spark_corpus(
        chunks,
        collection_out=tmp_path / "corpus" / "collection.tsv",
        manifest_out=tmp_path / "corpus" / "manifest.jsonl",
        report_out=tmp_path / "corpus" / "report.json",
        dataset_id=990901,
    )

    assert report.chunks == 1
    assert report.dataset_ids == [990901]
    collection = read_tsv_collection(tmp_path / "corpus" / "collection.tsv")
    assert collection == {"spark-990901-990901001-2": text}
    [manifest] = load_manifest(tmp_path / "corpus" / "manifest.jsonl")
    assert manifest.source_id == "spark-990901-990901001-2"
    assert manifest.doc_id == 990901001
    assert manifest.ordinal == 2
    saved_report = json.loads((tmp_path / "corpus" / "report.json").read_text(encoding="utf-8"))
    assert saved_report["chunks"] == 1


def test_export_spark_corpus_rejects_dataset_mismatch(tmp_path) -> None:
    chunks = tmp_path / "chunk_records.jsonl"
    _write_chunks(
        chunks,
        [{"dataset_id": 1, "doc_id": 2, "ordinal": 0, "content": "正文"}],
    )
    with pytest.raises(ValueError, match="与参数 990901 不一致"):
        export_spark_corpus(
            chunks,
            collection_out=tmp_path / "collection.tsv",
            manifest_out=tmp_path / "manifest.jsonl",
            dataset_id=990901,
        )


def test_export_spark_corpus_uses_source_passage_id_when_present(tmp_path) -> None:
    chunks = tmp_path / "chunk_records.jsonl"
    _write_chunks(
        chunks,
        [
            {
                "dataset_id": 990901,
                "doc_id": 3,
                "ordinal": 0,
                "content": "正文",
                "source_passage_id": "custom-pid",
            }
        ],
    )
    export_spark_corpus(
        chunks,
        collection_out=tmp_path / "collection.tsv",
        manifest_out=tmp_path / "manifest.jsonl",
    )
    assert read_tsv_collection(tmp_path / "collection.tsv") == {"custom-pid": "正文"}
