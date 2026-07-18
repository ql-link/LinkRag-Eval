"""Golden V2 Spark 离线 bundle 导入器:纯文件校验,不连活栈。"""

from __future__ import annotations

import hashlib
import json

import pytest

from linkrag_eval.golden_v2 import import_spark_bundle
from linkrag_eval.store.ids import content_hash, eval_chunk_id


def _write_jsonl(path, rows) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bundle(tmp_path, *, model: str = "gpt-5.3-codex-spark", mutate_hash: bool = False):
    chunk_id = eval_chunk_id(990201, 12003, 3)
    corpus = tmp_path / "corpus_blueprints.jsonl"
    chunks = tmp_path / "chunk_records.jsonl"
    queries = tmp_path / "query_seeds.jsonl"
    hard = tmp_path / "hard_case_seeds.jsonl"

    _write_jsonl(
        corpus,
        [
            {
                "blueprint_id": "spark-corpus-0001",
                "domain": "policy",
                "body": "这是一段可导入评测语料的正文。",
            }
        ],
    )
    _write_jsonl(
        chunks,
        [
            {
                "dataset_id": 990201,
                "doc_id": 12003,
                "ordinal": 3,
                "content": "政策 A 的办理时限为 7 个工作日。",
                "content_hash": content_hash("政策 A 的办理时限为 7 个工作日。"),
                "chunk_id": chunk_id,
            }
        ],
    )
    _write_jsonl(
        queries,
        [
            {
                "seed_id": "spark-query-0001",
                "query": "政策 A 多久能办完",
                "source": "spark_pregen",
                "type_hint": "paraphrase",
                "must_not_contain": ["7 个工作日"],
            }
        ],
    )
    _write_jsonl(
        hard,
        [
            {
                "seed_id": "spark-hard-0001",
                "query": "简称 A 的处理周期和普通事项一样吗",
                "hard_reason": "alias",
            }
        ],
    )
    artifacts = [
        {"kind": "corpus_blueprints", "path": corpus.name, "sha256": _sha(corpus)},
        {"kind": "chunk_records", "path": chunks.name, "sha256": _sha(chunks)},
        {"kind": "query_seeds", "path": queries.name, "sha256": _sha(queries)},
        {"kind": "hard_case_seeds", "path": hard.name, "sha256": _sha(hard)},
    ]
    if mutate_hash:
        artifacts[0]["sha256"] = "0" * 64
    manifest = tmp_path / "bundle_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "eval-offline-batch-v1",
                "batch_id": "batch-test",
                "generator": {"provider": "codex-subagent", "model": model},
                "artifacts": artifacts,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return manifest


def test_import_spark_bundle_writes_normalized_outputs(tmp_path) -> None:
    manifest = _bundle(tmp_path)
    out = tmp_path / "out" / "query_seeds.jsonl"

    report = import_spark_bundle(manifest, out=out)

    assert report.batch_id == "batch-test"
    assert report.generator_model == "gpt-5.3-codex-spark"
    assert report.query_seeds == 1
    assert report.hard_case_seeds == 1
    assert report.chunk_records == 1
    query = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert query["metadata"]["generator_model"] == "gpt-5.3-codex-spark"
    assert query["metadata"]["generator_batch_id"] == "batch-test"
    chunk = json.loads((tmp_path / "out" / "chunk_records.jsonl").read_text(encoding="utf-8"))
    assert chunk["chunk_id"] == eval_chunk_id(990201, 12003, 3)
    assert (tmp_path / "out" / "spark_import_report.json").exists()


def test_import_spark_bundle_rejects_wrong_generator_model(tmp_path) -> None:
    manifest = _bundle(tmp_path, model="deepseek-v4-flash")
    with pytest.raises(ValueError, match="生成模型必须是 gpt-5.3-codex-spark"):
        import_spark_bundle(manifest, out=tmp_path / "out.jsonl")


def test_import_spark_bundle_rejects_hash_mismatch(tmp_path) -> None:
    manifest = _bundle(tmp_path, mutate_hash=True)
    with pytest.raises(ValueError, match="artifact hash 不一致"):
        import_spark_bundle(manifest, out=tmp_path / "out.jsonl")


def test_import_spark_bundle_rejects_bad_chunk_id(tmp_path) -> None:
    manifest = _bundle(tmp_path)
    chunks = tmp_path / "chunk_records.jsonl"
    _write_jsonl(
        chunks,
        [
            {
                "dataset_id": 990201,
                "doc_id": 12003,
                "ordinal": 3,
                "content": "政策 A 的办理时限为 7 个工作日。",
                "chunk_id": "not-the-deterministic-id",
            }
        ],
    )
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for artifact in data["artifacts"]:
        if artifact["kind"] == "chunk_records":
            artifact["sha256"] = _sha(chunks)
    manifest.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="chunk_id 与 uuid5 规则不一致"):
        import_spark_bundle(manifest, out=tmp_path / "out.jsonl")


def test_import_spark_bundle_rejects_answer_leakage(tmp_path) -> None:
    manifest = _bundle(tmp_path)
    queries = tmp_path / "query_seeds.jsonl"
    _write_jsonl(
        queries,
        [
            {
                "seed_id": "spark-query-0001",
                "query": "政策 A 是不是 7 个工作日办完",
                "source": "spark_pregen",
                "must_not_contain": ["7 个工作日"],
            }
        ],
    )
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for artifact in data["artifacts"]:
        if artifact["kind"] == "query_seeds":
            artifact["sha256"] = _sha(queries)
    manifest.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="泄漏答案词"):
        import_spark_bundle(manifest, out=tmp_path / "out.jsonl")
