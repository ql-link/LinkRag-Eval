"""Golden V2 synth-corpus tests。"""

from __future__ import annotations

import json

import pytest

from linkrag_eval.golden_v2 import synthesize_corpus_from_spec
from linkrag_eval.store.ids import content_hash, eval_chunk_id


def _write_spec(path) -> None:
    spec = {
        "domains": [
            {
                "domain": "policy",
                "scenarios": ["实名资料更正", "争议复议"],
                "entities": ["真实姓名", "联系地址"],
                "constraints": ["7 个工作日内反馈", "近 30 天无异常争议"],
                "hard_distractors": ["资料长期无法核验", "重复提交同类问题"],
            },
            {
                "domain": "logistics",
                "scenarios": ["包裹清关", "异常催发"],
                "entities": ["补税链接", "物流单号"],
                "constraints": ["3 个工作日内推送", "24 小时内更新"],
                "hard_distractors": ["未在 7 日内支付", "发错货由商家承担"],
            },
        ]
    }
    path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")


def test_synthesize_corpus_from_spec_writes_standard_records(tmp_path) -> None:
    spec = tmp_path / "spec.json"
    _write_spec(spec)

    report = synthesize_corpus_from_spec(
        spec,
        dataset_id=991001,
        target_chunks=5,
        out_dir=tmp_path / "out",
        seed=7,
        batch_id="test-batch",
    )

    assert report.dataset_id == 991001
    assert report.chunks == 5
    rows = [
        json.loads(line)
        for line in (tmp_path / "out" / "chunk_records.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 5
    first = rows[0]
    assert first["dataset_id"] == 991001
    assert first["doc_id"] == 99100100001
    assert first["chunk_id"] == eval_chunk_id(991001, 99100100001, 0)
    assert first["content_hash"] == content_hash(first["content"])
    assert first["metadata"]["generator_batch_id"] == "test-batch"
    saved_report = json.loads((tmp_path / "out" / "synth_report.json").read_text(encoding="utf-8"))
    assert saved_report["chunks"] == 5


def test_synthesize_corpus_from_spec_is_deterministic(tmp_path) -> None:
    spec = tmp_path / "spec.json"
    _write_spec(spec)

    synthesize_corpus_from_spec(spec, dataset_id=991001, target_chunks=3, out_dir=tmp_path / "a", seed=1)
    synthesize_corpus_from_spec(spec, dataset_id=991001, target_chunks=3, out_dir=tmp_path / "b", seed=1)

    assert (tmp_path / "a" / "chunk_records.jsonl").read_text(encoding="utf-8") == (
        tmp_path / "b" / "chunk_records.jsonl"
    ).read_text(encoding="utf-8")


def test_synthesize_corpus_does_not_inject_global_template_clauses(tmp_path) -> None:
    spec = tmp_path / "spec.json"
    _write_spec(spec)

    synthesize_corpus_from_spec(spec, dataset_id=991001, target_chunks=3, out_dir=tmp_path / "out")

    contents = (tmp_path / "out" / "chunk_records.jsonl").read_text(encoding="utf-8")
    assert "状态页展示处理进度" not in contents
    assert "系统只保留最近一次有效记录" not in contents


def test_synthesize_corpus_rejects_bad_spec(tmp_path) -> None:
    spec = tmp_path / "bad.json"
    spec.write_text(json.dumps({"domains": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="spec.domains 为空"):
        synthesize_corpus_from_spec(spec, dataset_id=991001, target_chunks=1, out_dir=tmp_path / "out")
