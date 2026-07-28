"""Golden V2 builder:judgments → tune/blind golden jsonl。"""

from __future__ import annotations

import json

from linkrag_eval.golden.loader import load_golden
from linkrag_eval.golden_v2 import build_golden_from_judgments


def _write_jsonl(path, rows) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_build_golden_from_judgments_writes_chunk_refs(tmp_path) -> None:
    judgments = tmp_path / "judgments.jsonl"
    _write_jsonl(
        judgments,
        [
            {
                "query_id": "q1",
                "query": "多久办完",
                "role": "realistic",
                "source": "spark_pregen",
                "type_hint": "keyword",
                "candidate": {"chunk_id": "c1", "doc_id": 10, "dataset_id": 990901},
                "relevant": True,
                "grade": 2,
            },
            {
                "query_id": "q1",
                "query": "多久办完",
                "role": "realistic",
                "candidate": {"chunk_id": "c2", "doc_id": 11, "dataset_id": 990901},
                "relevant": False,
                "grade": 0,
            },
            {
                "query_id": "h1",
                "query": "难例",
                "role": "hard",
                "hard_reason": "alias",
                "candidate": {"chunk_id": "hc1", "doc_id": 12, "dataset_id": 990901},
                "relevant": True,
                "grade": 1,
            },
        ],
    )

    report = build_golden_from_judgments(
        [judgments],
        out_dir=tmp_path / "golden",
        user_id=990001,
        tune_ratio=0.5,
    )

    assert report.total_queries == 2
    paths = list((tmp_path / "golden").glob("*_*.jsonl"))
    samples = []
    for path in paths:
        if path.stat().st_size:
            samples.extend(load_golden(path))
    by_id = {s.id: s for s in samples}
    assert by_id["q1"].expected_chunk_ids == ["c1"]
    assert by_id["q1"].expected_doc_ids == [10]
    assert by_id["q1"].relevance_grades == {"c1": 2}
    assert by_id["h1"].expected_chunk_ids == ["hc1"]


def test_build_golden_from_judgments_writes_unresolved(tmp_path) -> None:
    judgments = tmp_path / "judgments.jsonl"
    _write_jsonl(
        judgments,
        [
            {
                "query_id": "q1",
                "query": "无答案",
                "role": "realistic",
                "candidate": {"chunk_id": "c1", "doc_id": 1, "dataset_id": 1},
                "relevant": False,
                "grade": 0,
            }
        ],
    )
    report = build_golden_from_judgments([judgments], out_dir=tmp_path / "golden", user_id=1)
    assert report.unresolved == 1
    unresolved = json.loads((tmp_path / "golden" / "unresolved.jsonl").read_text(encoding="utf-8"))
    assert unresolved["query_id"] == "q1"
