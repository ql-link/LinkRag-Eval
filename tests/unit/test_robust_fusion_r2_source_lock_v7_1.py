from __future__ import annotations

import pytest

from linkrag_eval.robust_fusion.r2_source_lock_v7_1 import validate_cross_family_duplicates


def _family(prefix: str, number: int) -> dict[str, str]:
    return {
        "query": f"{prefix} question about capacity {number}?",
        "reference": f"{prefix} reference has capacity {number} and a distinct background sentence.",
        "equivalent_candidate": f"{prefix} reference has capacity {number} and a distinct background sentence!",
        "factual_conflict_candidate": f"{prefix} reference has capacity {number + 1} and a distinct background sentence!",
    }


def test_within_family_template_match_is_allowed() -> None:
    validate_cross_family_duplicates([_family("Alder", 10)])


def test_cross_family_exact_duplicate_is_rejected() -> None:
    first = _family("Alder", 10)
    second = _family("Birch", 20)
    second["query"] = first["query"]
    with pytest.raises(RuntimeError, match="cross-family exact"):
        validate_cross_family_duplicates([first, second])


def test_cross_family_template_duplicate_is_rejected() -> None:
    first = _family("Alder", 10)
    second = _family("Alder", 99)
    with pytest.raises(RuntimeError, match="cross-family template"):
        validate_cross_family_duplicates([first, second])


def test_distinct_cross_family_rows_pass() -> None:
    validate_cross_family_duplicates([_family("Alder", 10), _family("Zephyr", 24)])
