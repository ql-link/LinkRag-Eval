from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/prepare_grounded_supplement_targets.py"


def _module():
    spec = importlib.util.spec_from_file_location("prepare_grounded_supplements", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_select_targets_balances_and_never_reuses_chunks(tmp_path: Path) -> None:
    module = _module()
    chunks = tmp_path / "chunks.jsonl"
    rows = []
    for dataset_id in (1, 2):
        for index in range(8):
            rows.append(
                {
                    "dataset_id": dataset_id,
                    "doc_id": dataset_id * 100 + index,
                    "chunk_id": f"{dataset_id}-{index}",
                    "content": "足够长的规则正文" * 20,
                    "metadata": {"scenario": f"scenario-{index}"},
                }
            )
    chunks.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )

    selected = module.select_targets(
        [chunks],
        excluded_chunk_ids={"1-0"},
        scenario_counts={"short_keyword": 4, "dense_paraphrase": 2, "long_sparse": 4},
    )

    all_ids = [row["chunk_id"] for scenario_rows in selected.values() for row in scenario_rows]
    assert len(all_ids) == len(set(all_ids)) == 10
    assert "1-0" not in all_ids
    for scenario_rows in selected.values():
        counts = {dataset_id: 0 for dataset_id in (1, 2)}
        for row in scenario_rows:
            counts[row["dataset_id"]] += 1
        assert max(counts.values()) - min(counts.values()) <= 1
