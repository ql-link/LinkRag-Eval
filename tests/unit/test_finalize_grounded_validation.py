from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_finalizes_blinded_decisions_and_accepts_alternate_chunk(tmp_path: Path) -> None:
    seeds = tmp_path / "seeds.jsonl"
    pool = tmp_path / "pool.jsonl"
    decisions = tmp_path / "decisions"
    logs = tmp_path / "logs"
    out = tmp_path / "out"
    _write(
        seeds,
        [
            {
                "query_id": "q1",
                "query": "测试问题",
                "type_hint": "dense_paraphrase",
                "target_chunk_id": "generated-target",
            }
        ],
    )
    _write(
        pool,
        [
            {
                "query_id": "q1",
                "candidates": [
                    {"chunk_id": "alternate", "doc_id": 7, "dataset_id": 9, "content": "答案"}
                ],
            }
        ],
    )
    _write(
        decisions / "decisions_001.jsonl",
        [
            {
                "query_id": "q1",
                "relevant_chunk_id": "alternate",
                "evidence_span": "答案",
                "reason": "完整支持",
                "judge_model": "ignored",
            }
        ],
    )
    logs.mkdir()

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/finalize_grounded_validation.py"),
            "--seeds",
            str(seeds),
            "--pool",
            str(pool),
            "--decisions-dir",
            str(decisions),
            "--spark-log-dir",
            str(logs),
            "--out-dir",
            str(out),
        ],
        check=True,
    )

    sample = json.loads((out / "accepted_samples.jsonl").read_text())
    assert sample["expected_chunk_ids"] == ["alternate"]
    assert sample["generation_target_match"] is False
    report = json.loads((out / "validation_report.json").read_text())
    assert report["accepted"] == 1
    assert report["alternate_canonical_chunks"] == 1
