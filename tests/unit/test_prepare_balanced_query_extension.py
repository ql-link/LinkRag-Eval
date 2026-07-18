from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_prepare_extension_only_keeps_unresolved_unjudged_non_random(tmp_path: Path) -> None:
    pool = tmp_path / "pool.jsonl"
    judgments = tmp_path / "judgments.jsonl"
    out = tmp_path / "out"
    candidates = [
        {"chunk_id": "c1", "sources": ["dense"]},
        {"chunk_id": "c2", "sources": ["sparse"]},
        {"chunk_id": "c3", "sources": ["bm25"]},
        {"chunk_id": "random", "sources": ["random_neighbor"]},
    ]
    _write_jsonl(
        pool,
        [
            {"query_id": "q1", "query": "one", "candidates": candidates},
            {"query_id": "q2", "query": "two", "candidates": candidates},
        ],
    )
    _write_jsonl(
        judgments,
        [
            {"query_id": "q1", "relevant": False, "grade": 0, "candidate": {"chunk_id": "c1"}},
            {"query_id": "q2", "relevant": True, "grade": 3, "candidate": {"chunk_id": "c1"}},
        ],
    )

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/prepare_balanced_query_extension.py"),
            "--candidate-pool",
            str(pool),
            "--judgments",
            str(judgments),
            "--out-dir",
            str(out),
            "--additional-candidates",
            "2",
        ],
        check=True,
    )

    rows = [json.loads(line) for line in (out / "pool_001.jsonl").read_text().splitlines()]
    assert [row["query_id"] for row in rows] == ["q1"]
    assert [candidate["chunk_id"] for candidate in rows[0]["candidates"]] == ["c2", "c3"]
