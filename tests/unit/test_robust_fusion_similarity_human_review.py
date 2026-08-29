from __future__ import annotations

import json
from pathlib import Path

import pytest

from linkrag_eval.robust_fusion.similarity_dev_calibration import sha256_file
from scripts.review_robust_fusion_similarity_human_audit import (
    comparison,
    quadratic_weighted_kappa,
    spearman,
    validate_adjudication,
    verify_adjudication_lock,
)


def _row(score: int, *, uncertain: str = "no") -> dict[str, str]:
    return {
        "human_similarity_ordinal": str(score),
        "confidence": "high",
        "uncertain": uncertain,
        "note": "needs review" if uncertain == "yes" else "",
    }


def test_quadratic_weighted_kappa_exact_match() -> None:
    assert quadratic_weighted_kappa([2, 4, 5], [2, 4, 5]) == pytest.approx(1.0)


def test_comparison_includes_uncertain_and_every_nonexact_row() -> None:
    a = {
        "exact": _row(4),
        "uncertain": _row(4, uncertain="yes"),
        "one_apart": _row(4),
    }
    b = {
        "exact": _row(4),
        "uncertain": _row(4),
        "one_apart": _row(5),
    }

    result = comparison(a, b)

    assert result["mandatory_adjudication_ids"] == ["uncertain"]
    assert result["nonexact_ids"] == ["one_apart"]
    assert result["adjudication_ids_for_unique_final_score"] == ["one_apart", "uncertain"]


def test_spearman_uses_average_ranks_for_ordinal_ties() -> None:
    assert spearman([0.1, 0.2, 0.3, 0.4], [1, 2, 2, 5]) > 0.9


def test_adjudication_lock_rejects_content_drift(tmp_path: Path) -> None:
    output_dir = tmp_path / "human_audit/facilitator/adjudication_v1"
    output_dir.mkdir(parents=True)
    adjudication_path = output_dir / "adjudication.csv"
    manifest_path = output_dir / "manifest.json"
    adjudication_path.write_text("audit_id,score\nA,4\n", encoding="utf-8")
    manifest_path.write_text("{}\n", encoding="utf-8")
    lock = {
        "content_read_before_lock": False,
        "adjudication": {
            "relative_path": "adjudication.csv",
            "sha256": sha256_file(adjudication_path),
            "size_bytes": adjudication_path.stat().st_size,
        },
        "package_manifest": {
            "relative_path": "manifest.json",
            "sha256": sha256_file(manifest_path),
        },
    }
    lock_path = output_dir / "adjudication_lock.json"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    (output_dir / "adjudication_lock.sha256").write_text(
        f"{sha256_file(lock_path)}  adjudication_lock.json\n", encoding="utf-8"
    )

    verify_adjudication_lock(tmp_path)
    adjudication_path.write_text("audit_id,score\nA,5\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="locked adjudication drift"):
        verify_adjudication_lock(tmp_path)


def test_adjudication_requires_one_consistent_arbiter(tmp_path: Path) -> None:
    path = tmp_path / "adjudication.csv"
    path.write_text(
        "audit_id,adjudicated_similarity_ordinal,arbiter_id,rationale\n"
        "A,4,arbiter-one,reason one\n"
        "B,3,arbiter-two,reason two\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="one consistent arbiter"):
        validate_adjudication(path, {"A", "B"})
