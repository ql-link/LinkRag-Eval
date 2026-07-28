from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "repair_ltr_golden_quality", ROOT / "scripts/repair_ltr_golden_quality.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _row(sample_id: str, query: str, hint: str) -> dict:
    return {
        "id": sample_id,
        "query": query,
        "type": "keyword",
        "note": f"role=blind; type_hint={hint}; independently_validated=true",
    }


def test_repair_demotes_invalid_exact_and_rewrites_unsupported_time() -> None:
    rows, report = MODULE.repair_rows(
        [
            _row("exact", "滞留退运怎么处理", "exact_identifier"),
            _row(
                "blind-v2-20260718-number-time-0042",
                "多次滞留后重打面单，24小时自动退运吗？",
                "number_time",
            ),
        ],
        rewrite_known_blind_queries=True,
    )

    assert "type_hint=short_keyword" in rows[0]["note"]
    assert "24" not in rows[1]["query"]
    assert report["query_rewrites"] == 1
    assert report["remaining_invalid_exact_identifier"] == 0
