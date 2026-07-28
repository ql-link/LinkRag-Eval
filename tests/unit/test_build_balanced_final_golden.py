from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "build_balanced_final_golden", ROOT / "scripts/build_balanced_final_golden.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_document_grouped_split_has_exact_sizes_and_no_leakage() -> None:
    rows = [
        {
            "id": f"q-{index:03d}",
            "expected_doc_ids": [index // 2],
        }
        for index in range(150)
    ]
    tune, blind = MODULE._split_by_document(rows, 106)
    assert len(tune) == 106
    assert len(blind) == 44
    tune_docs = {row["expected_doc_ids"][0] for row in tune}
    blind_docs = {row["expected_doc_ids"][0] for row in blind}
    assert not tune_docs & blind_docs


def test_sample_uses_full_20k_dataset_scope() -> None:
    sample = MODULE._sample_from_validation(
        {
            "query_id": "q1",
            "query": "问题",
            "expected_chunk_ids": ["chunk"],
            "expected_doc_ids": [7],
            "type_hint": "short_keyword",
        }
    )
    assert sample["dataset_ids"] == [992000, 992001, 992002, 992003]
    assert sample["expected_chunk_ids"] == ["chunk"]
    assert sample["type"] == "keyword"
