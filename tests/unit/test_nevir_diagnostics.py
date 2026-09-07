"""Synthetic diagnostic and blind-review contracts; no datasets, services or fitted models."""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from linkrag_eval.retrieval.learning_to_rank import nevir_diagnostics as diagnostics
from linkrag_eval.retrieval.learning_to_rank.experiment import build_online_features


def _prepared(pair_count=38):
    prepared, bodies, mapping = [], {}, []
    for pair in range(pair_count):
        cids = [f"PRIVATE-CHUNK-{pair}-{i}" for i in range(3)]
        contents = {cid: f"  Example {pair}, passage {i}.\n" for i, cid in enumerate(cids)}
        for i, cid in enumerate(cids):
            bodies[cid] = {"content": contents[cid], "source": "PRIVATE-BODY-SOURCE"}
            mapping.append({"chunk_id": cid, "source_passage_id": f"PRIVATE-PASSAGE-{pair}-{i}"})
        for direction in range(2):
            query = f"Which statement describes example {pair}, question {direction}?"
            routes = {"dense": [
                {"chunk_id": cid, "doc_id": pair * 3 + i, "dataset_id": 123,
                 "score": 0.9 - i * 0.1, "rank": i}
                for i, cid in enumerate(cids)
            ], "sparse": [], "bm25": []}
            prepared.append({
                "source_query_id": f"PRIVATE-QUERY-{pair}-{direction}",
                "source_group_id": f"PRIVATE-SOURCE-{pair}", "pair_id": f"PRIVATE-PAIR-{pair}",
                "direction": f"q{direction + 1}", "query": query,
                "preferred_chunk_id": cids[direction], "other_chunk_id": cids[1 - direction],
                "contents": contents.copy(), "method_row": {"query": query, "routes": routes},
                "coverage_state": "both", "target_presence": "both", "candidate_count": 3,
                "rank_input_complete": True,
                "route_status": {"dense": "ok", "sparse": "empty", "bm25": "empty"},
                "official_label_available": True, "structural_conflict": False,
                "semantic_uncertain": False, "semantic_review_status": "not_semantically_reviewed",
                "models": {"A": "PRIVATE-MODEL-A", "B": "PRIVATE-MODEL-B"},
            })
    return prepared, bodies, mapping


def _rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _html_payload(html):
    match = re.search(r'<script[^>]*id="review-data"[^>]*>(.*?)</script>', html, re.DOTALL)
    assert match is not None
    return json.loads(match.group(1))


def test_two_review_packets_cover_all_queries_without_private_metadata(tmp_path):
    prepared, bodies, _ = _prepared()
    original = copy.deepcopy(prepared)
    result = diagnostics.make_review_packets(prepared, bodies, tmp_path / "review")
    assert prepared == original
    assert result["packet_counts"] == {"reviewer_1": 76, "reviewer_2": 76}
    assert result["human_reviews_received"] == result["ai_reviews_generated"] == 0
    assert result["status"] == "materials_ready_human_review_pending"
    by_id = {row["source_query_id"]: row for row in prepared}
    query_orders, orientations = [], []
    for reviewer in ("reviewer_1", "reviewer_2"):
        folder = tmp_path / "review" / reviewer
        public = _rows(folder / "cases.jsonl")
        blank = _rows(folder / "blank-answers.jsonl")
        private = _rows(tmp_path / "review/private" / f"{reviewer}-mapping.jsonl")
        html = (folder / "review.html").read_text()
        assert _html_payload(html)["cases"] == public
        assert len(public) == len(blank) == len(private) == 76
        assert {row["source_query_id"] for row in private} == set(by_id)
        assert len({row["case_id"] for row in public}) == 76
        private_by_case = {row["case_id"]: row for row in private}
        query_orders.append([row["source_query_id"] for row in private])
        preferred_sides = {}
        for row in public:
            assert set(row) == {"case_id", "query", "paragraphs"}
            link = private_by_case[row["case_id"]]
            source = by_id[link["source_query_id"]]
            assert row["query"] == source["query"]
            assert {p["display_id"] for p in row["paragraphs"]} == {"X", "Y"}
            for paragraph in row["paragraphs"]:
                assert set(paragraph) == {"display_id", "content"}
                cid = link["display_mapping"][paragraph["display_id"]]
                assert paragraph["content"] == bodies[cid]["content"]
                if cid == source["preferred_chunk_id"]:
                    preferred_sides[link["source_query_id"]] = paragraph["display_id"]
        assert set(preferred_sides.values()) == {"X", "Y"}
        orientations.append(preferred_sides)
        for row in blank:
            assert row["case_id"] in private_by_case
            assert row["reviewer_type"] is row["pair_preference"] is None
            assert row["adjudication_status"] == "待复核"
            assert all(p["applicability"] is None and p["evidence_spans"] == []
                       for p in row["paragraphs"])
        for path in folder.iterdir():
            assert "PRIVATE-" not in path.read_text(), path.name
    assert query_orders[0] != query_orders[1]
    assert orientations[0] != orientations[1]


@pytest.mark.parametrize("source", ["snapshot", "corpus", "unavailable"])
def test_missing_target_body_is_review_only_and_never_changes_prediction_input(tmp_path, source):
    prepared, _, mapping = _prepared(1)
    missing_cid = prepared[0]["other_chunk_id"]
    missing_content = prepared[0]["contents"][missing_cid]
    for row in prepared[:1] if source == "snapshot" else prepared:
        row["contents"].pop(missing_cid)
        row["method_row"]["routes"]["dense"] = [
            hit for hit in row["method_row"]["routes"]["dense"] if hit["chunk_id"] != missing_cid
        ]
    corpus = tmp_path / "synthetic-corpus.jsonl"
    if source == "corpus":
        pid = next(row["source_passage_id"] for row in mapping if row["chunk_id"] == missing_cid)
        corpus.write_text(json.dumps({"source_passage_id": pid, "content": missing_content}) + "\n"
                          + json.dumps({"source_passage_id": "unrelated", "content": "ignore"}) + "\n")
    original = copy.deepcopy(prepared)
    ids_before, x_before = build_online_features(
        **prepared[0]["method_row"], candidate_contents=prepared[0]["contents"])
    bodies = diagnostics._review_bodies(prepared, mapping, corpus)
    result = diagnostics.make_review_packets(prepared, bodies, tmp_path / "review")
    assert prepared == original
    ids_after, x_after = build_online_features(
        **prepared[0]["method_row"], candidate_contents=prepared[0]["contents"])
    assert ids_before == ids_after and missing_cid not in ids_after
    np.testing.assert_array_equal(x_before, x_after)
    assert "unrelated" not in bodies
    if source == "unavailable":
        assert missing_cid not in bodies
        assert result["missing_target_bodies"] == [missing_cid]
    else:
        assert bodies[missing_cid]["content"] == missing_content
        assert bodies[missing_cid]["source"] == (
            "saved_development_candidate_snapshot" if source == "snapshot"
            else "prepared_corpus_review_only")
        assert result["missing_target_bodies"] == []
    for reviewer in ("reviewer_1", "reviewer_2"):
        public = _rows(tmp_path / "review" / reviewer / "cases.jsonl")
        assert len(public) == 2
        assert sum(p["content"] is None for row in public for p in row["paragraphs"]) == (
            2 if source == "unavailable" else 0)


@pytest.mark.parametrize(("left", "right", "expected"), [
    (1.0, 1.0, "tie"), (-0.0, 0.0, "tie"),
    (np.nextafter(1.0, 2.0), 1.0, "correct"),
    (1.0, np.nextafter(1.0, 2.0), "wrong"),
    (np.nextafter(0.0, 1.0), 0.0, "correct"),
    (np.finfo(float).max, -np.finfo(float).max, "correct"),
])
def test_strict_preference_does_not_use_tolerance_or_subtraction(left, right, expected):
    assert diagnostics._relation(left, right) == expected


@pytest.mark.parametrize(("a", "b", "expected"), [
    ("correct", "correct", "both_correct"),
    ("correct", "wrong", "only_a_correct"), ("correct", "tie", "only_a_correct"),
    ("wrong", "correct", "only_b_correct"), ("tie", "correct", "only_b_correct"),
    ("wrong", "wrong", "neither_strictly_correct"),
    ("wrong", "tie", "neither_strictly_correct"),
    ("tie", "wrong", "neither_strictly_correct"),
    ("tie", "tie", "neither_strictly_correct"),
    ("not_evaluable", "correct", "not_evaluable"),
    ("correct", "not_evaluable", "not_evaluable"),
    ("not_evaluable", "not_evaluable", "not_evaluable"),
])
def test_official_four_cells_keep_ties_and_coverage_distinct(a, b, expected):
    assert diagnostics._four_cell(a, b) == expected


def test_html_escapes_raw_text_and_cache_identity_tracks_actual_public_material():
    cases = [{"case_id": "anonymous", "query": "</script><img src=x> 😀",
              "paragraphs": [{"display_id": "X", "content": "  Original.\n"},
                             {"display_id": "Y", "content": None}]}]
    html = diagnostics._review_html("reviewer_1", cases)
    payload = _html_payload(html)
    assert payload["cases"] == cases
    assert "<img src=x>" not in html
    assert len(re.findall(r"[a-f0-9]{64}", payload["storage_key"])) == 1
    assert payload == _html_payload(diagnostics._review_html("reviewer_1", copy.deepcopy(cases)))
    changed = copy.deepcopy(cases)
    changed[0]["paragraphs"][0]["content"] += "Changed."
    assert _html_payload(diagnostics._review_html("reviewer_1", changed))["storage_key"] != payload["storage_key"]
    assert _html_payload(diagnostics._review_html("reviewer_2", cases))["storage_key"] != payload["storage_key"]


_JS_HARNESS = r"""
const fs = require('fs'), vm = require('vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const nodes = {}, storage = {...input.storage};
let exported = null;
const node = id => nodes[id] ||= {value:'',textContent:'',appendChild(){},click(){}};
node('review-data').textContent = JSON.stringify(input.payload);
const context = {
  document:{getElementById:node,createElement:()=>({click(){}})},
  localStorage:{getItem:k=>storage[k] || null,setItem:(k,v)=>{storage[k]=v;}},
  Blob:class {constructor(parts){this.text=parts.join('');}},
  URL:{createObjectURL:blob=>{exported=JSON.parse(blob.text);return 'mock-blob';},revokeObjectURL(){}},
  window:{getSelection(){
    const s=input.selection, textNode={}, container=node(s.side+'-text');
    container.contains=n=>n===textNode;
    const range={startContainer:textNode,endContainer:textNode,startOffset:0,
      toString:()=>s.quote,cloneRange:()=>({selectNodeContents(){},setEnd(){},toString:()=>s.prefix})};
    return {rangeCount:1,getRangeAt:()=>range};
  }}
};
vm.runInNewContext(input.script, context, {timeout:1000});
for (const action of input.actions) {
  if (action.kind==='set') node(action.id).value=action.value;
  else node(action.id).onclick();
}
process.stdout.write(JSON.stringify({exported,storage,
  values:Object.fromEntries(Object.entries(nodes).map(([k,v])=>[k,v.value])),
  notice:node('notice').textContent}));
"""


def _run_review_js(payload, *, storage=None, actions=None, selection=None):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is optional; needed only to execute the standalone review form JavaScript")
    result = subprocess.run([node, "-e", _JS_HARNESS], input=json.dumps({
        "script": diagnostics._REVIEW_JS, "payload": payload, "storage": storage or {},
        "actions": actions or [], "selection": selection,
    }), capture_output=True, text=True, check=True, timeout=10)
    return json.loads(result.stdout)


def _browser_packet():
    cases = [{"case_id": "current-case", "query": "Which statement?",
              "paragraphs": [{"display_id": "X", "content": "A😀B\n"},
                             {"display_id": "Y", "content": "Other."}]}]
    return _html_payload(diagnostics._review_html("reviewer_1", cases))


def test_review_browser_restores_identity_and_exports_only_current_cases():
    payload = _browser_packet()
    current = {"case_id": "current-case", "reviewer_name": "Reviewer", "reviewer_type": "human",
               "pair_preference": "X", "adjudication_status": "独立复核",
               "paragraphs": [{"display_id": "X", "applicability": "支持所问条件",
                               "evidence_spans": [{"quote": "😀", "start": 1, "end": 2}]}]}
    stored = {"reviewer_name": "Reviewer", "reviewer_type": "human",
              "answers": {"current-case": current, "obsolete-case": {"case_id": "obsolete-case"}}}
    result = _run_review_js(payload, storage={payload["storage_key"]: json.dumps(stored)},
                            actions=[{"kind": "click", "id": "download"}])
    exported = result["exported"]
    assert exported["reviewer_name"] == "Reviewer" and exported["reviewer_type"] == "human"
    assert exported["scheduled_cases"] == 1
    assert [row["case_id"] for row in exported["answers"]] == ["current-case"]
    answer = exported["answers"][0]
    assert answer["reviewer_type"] == "human" and answer["reviewer_name"] == "Reviewer"
    assert answer["pair_preference"] == "X"
    assert answer["paragraphs"][0]["evidence_spans"] == [{"quote": "😀", "start": 1, "end": 2}]


def test_review_capture_uses_unicode_code_points_and_evidence_mismatch_blocks_export():
    payload = _browser_packet()
    selection = {"side": "X", "prefix": "A😀", "quote": "B"}
    actions = [{"kind": "click", "id": "X-capture"}, {"kind": "click", "id": "download"}]
    result = _run_review_js(payload, selection=selection, actions=actions)
    assert result["exported"]["answers"][0]["paragraphs"][0]["evidence_spans"] == [
        {"quote": "B", "start": 2, "end": 3}]
    bad = _run_review_js(payload, selection=selection, actions=[
        {"kind": "click", "id": "X-capture"},
        {"kind": "set", "id": "X-start", "value": "3"},
        {"kind": "click", "id": "download"},
    ])
    assert bad["exported"] is None
    assert "证据位置" in bad["notice"]
    assert payload["storage_key"] not in bad["storage"]


def test_review_evidence_end_must_not_exceed_original_text_length():
    payload = _browser_packet()
    result = _run_review_js(payload, actions=[
        {"kind": "set", "id": "X-evidence", "value": "A😀B\n"},
        {"kind": "set", "id": "X-start", "value": "0"},
        {"kind": "set", "id": "X-end", "value": "999"},
        {"kind": "click", "id": "download"},
    ])
    assert result["exported"] is None
    assert "证据位置" in result["notice"]
    assert payload["storage_key"] not in result["storage"]


def test_missing_required_inputs_record_exact_blocker_before_model_loading(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics, "_git", lambda *_: "synthetic-code")
    monkeypatch.setattr(diagnostics, "load_rankers", lambda *_: pytest.fail("model load before input check"))
    out = tmp_path / "diagnostics"
    experiment = tmp_path / "experiment"
    with pytest.raises(FileNotFoundError, match="missing required local input"):
        diagnostics.run_diagnostics(
            experiment_dir=experiment, model_a=tmp_path / "a", model_b=tmp_path / "b",
            saved_b_predictions=tmp_path / "saved-b.jsonl", execution_plan=tmp_path / "plan.md", out=out)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["status"] == manifest["mechanical_status"] == "blocked"
    assert manifest["human_review_status"] == "pending"
    assert manifest["blocker"]["type"] == "FileNotFoundError"
    assert str(experiment / "prepared/development/queries.jsonl") in manifest["blocker"]["detail"]
    assert not (out / "raw-predictions.jsonl").exists()
    assert not (out / "decision.md").exists()


def _mock_run_inputs(tmp_path, monkeypatch):
    prepared, _, _ = _prepared(1)
    experiment, model_a, model_b = tmp_path / "experiment", tmp_path / "a", tmp_path / "b"
    saved_path, plan = tmp_path / "saved-b.jsonl", tmp_path / "plan.md"
    files = [experiment / "prepared/development/queries.jsonl",
             experiment / "prepared/development/supervision.jsonl",
             experiment / "candidates/development/inputs.jsonl",
             experiment / "prepared/passage-mapping.jsonl", model_a / "model.txt", model_b / "model.txt", plan]
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
    saved = []
    for row in prepared:
        ids, _ = build_online_features(**row["method_row"], candidate_contents=row["contents"])
        saved.append({**{k: row[k] for k in ("source_query_id", "source_group_id", "pair_id", "direction",
                                           "official_label_available", "structural_conflict", "semantic_uncertain",
                                           "semantic_review_status", "candidate_count")},
                      "scores": [{"chunk_id": cid, "score": 0.0} for cid in ids],
                      "preference_relation": "tie", "score_difference": 0.0})
    monkeypatch.setattr(diagnostics, "_git", lambda *_: "synthetic-code")
    monkeypatch.setattr(diagnostics, "prepare_inputs", lambda **_: copy.deepcopy(prepared))
    monkeypatch.setattr(diagnostics, "validate_production_bundle", lambda _: {})
    ranker = SimpleNamespace(model=SimpleNamespace(predict=lambda x, **_: np.zeros(len(x))))
    monkeypatch.setattr(diagnostics, "load_rankers", lambda *_: ({"A": ranker, "B": ranker}, {}, {}))
    monkeypatch.setattr(diagnostics, "audit_pair", lambda **_: {
        "verification": {"passed": True, "max_abs_delta_error": 0.0, "max_abs_score_error": 0.0},
        "different_leaf_count": 0,
    })
    return saved, {"experiment_dir": experiment, "model_a": model_a, "model_b": model_b,
                   "saved_b_predictions": saved_path, "execution_plan": plan, "out": tmp_path / "diagnostics"}


@pytest.mark.parametrize(("key", "value", "message"), [
    ("source_group_id", "wrong-source", "supervision association"),
    ("pair_id", "wrong-pair", "supervision association"),
    ("direction", "q2", "supervision association"),
    ("official_label_available", False, "supervision association"),
    ("structural_conflict", True, "supervision association"),
    ("semantic_uncertain", True, "supervision association"),
    ("semantic_review_status", "different-status", "supervision association"),
    ("candidate_count", 2, "supervision association"),
    ("preference_relation", "correct", "preference replay"),
    ("score_difference", float(np.nextafter(0.0, 1.0)), "preference replay"),
])
def test_saved_b_association_and_preference_drift_block_even_with_equal_scores(
    tmp_path, monkeypatch, key, value, message,
):
    saved, kwargs = _mock_run_inputs(tmp_path, monkeypatch)
    saved[0][key] = value
    kwargs["saved_b_predictions"].write_text("".join(json.dumps(row) + "\n" for row in saved))
    with pytest.raises(diagnostics.EvaluationContractError, match=message):
        diagnostics.run_diagnostics(**kwargs)
    manifest = json.loads((kwargs["out"] / "manifest.json").read_text())
    assert manifest["status"] == manifest["mechanical_status"] == "blocked"
    assert message in manifest["blocker"]["detail"]
    assert not (kwargs["out"] / "replay-check.json").exists()


def test_saved_b_summary_mismatch_cannot_be_reported_as_completed(tmp_path, monkeypatch):
    saved, kwargs = _mock_run_inputs(tmp_path, monkeypatch)
    kwargs["saved_b_predictions"].write_text("".join(json.dumps(row) + "\n" for row in saved))
    with pytest.raises(diagnostics.EvaluationContractError, match="47/74 and 11/37"):
        diagnostics.run_diagnostics(**kwargs)
    manifest = json.loads((kwargs["out"] / "manifest.json").read_text())
    assert manifest["status"] == "blocked"
    assert not (kwargs["out"] / "decision.md").exists()
