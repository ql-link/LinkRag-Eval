"""collection.tsv / manifest jsonl 读取器:纯解析。"""

from __future__ import annotations

import json

import pytest

from linkrag_eval.golden.corpus_io import load_manifest, read_tsv_collection


def test_read_tsv_collection(tmp_path) -> None:
    p = tmp_path / "c.tsv"
    p.write_text("p1\t正文一\np2\t正文二\n\n", encoding="utf-8")  # 含空行
    corpus = read_tsv_collection(p)
    assert corpus == {"p1": "正文一", "p2": "正文二"}


def test_tsv_duplicate_pid_rejected(tmp_path) -> None:
    p = tmp_path / "c.tsv"
    p.write_text("p1\ta\np1\tb\n", encoding="utf-8")
    with pytest.raises(ValueError, match="pid 重复"):
        read_tsv_collection(p)


def test_load_manifest_filters_fields(tmp_path) -> None:
    p = tmp_path / "m.jsonl"
    p.write_text(
        "\n".join(json.dumps(r) for r in [
            {"source_id": "p1", "doc_id": 991310000, "status": "success"},
            {"source_id": "p2", "doc_id": 991310001, "status": "failed"},
        ]),
        encoding="utf-8",
    )
    recs = load_manifest(p)
    assert [r.source_id for r in recs] == ["p1", "p2"]
    assert recs[0].doc_id == 991310000 and recs[0].status == "success"
    assert recs[1].status == "failed"
