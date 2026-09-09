"""Synthetic packet/receipt checks only; no real human judgments are generated."""
from __future__ import annotations

import copy
import json
import zipfile

import pytest

from linkrag_eval.retrieval.learning_to_rank.nevir_diagnostics import make_review_packets
from linkrag_eval.retrieval.learning_to_rank.review_handoff import (
    PUBLIC_FILES,
    ReviewHandoffError,
    create_handoff,
    disagreement_material,
    read_rows,
    receive_submission,
    validate_existing_packet,
    validate_submission,
)

from .test_nevir_diagnostics import _prepared


@pytest.fixture
def packets(tmp_path):
    prepared, bodies, _ = _prepared(2)
    source = tmp_path / "source"
    make_review_packets(prepared, bodies, source)
    out = tmp_path / "handoff"
    create_handoff(source, prepared, bodies, out)
    return prepared, bodies, source, out


def submission(folder, reviewer, name="Synthetic QA identity"):
    answers = read_rows(folder / reviewer / "blank-answers.jsonl")
    for row in answers:
        row.update(reviewer_name=name, reviewer_type="human", query_ambiguity="no",
                   pair_preference="tie", pair_reason="Synthetic test fixture only.", adjudication_status="独立复核")
        for paragraph in row["paragraphs"]:
            paragraph.update(applicability="相关但证据不足", reason="Synthetic fixture lacks evidence.")
    return {"schema_version": 1, "packet": reviewer, "scheduled_cases": len(answers),
            "exported_at": "2026-09-08T00:00:00Z", "reviewer_name": name,
            "reviewer_type": "human", "answers": answers}


def test_packages_keep_original_bytes_order_and_private_files_out(packets):
    _, _, source, out = packets
    for name in ("reviewer_1", "reviewer_2"):
        with zipfile.ZipFile(out / f"{name}_package.zip") as archive:
            assert set(archive.namelist()) == {f"{name}/{f}" for f in (*PUBLIC_FILES, "README.md")}
            for filename in PUBLIC_FILES:
                assert archive.read(f"{name}/{filename}") == (source / name / filename).read_bytes()
            assert b"PRIVATE-" not in b"".join(archive.read(f) for f in archive.namelist())
    assert (out / "reviewer_1/README.md").read_bytes() == (out / "reviewer_2/README.md").read_bytes()


@pytest.mark.parametrize("mutation", ["query", "order", "mapping", "existing_answer"])
def test_packet_mismatch_refused_without_overwriting(packets, mutation):
    prepared, bodies, source, out = packets
    folder = source / "reviewer_1"
    mapping = source / "private/reviewer_1-mapping.jsonl"
    path = mapping if mutation == "mapping" else folder / ("blank-answers.jsonl" if mutation == "existing_answer" else "cases.jsonl")
    rows = read_rows(path)
    if mutation == "query":
        rows[0]["query"] += " Changed"
    elif mutation == "order":
        rows.reverse()
    elif mutation == "mapping":
        rows[0]["source_group_id"] = "wrong"
    else:
        rows[0]["reviewer_name"] = "existing draft"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    with pytest.raises(ReviewHandoffError):
        validate_existing_packet(folder, mapping, "reviewer_1", prepared, bodies)
    with pytest.raises(ReviewHandoffError, match="overwrite"):
        create_handoff(source, prepared, bodies, out)


def test_intake_checks_ids_missing_fields_and_rejects_ai(packets):
    *_, folder = packets
    cases = read_rows(folder / "reviewer_1/cases.jsonl")
    payload = submission(folder, "reviewer_1")
    assert validate_submission(payload, cases, "reviewer_1")["complete"]
    bad = copy.deepcopy(payload)
    bad["answers"].append(bad["answers"][0])
    assert validate_submission(bad, cases, "reviewer_1")["errors"]
    bad = copy.deepcopy(payload)
    bad["answers"].pop()
    assert len(validate_submission(bad, cases, "reviewer_1")["missing_case_ids"]) == 1
    bad = copy.deepcopy(payload)
    bad["reviewer_type"] = "ai_provisional"
    assert validate_submission(bad, cases, "reviewer_1")["errors"]
    bad = copy.deepcopy(payload)
    bad["answers"][0]["pair_reason"] = ""
    assert validate_submission(bad, cases, "reviewer_1")["incomplete_cases"]


def test_unicode_evidence_uses_codepoints_not_utf16(packets):
    *_, folder = packets
    cases = read_rows(folder / "reviewer_1/cases.jsonl")
    cases[0]["paragraphs"][0]["content"] = "A😀B"
    payload = submission(folder, "reviewer_1")
    p = payload["answers"][0]["paragraphs"][0]
    p["evidence_spans"] = [{"start": 1, "end": 2, "quote": "😀"}]
    assert not validate_submission(payload, cases, "reviewer_1")["errors"]
    p["evidence_spans"][0]["end"] = 3
    assert validate_submission(payload, cases, "reviewer_1")["errors"]


@pytest.mark.parametrize("partial", [False, True])
def test_receive_preserves_bytes_and_aligns_without_gold_or_private_metadata(packets, tmp_path, partial):
    *_, folder = packets
    manifest = folder / "handoff-manifest.json"
    intakes = []
    for i in (1, 2):
        reviewer = f"reviewer_{i}"
        path = tmp_path / f"synthetic-{i}.json"
        payload = submission(folder, reviewer, name=f"Synthetic QA {i}")
        if partial:
            payload["answers"][0].pop("query_ambiguity")
            payload["answers"][0].pop("pair_preference")
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=3))
        dest = tmp_path / f"synthetic-intake-{i}"
        result = receive_submission(path, manifest, reviewer, dest)
        assert result["complete"] is (not partial) and result["human_adjudication"] == "pending"
        assert (dest / "original-submission.json").read_bytes() == path.read_bytes()
        assert (dest / "original-submission.json").stat().st_mode & 0o222 == 0
        with pytest.raises(ReviewHandoffError):
            receive_submission(path, manifest, reviewer, dest)
        intakes.append(dest)
    output = tmp_path / "synthetic-adjudication"
    result = disagreement_material(manifest, *intakes, output)
    assert result["aligned_cases"] == 4
    assert not result["human_judgments_locked"] and not result["models_associated"]
    content = (output / "human-adjudication-cases.json").read_text()
    assert "PRIVATE-" not in content and "official" not in content
    assert all(r["adjudication"]["status"] == "pending" for r in json.loads(content))
    for case in json.loads(content):
        for opinion in case["human_reviews"]:
            assert opinion["original_case_id"]
            assert set(opinion["original_to_canonical_display"]) == {"X", "Y"}
            assert opinion["reason_display_convention"]
            for paragraph in opinion["paragraphs"]:
                assert opinion["original_to_canonical_display"][paragraph["original_display_id"]] == paragraph["display_id"]
    receipt_path = intakes[0] / "receipt.json"
    original_receipt = receipt_path.read_text()
    receipt = json.loads(original_receipt)
    receipt["distribution_zip_sha256"] = "another-distribution"
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ReviewHandoffError, match="another distribution"):
        disagreement_material(manifest, *intakes, tmp_path / "wrong-version")
    receipt_path.write_text(original_receipt)
    (intakes[0] / "normalized.json").write_text("[]")
    with pytest.raises(ReviewHandoffError, match="changed"):
        disagreement_material(manifest, *intakes, tmp_path / "tampered")


def test_malformed_export_is_preserved_with_failure_receipt(packets, tmp_path):
    *_, folder = packets
    path = tmp_path / "broken.json"
    path.write_bytes(b"{not-json")
    out = tmp_path / "broken-intake"
    result = receive_submission(path, folder / "handoff-manifest.json", "reviewer_1", out)
    assert result["errors"] and not result["complete"]
    assert (out / "original-submission.json").read_bytes() == path.read_bytes()


def test_export_with_mismatching_body_version_is_rejected(packets):
    *_, folder = packets
    payload = submission(folder, 'reviewer_1')
    payload['storage_key'] = 'different-body-version'
    cases = read_rows(folder / 'reviewer_1/cases.jsonl')
    result = validate_submission(payload, cases, 'reviewer_1')
    assert result['errors'], 'must not silently accept a newer export from another body version'


def test_paragraph_uncertainty_reaches_human_disagreement_queue(packets, tmp_path):
    *_, folder = packets
    intakes = []
    for i in (1, 2):
        reviewer = f"reviewer_{i}"
        payload = submission(folder, reviewer, name=f"QA ONLY {i}")
        for answer in payload["answers"]:
            answer["pair_preference"] = "X"
            answer["paragraphs"][0]["applicability"] = "无法裁定"
        path = tmp_path / f"uncertain-{i}.json"
        path.write_text(json.dumps(payload))
        intake = tmp_path / f"uncertain-intake-{i}"
        receive_submission(path, folder / "handoff-manifest.json", reviewer, intake)
        intakes.append(intake)
    out = tmp_path / "uncertain-disagreements"
    disagreement_material(folder / "handoff-manifest.json", *intakes, out)
    rows = json.loads((out / "disagreements.json").read_text())
    assert len(rows) == 4
    assert all("uncertainty_or_ambiguity_retained" in r["mechanical_flags"] for r in rows)


def test_partial_review_keeps_available_disagreements_and_uncertainty():
    from linkrag_eval.retrieval.learning_to_rank.review_handoff import comparison_flags

    a = {'incomplete': True, 'pair_preference': 'X', 'query_ambiguity': None,
         'pair_reason_code': None, 'adjudication_status': '独立复核',
         'paragraphs': [{'applicability': '支持所问条件', 'reason_types': []},
                        {'applicability': '相关但证据不足', 'reason_types': ['entity', 'polarity']}]}
    b = copy.deepcopy(a)
    b.update(incomplete=False, pair_preference='undetermined', query_ambiguity='yes', pair_reason_code='other')
    b['paragraphs'][0]['reason_types'] = ['action_relation']
    b['paragraphs'][1]['reason_types'].reverse()
    assert comparison_flags([a, b]) == ['missing_or_incomplete_human_review',
                                        'human_choices_disagree', 'uncertainty_or_ambiguity_retained']


def test_tie_is_not_uncertainty_and_review_status_is_not_semantic_disagreement():
    from linkrag_eval.retrieval.learning_to_rank.review_handoff import comparison_flags

    a = {'incomplete': False, 'pair_preference': 'tie', 'query_ambiguity': 'no',
         'pair_reason_code': 'both_support', 'adjudication_status': '独立复核',
         'paragraphs': [{'applicability': '支持所问条件', 'reason_types': ['entity']}] * 2}
    b = copy.deepcopy(a)
    assert comparison_flags([a, b]) == ['tie_preference_present']
    b.update(adjudication_status='争议保留')
    flags = comparison_flags([a, b])
    assert 'review_status_differs' in flags and 'human_choices_disagree' not in flags
    assert 'uncertainty_or_ambiguity_retained' in flags
