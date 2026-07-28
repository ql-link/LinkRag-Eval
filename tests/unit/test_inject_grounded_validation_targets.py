from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_injects_missing_target_and_preserves_random_negative(tmp_path: Path) -> None:
    seeds = tmp_path / "seeds.jsonl"
    pool = tmp_path / "pool.jsonl"
    chunks = tmp_path / "chunks.jsonl"
    out = tmp_path / "out.jsonl"
    report = tmp_path / "report.json"
    _write(
        seeds,
        [{"query_id": "q1", "target_chunk_id": "target", "target_doc_id": 2}],
    )
    _write(
        pool,
        [
            {
                "query_id": "q1",
                "candidates": [
                    {"chunk_id": "route", "sources": ["dense"]},
                    {"chunk_id": "random", "sources": ["random_neighbor"]},
                ],
            }
        ],
    )
    _write(
        chunks,
        [
            {
                "chunk_id": "target",
                "doc_id": 2,
                "dataset_id": 9,
                "content": "target content",
            }
        ],
    )

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/inject_grounded_validation_targets.py"),
            "--seeds",
            str(seeds),
            "--candidate-pool",
            str(pool),
            "--chunks",
            str(chunks),
            "--out",
            str(out),
            "--report-out",
            str(report),
        ],
        check=True,
    )

    row = json.loads(out.read_text().strip())
    by_id = {candidate["chunk_id"]: candidate for candidate in row["candidates"]}
    assert set(by_id) == {"route", "random", "target"}
    assert "target_chunk_id" not in row
    assert "target_doc_id" not in row
    assert all("sources" not in candidate for candidate in row["candidates"])
    assert json.loads(report.read_text())["injected_targets"] == 1
