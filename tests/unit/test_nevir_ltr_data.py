"""NevIR 准备的身份、原文、监督冲突和来源隔离；零活栈。"""

from __future__ import annotations

import copy
import json

import pytest

from linkrag_eval.runners.nevir_ltr_data import (
    build_nevir_ltr_inputs,
    prepare_nevir_ltr,
    read_source_rows,
)
from linkrag_eval.store.ids import eval_chunk_id


def _row(pair_id, q1, q2, doc1, doc2):
    return {"id": pair_id, "WorkerId": "private-worker", "q1": q1, "q2": q2,
            "doc1": doc1, "doc2": doc2}


@pytest.fixture
def data():
    train = [
        _row("619-2", "Same query?", "Same query?", "Original\nbody.", "First variant."),
        _row("619-3", "Who remains?", "Who left?", "Original\nbody.", "Second variant."),
        _row("200-3", "Who may enter?", "Who is blocked?", "May enter.", "Blocked entry."),
    ]
    validation = [
        _row("900-2", "What is hot?", "What is cold?", "Hot subject.", "Cold subject."),
        _row("901-2", "Which is first?", "Which is last?", "First location.", "Last location."),
    ]
    counts = {
        "train": {"official_pair_rows": 3, "query_slots": 6, "source_components": 2},
        "development": {"official_pair_rows": 1, "query_slots": 2, "source_components": 1},
        "confirmation": {"official_pair_rows": 1, "query_slots": 2, "source_components": 1},
    }
    train_development = {
        "status": "suggested_not_consumed", "counts": counts,
        "train_groups": [
            {"component_id": "group-619", "source_prefixes": ["619"], "members": [
                {"pair_id": "619-2", "source_row_index_zero_based": 0,
                 "recommended_loss_eligible": False,
                 "structural_label_conflict": "identical_query_text_opposite_preferences_same_pair"},
                {"pair_id": "619-3", "source_row_index_zero_based": 1,
                 "recommended_loss_eligible": True},
            ]},
            {"component_id": "group-200", "source_prefixes": ["200"], "members": [
                {"pair_id": "200-3", "source_row_index_zero_based": 2,
                 "recommended_loss_eligible": True, "prior_exposure": "direct_text_or_results",
                 "unresolved_label_note": "permission_vs_nonprevention"},
            ]},
        ],
        "development_groups": [
            {"component_id": "group-900", "source_prefixes": ["900"], "members": [
                {"pair_id": "900-2", "source_row_index_zero_based": 0,
                 "prior_exposure": "source_associated"},
            ]},
        ],
    }
    confirmation = {
        "status": "suggested_not_consumed", "counts": copy.deepcopy(counts),
        "not_for_training_consumption": True,
        "confirmation_groups": [
            {"component_id": "group-901", "source_prefixes": ["901"], "members": [
                {"pair_id": "901-2", "source_row_index_zero_based": 1},
            ]},
        ],
    }
    return {
        "train_rows": train, "validation_rows": validation,
        "train_development_proposal": train_development, "confirmation_proposal": confirmation,
        "dataset_id": 995300, "doc_id_base": 9953000000000,
        "qdrant_prefix": "eval_nevir_ltr_20260907", "seed": 20260907,
    }


def test_original_text_identity_and_unlabelled_query_corpus_views(data):
    result = build_nevir_ltr_inputs(**data)
    again = build_nevir_ltr_inputs(**data)
    assert result == again
    assert result["identity"]["corpus_count"] == 9  # Shared doc1 is one independent paragraph.
    bodies = {row["source_passage_id"]: row["content"] for row in result["corpus"]}
    mapping = {row["source_passage_id"]: row for row in result["passage_mapping"]}
    assert len(mapping) == len({row["doc_id"] for row in mapping.values()}) == 9
    for index, row in enumerate(result["passage_mapping"]):
        assert set(row) == {"source_passage_id", "dataset_id", "doc_id", "chunk_id"}
        assert row["doc_id"] == data["doc_id_base"] + index
        assert row["chunk_id"] == eval_chunk_id(data["dataset_id"], row["doc_id"], 0)
    assert all(set(row) == {"source_passage_id", "content"} for row in result["corpus"])
    seen_queries, seen_groups = set(), set()
    source = {row["id"]: row for rows in (data["train_rows"], data["validation_rows"]) for row in rows}
    for role, rows in result["roles"].items():
        queries = {row["source_query_id"]: row["query"] for row in rows["queries"]}
        assert all(set(row) == {"source_query_id", "query"} for row in rows["queries"])
        assert seen_queries.isdisjoint(queries)
        seen_queries.update(queries)
        groups = {row["source_group_id"] for row in rows["supervision"]}
        assert seen_groups.isdisjoint(groups)
        seen_groups.update(groups)
        for supervision in rows["supervision"]:
            original = source[supervision["pair_id"]]
            direction = supervision["direction"]
            assert supervision["role"] == role
            assert queries[supervision["source_query_id"]] == original[direction]
            preferred, other = ("doc1", "doc2") if direction == "q1" else ("doc2", "doc1")
            assert bodies[supervision["preferred_passage_id"]] == original[preferred]
            assert bodies[supervision["other_passage_id"]] == original[other]
            assert supervision["preferred_chunk_id"] == mapping[supervision["preferred_passage_id"]]["chunk_id"]
            assert supervision["other_chunk_id"] == mapping[supervision["other_passage_id"]]["chunk_id"]
            assert supervision["official_label_available"] is True
    assert seen_queries == {f"q{i:06d}" for i in range(10)}
    assert result["isolation"]["cross_role_known_relationships"] == 0
    assert result["isolation"]["test_isolation_proven"] is False


def test_opposing_identical_queries_are_preserved_and_only_the_conflict_is_marked(data):
    result = build_nevir_ltr_inputs(**data)
    rows = result["roles"]["train"]["supervision"]
    conflict = [row for row in rows if row["pair_id"] == "619-2"]
    assert len(conflict) == 2
    assert all(row["structural_conflict"] for row in conflict)
    assert conflict[0]["preferred_chunk_id"] == conflict[1]["other_chunk_id"]
    assert all(not row["structural_conflict"] for row in rows if row["pair_id"] == "619-3")
    assert result["counts"]["train"]["structural_conflict_query_count"] == 2


def test_unknown_semantic_status_is_not_claimed_verified_and_ai_note_is_not_new_label(data):
    result = build_nevir_ltr_inputs(**data)
    for row in result["roles"]["confirmation"]["supervision"]:
        assert row["semantic_review_status"] == "not_semantically_reviewed"
        assert row["semantic_uncertain"] is False
    for row in result["roles"]["train"]["supervision"]:
        if row["pair_id"] == "200-3":
            assert row["semantic_uncertain"] is True
            assert row["semantic_issue_scope"] == "existing_pair_level_note"
            assert row["official_label_available"] is True
            assert not row["structural_conflict"]


@pytest.mark.parametrize("mode", ["body", "exact_query", "normalized_query", "token_multiset"])
def test_rejects_known_cross_role_relationships(data, mode):
    train = data["train_rows"][1]
    heldout = data["validation_rows"][1]
    if mode == "body":
        heldout["doc1"] = train["doc1"]
    elif mode == "exact_query":
        heldout["q1"] = train["q1"]
    elif mode == "normalized_query":
        heldout["q1"] = "WHO REMAINS!!!"
    else:
        heldout["q1"] = "Remains who?"
    with pytest.raises(ValueError, match="known .* relationship"):
        build_nevir_ltr_inputs(**data)


@pytest.mark.parametrize("mode", ["missing", "wrong_index", "duplicate", "loss", "conflict"])
def test_rejects_invalid_split_or_changed_structural_policy(data, mode):
    members = data["train_development_proposal"]["train_groups"][0]["members"]
    if mode == "missing":
        members.pop()
    elif mode == "wrong_index":
        members[0]["source_row_index_zero_based"] = 1
    elif mode == "duplicate":
        members.append(copy.deepcopy(members[0]))
    elif mode == "loss":
        members[0]["recommended_loss_eligible"] = True
    else:
        del members[0]["structural_label_conflict"]
    with pytest.raises(ValueError):
        build_nevir_ltr_inputs(**data)


def test_non_ascii_query_tokens_do_not_cause_spurious_equivalence(data):
    data["train_rows"][1]["q1"] = "誰が残る？"
    data["validation_rows"][1]["q1"] = "先に来るのは誰？"
    build_nevir_ltr_inputs(**data)


def test_confirmation_with_prior_feedback_is_rejected(data):
    member = data["confirmation_proposal"]["confirmation_groups"][0]["members"][0]
    member["prior_exposure"] = "direct_text_or_results"
    with pytest.raises(ValueError, match="prior development exposure"):
        build_nevir_ltr_inputs(**data)


def test_source_reader_never_opens_test_and_preserves_newlines(tmp_path, data):
    path = tmp_path / "train.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in data["train_rows"]) + "\n")
    assert read_source_rows(path) == data["train_rows"]
    with pytest.raises(ValueError, match="only reads"):
        read_source_rows(tmp_path / "test.jsonl")
    path.write_text("\n")
    with pytest.raises(ValueError, match="Blank source row"):
        read_source_rows(path)


def test_preparation_refuses_nonempty_destination_before_reading_sources(tmp_path):
    output = tmp_path / "experiment"
    output.mkdir()
    (output / "keep.json").write_text("original")
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        prepare_nevir_ltr(
            source_dir=tmp_path / "absent", train_development_proposal=tmp_path / "absent1",
            confirmation_proposal=tmp_path / "absent2", output_dir=output,
        )
    assert (output / "keep.json").read_text() == "original"
