from __future__ import annotations

from collections import UserDict
from types import SimpleNamespace

import pytest

from linkrag_eval.retrieval.candidate_evidence import (
    ensure_method_view_safe,
    serialize_candidate_response,
)

ROUTES = ("dense", "sparse", "bm25")
CORPUS_IDS = {"chunk-a", "chunk-b", "chunk-c"}


def _response() -> SimpleNamespace:
    return SimpleNamespace(
        failed_sources=[],
        route_hits={
            "dense": [
                SimpleNamespace(chunk_id="chunk-a", score=0.8),
                SimpleNamespace(chunk_id="chunk-b", score=0.7),
            ],
            "sparse": [SimpleNamespace(chunk_id="chunk-b", score=12.5)],
            "bm25": [],
        },
        candidate_hits=[
            SimpleNamespace(chunk_id="chunk-b", doc_id=2, dataset_id=9, fused_score=0.77),
            SimpleNamespace(chunk_id="chunk-a", doc_id=1, dataset_id=9, fused_score=0.66),
        ],
        elapsed_ms=12,
    )


def _serialize(response: SimpleNamespace) -> tuple[list[dict], dict]:
    return serialize_candidate_response(
        query_uid="query-a",
        response=response,
        allowed_chunk_ids=CORPUS_IDS,
        required_routes=ROUTES,
    )


def test_serialization_preserves_evidence_and_projects_only_explicit_fields() -> None:
    response = _response()
    response.metadata = {"target_relation": "evaluation-only"}
    response.per_source_counts = {"dense": 150, "sparse": 50, "bm25": 100}
    response.candidate_hits[0].metadata = {"source_relevance_label": 0}
    response.candidate_hits[0].target_relation = "evaluation-only"
    rows, summary = _serialize(response)

    assert [row["chunk_id"] for row in rows] == ["chunk-b", "chunk-a"]
    assert [row["candidate_rank"] for row in rows] == [1, 2]
    assert rows[0] == {
        "query_uid": "query-a",
        "candidate_rank": 1,
        "chunk_id": "chunk-b",
        "doc_id": 2,
        "dataset_id": 9,
        "fused_score": 0.77,
        "route_evidence": {
            "dense": {"retrieved": True, "rank": 2, "raw_score": 0.7},
            "sparse": {"retrieved": True, "rank": 1, "raw_score": 12.5},
            "bm25": {"retrieved": False, "rank": None, "raw_score": None},
        },
    }
    assert rows[1]["route_evidence"]["dense"]["rank"] == 1
    assert rows[1]["route_evidence"]["sparse"]["raw_score"] is None
    assert summary == {
        "query_uid": "query-a",
        "elapsed_ms": 12,
        "candidate_count": 2,
        "route_hit_counts": {"dense": 2, "sparse": 1, "bm25": 0},
        "failed_sources": [],
    }


def test_present_empty_routes_are_valid() -> None:
    response = _response()
    response.route_hits = {route: [] for route in ROUTES}
    response.candidate_hits = []
    rows, summary = _serialize(response)
    assert rows == []
    assert summary["candidate_count"] == 0


def test_failed_source_is_rejected_even_when_hit_lists_exist() -> None:
    response = _response()
    response.failed_sources = ["dense"]
    with pytest.raises(RuntimeError, match="失败来源"):
        _serialize(response)


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_route_set_must_match_explicit_contract(change: str) -> None:
    response = _response()
    if change == "missing":
        del response.route_hits["bm25"]
    else:
        response.route_hits["other"] = []
    with pytest.raises(RuntimeError, match="路集合不符"):
        _serialize(response)


@pytest.mark.parametrize("location", ["route", "candidate"])
def test_duplicate_ids_are_rejected(location: str) -> None:
    response = _response()
    hits = response.route_hits["dense"] if location == "route" else response.candidate_hits
    hits.append(hits[0])
    with pytest.raises(RuntimeError, match="重复 chunk_id"):
        _serialize(response)


@pytest.mark.parametrize("location", ["route", "candidate"])
def test_out_of_corpus_ids_are_rejected(location: str) -> None:
    response = _response()
    hits = response.route_hits["dense"] if location == "route" else response.candidate_hits
    hits[0].chunk_id = "outside-corpus"
    with pytest.raises(RuntimeError, match="允许语料外"):
        _serialize(response)


@pytest.mark.parametrize("location", ["route", "candidate"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_scores_are_rejected(location: str, value: float) -> None:
    response = _response()
    if location == "route":
        response.route_hits["dense"][0].score = value
    else:
        response.candidate_hits[0].fused_score = value
    with pytest.raises(RuntimeError, match="非有限数"):
        _serialize(response)


@pytest.mark.parametrize("change", ["missing_candidate", "extra_candidate"])
def test_candidate_set_must_equal_route_union(change: str) -> None:
    response = _response()
    if change == "missing_candidate":
        response.candidate_hits.pop()
    else:
        response.candidate_hits.append(
            SimpleNamespace(chunk_id="chunk-c", doc_id=3, dataset_id=9, fused_score=0.1)
        )
    with pytest.raises(RuntimeError, match="并集不一致"):
        _serialize(response)


@pytest.mark.parametrize("routes", [[], ["dense", "dense"], [""], "dense"])
def test_required_routes_must_be_explicit_unique_names(routes) -> None:
    with pytest.raises((TypeError, ValueError), match="required_routes"):
        serialize_candidate_response(
            query_uid="query-a",
            response=_response(),
            allowed_chunk_ids=CORPUS_IDS,
            required_routes=routes,
        )


@pytest.mark.parametrize("field", ["target_relation", "source_relevance_label", "similarity_band"])
def test_nested_evaluation_fields_are_rejected(field: str) -> None:
    with pytest.raises(RuntimeError, match="禁止字段"):
        ensure_method_view_safe([{"nested": (UserDict({field: "hidden"}),)}])


def test_input_guard_accepts_text_without_treating_it_as_a_label() -> None:
    ensure_method_view_safe([{"content": "target_relation is a literal field name in this article"}])
