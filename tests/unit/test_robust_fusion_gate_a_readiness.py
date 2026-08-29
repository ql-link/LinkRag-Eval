from __future__ import annotations

from pathlib import Path

from scripts import audit_robust_fusion_gate_a_readiness as readiness

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _build_report() -> dict:
    # The LinkRag-specific git check is intentionally forced to remain blocked in
    # this repository-level regression. The assertions below concern evidence
    # lineage and never authorize Gate A.
    return readiness.build_report(REPOSITORY_ROOT, REPOSITORY_ROOT)


def _check(report: dict, check_id: str) -> dict:
    return next(check for check in report["checks"] if check["check_id"] == check_id)


def test_current_readiness_recognizes_append_only_completed_evidence() -> None:
    report = _build_report()

    expected_passes = {
        "protocol_version_alignment",
        "actual_three_route_preflight",
        "public_data_first_layer_eligibility",
        "internal_v6_governance_skeleton",
        "p2_calibration_input_package",
        "p2_double_annotation_adjudication",
        "non_bge_similarity_encoder_qualification",
        "two_reranker_family_selection",
    }
    expected_blockers = {
        "internal_v6_real_population_and_adjudication",
        "non_bge_similarity_measurement_freeze",
        "clean_dual_repo_contract_lock_and_ci",
        "complete_pre_gate_task_ledger",
        "gate_a_snapshot_preregistration_and_external_timestamp",
    }

    assert report["overall_status"] == "NOT_READY_FOR_GATE_A"
    assert report["summary"] == {
        "check_count": 13,
        "pass_count": 8,
        "blocking_count": 5,
        "blocked_by_kind": {
            "BLOCKED_AUTOMATIC": 2,
            "BLOCKED_HUMAN": 1,
            "BLOCKED_GOVERNANCE": 2,
        },
    }
    assert {
        check["check_id"] for check in report["checks"] if check["status"] == "PASS"
    } == expected_passes
    assert {
        check["check_id"] for check in report["checks"] if check["blocking"]
    } == expected_blockers

    p2 = _check(report, "p2_double_annotation_adjudication")
    assert p2["evidence"]["human_annotator_count"] == 2
    assert p2["evidence"]["model_or_tool_generated_submission_used"] is False
    assert p2["evidence"]["result_status"] == "PASS"

    internal = _check(report, "internal_v6_governance_skeleton")
    assert internal["evidence"]["append_only_lineage_valid"] is True
    assert internal["evidence"]["dev_human_review"] == {
        "verified": True,
        "human_annotator_count": 2,
        "accepted_family_count": 28,
    }


def test_frozen_pre_dev_qualifications_remain_valid_under_current_protocol() -> None:
    report = _build_report()

    for check_id in (
        "public_data_first_layer_eligibility",
        "non_bge_similarity_encoder_qualification",
        "two_reranker_family_selection",
    ):
        check = _check(report, check_id)
        assert check["status"] == "PASS"
        assert check["evidence"]["frozen_under_scientific_protocol"] == (
            readiness.FROZEN_SELECTION_SCIENTIFIC_PROTOCOL
        )
        assert check["evidence"]["current_scientific_protocol"] == (readiness.SCIENTIFIC_PROTOCOL)
        assert check["evidence"]["current_ledger_authorizes_frozen_artifact"] is True


def test_broken_frozen_qualification_requests_restore_not_post_dev_rerun(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        readiness,
        "SIMILARITY_QUALIFICATION_MANIFEST_SHA256",
        "0" * 64,
    )
    report = _build_report()
    check = _check(report, "non_bge_similarity_encoder_qualification")

    assert check["status"] == "BLOCKED_AUTOMATIC"
    assert "Restore the exact outcome-free v3 qualification artifact" in check["next_action"]
    assert "Do not rerun model selection after Dev outcomes" in check["next_action"]


def test_human_annotation_pass_is_bound_to_research_lead_verification(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        readiness,
        "HUMAN_ANNOTATION_VERIFICATION_SHA256",
        "0" * 64,
    )
    report = _build_report()

    assert _check(report, "p2_double_annotation_adjudication")["blocking"] is True
    assert _check(report, "internal_v6_governance_skeleton")["blocking"] is True


def test_checksum_verifier_rejects_empty_and_escaping_manifests(tmp_path: Path) -> None:
    checksum_path = tmp_path / "manifest.sha256"
    checksum_path.write_text("", encoding="utf-8")

    valid, errors = readiness.verify_checksum_file(tmp_path, checksum_path)
    assert valid is False
    assert errors == ["checksum file has no rows"]

    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("outside", encoding="utf-8")
    checksum_path.write_text(
        f"{readiness.sha256_file(outside)}  ../{outside.name}\n",
        encoding="utf-8",
    )

    valid, errors = readiness.verify_checksum_file(tmp_path, checksum_path)
    assert valid is False
    assert errors == [f"path escapes checksum root: ../{outside.name}"]
