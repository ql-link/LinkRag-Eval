"""Synthetic transport/validation tests; none of these are human annotations."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("issue21_prepare", Path(__file__).with_name("prepare.py"))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.fixture
def records():
    return [
        {
            "source_query_id": f"synthetic-{i}", "role": "synthetic_qa",
            "query": "Synthetic fixture only.",
            "paragraphs": {f"a-{i}": "Synthetic text A.", f"b-{i}": "Synthetic text B."},
            "reference_chunk_id": f"a-{i}",
        }
        for i in range(8)
    ]


def final_payload(packet, reviewer):
    payload = MODULE.blank_submission(packet)
    payload.update(
        submission_kind="final", reviewer_name=f"SYNTHETIC_QA_{reviewer}",
        human_confirmed=True, annotation_mode="human_only",
    )
    for case, answer in zip(packet["cases"], payload["answers"], strict=True):
        answer.update(
            status="reviewed", preference=case["reference_preference"],
            primary_type="其他", reason="Synthetic validation fixture; not a human submission.",
        )
    return payload


def test_shuffle_preserves_membership_and_changes_display_mapping(records):
    p1, m1 = MODULE.make_packet(records, 1)
    p2, m2 = MODULE.make_packet(records, 2)
    assert {r["source_query_id"] for r in m1} == {r["source_query_id"] for r in m2}
    assert [r["source_query_id"] for r in m1] != [r["source_query_id"] for r in m2]
    assert {c["case_id"] for c in p1["cases"]}.isdisjoint(c["case_id"] for c in p2["cases"])
    by_qid = {r["source_query_id"]: r for r in records}
    for packet, mapping in ((p1, m1), (p2, m2)):
        for case, m in zip(packet["cases"], mapping, strict=True):
            source = by_qid[m["source_query_id"]]
            assert m["display_mapping"][case["reference_preference"]] == source["reference_chunk_id"]
            for side in ("X", "Y"):
                assert case["paragraphs"][side] == source["paragraphs"][m["display_mapping"][side]]


@pytest.mark.parametrize("problem", [
    "other_packet", "duplicate_id", "missing_case", "unknown_type", "empty_reason",
    "no_attestation", "undeclared_mode", "missing_assistance_notes", "old_schema",
])
def test_rejects_unusable_final_submissions(records, problem):
    packet, _ = MODULE.make_packet(records, 1)
    payload = final_payload(packet, 1)
    if problem == "other_packet":
        payload["packet_id"] = MODULE.make_packet(records, 2)[0]["packet_id"]
    elif problem == "duplicate_id":
        payload["answers"][-1]["case_id"] = payload["answers"][0]["case_id"]
    elif problem == "missing_case":
        payload["answers"].pop()
    elif problem == "unknown_type":
        payload["answers"][0]["primary_type"] = "unsupported label"
    elif problem == "empty_reason":
        payload["answers"][0]["reason"] = " "
    elif problem == "no_attestation":
        payload["human_confirmed"] = False
    elif problem == "undeclared_mode":
        payload["annotation_mode"] = "not_declared"
    elif problem == "missing_assistance_notes":
        payload["annotation_mode"] = "model_assisted"
    elif problem == "old_schema":
        payload["schema_version"] = 1
    with pytest.raises(ValueError):
        MODULE.validate_submission(payload, packet, require_final=True)


def test_draft_and_explicit_uncertainty_are_not_filled_in(records):
    packet, _ = MODULE.make_packet(records, 1)
    blank = MODULE.blank_submission(packet)
    assert MODULE.validate_submission(blank, packet) == {"pending": 8}
    with pytest.raises(ValueError, match="final"):
        MODULE.validate_submission(blank, packet, require_final=True)
    payload = final_payload(packet, 1)
    payload["answers"][0].update(status="uncertain", preference="undetermined", primary_type=None)
    assert MODULE.validate_submission(payload, packet, require_final=True) == {"uncertain": 1, "reviewed": 7}
    assert payload["answers"][0]["primary_type"] is None


def test_receive_normalizes_xy_and_keeps_disagreements(records, tmp_path, monkeypatch):
    monkeypatch.setattr(MODULE, "HERE", tmp_path)
    private = tmp_path / "private"
    private.mkdir()
    MODULE.write_rows(private / "source-cases.jsonl", records)
    paths = []
    for reviewer in (1, 2):
        packet, mapping = MODULE.make_packet(records, reviewer)
        MODULE.write_rows(private / f"reviewer-{reviewer}-mapping.jsonl", mapping)
        payload = final_payload(packet, reviewer)
        if reviewer == 2:
            payload["answers"][0].update(
                status="uncertain", preference="undetermined", primary_type=None,
            )
        path = tmp_path / f"synthetic-qa-{reviewer}.json"
        MODULE.write_json(path, payload)
        paths.append(path)
    out = tmp_path / "synthetic-received"
    MODULE.receive(paths, out)
    receipt = json.loads((out / "receipt.json").read_text())
    assert receipt["paired_cases"] == 8
    assert receipt["both_classified"] == receipt["primary_type_agree"] == 7
    assert receipt["primary_type_agreement_rate"] == 1
    assert receipt["cases_needing_discussion"] == 1
    assert receipt["adjudication_performed"] is False
    assert receipt["original_research_labels_modified"] is False
    assert receipt["human_reviewer_count"] == 2
    assert "independence not established" in receipt["agreement_interpretation"]
    rows = MODULE.read_rows(out / "reviewer-labels.jsonl")
    for row in rows:
        if row["status"] == "reviewed":
            i = row["source_query_id"].split("-")[-1]
            assert row["preferred_chunk_id"] == f"a-{i}"
    with pytest.raises(ValueError, match="already exists"):
        MODULE.receive(paths, out)
    payload2 = json.loads(paths[1].read_text())
    payload2["reviewer_name"] = "SYNTHETIC_QA_1"
    MODULE.write_json(paths[1], payload2)
    with pytest.raises(ValueError, match="distinct"):
        MODULE.receive(paths, tmp_path / "same-person-rejected")
    assert not (tmp_path / "same-person-rejected").exists()


@pytest.mark.parametrize("reviewer", [1, 2])
def test_single_model_assisted_submission_keeps_provenance_without_agreement(
    records, tmp_path, monkeypatch, reviewer,
):
    monkeypatch.setattr(MODULE, "HERE", tmp_path)
    private = tmp_path / "private"
    private.mkdir()
    MODULE.write_rows(private / "source-cases.jsonl", records)
    packet, mapping = MODULE.make_packet(records, reviewer)
    MODULE.write_rows(private / f"reviewer-{reviewer}-mapping.jsonl", mapping)
    payload = final_payload(packet, reviewer)
    payload.update(annotation_mode="model_assisted", assistance_notes="SYNTHETIC MODEL; QA fixture only")
    payload["answers"][0].update(status="uncertain", preference="undetermined", primary_type=None)
    path = tmp_path / "synthetic-assisted.json"
    MODULE.write_json(path, payload)
    paths = [None, None]
    paths[reviewer - 1] = path
    out = tmp_path / "synthetic-received"
    MODULE.receive(paths, out)
    assert json.loads((out / f"reviewer-{reviewer}-original.json").read_text()) == payload
    receipt = json.loads((out / "receipt.json").read_text())
    assert receipt["human_reviewer_count"] == 1
    assert receipt["paired_cases"] == receipt["both_classified"] == 0
    assert receipt["primary_type_agreement_rate"] is None
    assert receipt["agreement_interpretation"] == "unavailable_single_submission"
    assert receipt["cases_needing_discussion"] == receipt["uncertain_judgments"] == 1
    assert MODULE.read_rows(out / "disagreements.jsonl") == []
    rows = MODULE.read_rows(out / "reviewer-labels.jsonl")
    assert len(rows) == 8
    assert all(r["annotation_mode"] == "model_assisted" for r in rows)
    assert all(r["assistance_notes"] == payload["assistance_notes"] for r in rows)
    assert len(MODULE.read_rows(out / "uncertain.jsonl")) == 1
    assert not (out / "labels.jsonl").exists()  # No fabricated consensus/adjudication.
    assert not (out / "independent-labels.jsonl").exists()


def test_receive_needs_at_least_one_submission(tmp_path):
    with pytest.raises(ValueError, match="at least one"):
        MODULE.receive([None, None], tmp_path / "not-created")
    assert not (tmp_path / "not-created").exists()


def test_reviewed_undetermined_is_preserved_as_uncertainty(records, tmp_path, monkeypatch):
    monkeypatch.setattr(MODULE, "HERE", tmp_path)
    (tmp_path / "private").mkdir()
    MODULE.write_rows(tmp_path / "private/source-cases.jsonl", records)
    packet, mapping = MODULE.make_packet(records, 2)
    MODULE.write_rows(tmp_path / "private/reviewer-2-mapping.jsonl", mapping)
    payload = final_payload(packet, 2)
    payload["previous_exposure"] = "yes"
    payload["answers"][0].update(preference="undetermined", primary_type="标签争议")
    payload["answers"][1].update(preference="tie", primary_type="标签争议")
    path = tmp_path / "original.json"
    path.write_bytes((json.dumps(payload, ensure_ascii=False, indent=3) + "\n\n").encode())
    out = tmp_path / "received"
    MODULE.receive([None, path], out)
    assert (out / "reviewer-2-original.json").read_bytes() == path.read_bytes()
    unresolved = MODULE.read_rows(out / "uncertain.jsonl")
    assert len(unresolved) == 1
    assert unresolved[0]["status"] == "reviewed"
    assert unresolved[0]["previous_exposure"] == "yes"
    receipt = json.loads((out / "receipt.json").read_text())
    assert receipt["uncertain_status_judgments"] == 0
    assert receipt["undetermined_preferences"] == receipt["cases_needing_discussion"] == 1
    assert receipt["primary_type_agreement_rate"] is None


def test_receive_rejects_mismatched_display_mapping(records, tmp_path, monkeypatch):
    monkeypatch.setattr(MODULE, "HERE", tmp_path)
    (tmp_path / "private").mkdir()
    MODULE.write_rows(tmp_path / "private/source-cases.jsonl", records)
    packet, mapping = MODULE.make_packet(records, 2)
    mapping[0]["display_mapping"] = dict(reversed(list(mapping[0]["display_mapping"].items())))
    sides = mapping[0]["display_mapping"]
    sides["X"], sides["Y"] = sides["Y"], sides["X"]
    MODULE.write_rows(tmp_path / "private/reviewer-2-mapping.jsonl", mapping)
    path = tmp_path / "original.json"
    MODULE.write_json(path, final_payload(packet, 2))
    with pytest.raises(ValueError, match="display mapping"):
        MODULE.receive([None, path], tmp_path / "not-created")
    assert not (tmp_path / "not-created").exists()


@pytest.mark.parametrize("mode,basis", [
    ("human_only", "single_human_only_confirmed_submission"),
    ("model_assisted", "single_model_assisted_human_confirmed_submission"),
])
def test_analysis_preserves_actual_annotation_mode(records, tmp_path, monkeypatch, mode, basis):
    monkeypatch.setattr(MODULE, "HERE", tmp_path)
    monkeypatch.setitem(sys.modules, "prepare", MODULE)
    spec = importlib.util.spec_from_file_location(
        "issue21_analyze", Path(__file__).with_name("analyze.py"),
    )
    analysis = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(analysis)
    monkeypatch.setattr(analysis, "HERE", tmp_path)
    source = [
        {
            **row, "pair_id": f"synthetic-pair-{i}", "source_group_id": "synthetic-group",
            "reference_basis": "synthetic_fixture",
            "official_preferred_chunk_id": row["reference_chunk_id"],
            "selected_for": [], "model_outcomes": {}, "technical_fallback": {},
        }
        for i, row in enumerate(records)
    ]
    (tmp_path / "private").mkdir()
    MODULE.write_rows(tmp_path / "private/source-cases.jsonl", source)
    packet, mapping = MODULE.make_packet(source, 1)
    MODULE.write_rows(tmp_path / "private/reviewer-1-mapping.jsonl", mapping)
    payload = final_payload(packet, 1)
    payload.update(
        annotation_mode=mode,
        assistance_notes="SYNTHETIC MODEL; QA fixture only" if mode == "model_assisted" else "",
    )
    path = tmp_path / "synthetic-final.json"
    MODULE.write_json(path, payload)
    received = tmp_path / "received"
    MODULE.receive([path, None], received)

    outputs = analysis.build(received)
    labels = [json.loads(line) for line in outputs["labels.jsonl"].splitlines()]
    assert len(labels) == len(source)
    assert {row["annotation_mode"] for row in labels} == {mode}
    assert {row["classification_basis"] for row in labels} == {basis}
    assert json.loads(outputs["summary.json"])["annotation_modes"] == [mode]


def test_untrusted_passage_cannot_close_embedded_json_script(records):
    records[0]["paragraphs"]["a-0"] = "</script><script>unexpected()</script>"
    packet, _ = MODULE.make_packet(records, 1)
    page = MODULE.render(packet)
    assert "</script><script>unexpected()" not in page
    assert "\\u003c/script>" in page
