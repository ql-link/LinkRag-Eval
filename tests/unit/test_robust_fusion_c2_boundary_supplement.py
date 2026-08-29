from __future__ import annotations

import csv
import json
import runpy
from pathlib import Path

import pytest

from linkrag_eval.robust_fusion.internal_v6_route_evidence import sha256_file

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_GLOBALS = runpy.run_path(
    str(REPO_ROOT / "scripts/initialize_robust_fusion_c2_boundary_supplement.py")
)
PACKAGE_VERSION = SCRIPT_GLOBALS["PACKAGE_VERSION"]
initialize = SCRIPT_GLOBALS["initialize"]


def _read_rows(path: Path, *, delimiter: str = "\t") -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def test_initialize_c2_supplement_is_empty_dev_only_and_sealed(tmp_path: Path) -> None:
    output = tmp_path / "c2-boundary"
    result = initialize(output)

    assert result["status"] == "INITIALIZED_PLANNED_EMPTY_DEV_ONLY"
    assert result["planned_case_count"] == 8
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["package_version"] == PACKAGE_VERSION
    assert manifest["split_role"] == "internal-v6-dev"
    assert manifest["population_state"] == "PLANNED_EMPTY"
    assert manifest["gate_eligibility"] == "NOT_ELIGIBLE"
    assert manifest["human_annotation_started"] is False
    assert manifest["retrieval_route_evidence_ready"] is False
    assert (
        manifest["materialized_case_count"],
        manifest["materialized_candidate_count"],
        manifest["materialized_pair_count"],
    ) == (0, 0, 0)

    quota_rows = _read_rows(output / "quota_plan.tsv")
    assert len(quota_rows) == 8
    assert {row["target_adjudicability"] for row in quota_rows} == {
        "conditionally_adjudicable",
        "detectable_only",
        "unidentifiable",
    }
    assert _read_rows(output / "case_intake.tsv") == []
    assert _read_rows(output / "candidate_intake.tsv") == []
    assert _read_rows(output / "pair_intake.tsv") == []
    assert _read_rows(output / "annotator_case_template.csv", delimiter=",") == []
    assert _read_rows(output / "annotator_candidate_template.csv", delimiter=",") == []
    assert _read_rows(output / "annotator_pair_template.csv", delimiter=",") == []

    receipt = (output / "manifest.sha256").read_text(encoding="utf-8").split()[0]
    assert receipt == sha256_file(output / "manifest.json")
    assert receipt == result["manifest_sha256"]


def test_initialize_c2_supplement_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "c2-boundary"
    initialize(output)

    with pytest.raises(RuntimeError, match="拒绝覆盖"):
        initialize(output)
