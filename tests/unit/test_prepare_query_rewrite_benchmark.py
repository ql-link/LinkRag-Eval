from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts" / "prepare_query_rewrite_benchmark.py"
SPEC = importlib.util.spec_from_file_location("prepare_query_rewrite_benchmark", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _row(index: int, hint: str, *, chunk_count: int = 1) -> dict:
    return {
        "id": f"q-{hint}-{index}",
        "query": f"{hint} query {index}",
        "user_id": 990001,
        "dataset_ids": [992000, 992001, 992002, 992003],
        "expected_chunk_ids": [f"c-{hint}-{index}-{i}" for i in range(chunk_count)],
        "expected_doc_ids": [index],
        "golden_answer": None,
        "type": "keyword" if hint == "keyword" else "paraphrase",
        "note": f"role=realistic; split=tune; type_hint={hint}",
        "relevance_grades": {f"c-{hint}-{index}-0": 3},
    }


def test_smoke_rows_are_balanced_and_single_chunk() -> None:
    rows = [
        _row(index, hint, chunk_count=2 if index == 8 else 1)
        for hint in MODULE.SMOKE_HINTS
        for index in range(9)
    ]

    selected = MODULE._smoke_rows(rows, 8)

    assert len(selected) == 40
    assert all(len(row["expected_chunk_ids"]) == 1 for row in selected)
    counts: dict[str, int] = {}
    for row in selected:
        hint = MODULE._note_field(row, "type_hint")
        counts[hint] = counts.get(hint, 0) + 1
    assert counts == {hint: 8 for hint in MODULE.SMOKE_HINTS}


def test_write_jsonl_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    rows = [_row(1, "keyword")]

    MODULE._write_jsonl(path, rows)

    assert [json.loads(line) for line in path.read_text().splitlines()] == rows
