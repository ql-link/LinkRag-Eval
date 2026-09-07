"""原始 T2 标签连接与覆盖汇总：纯构造数据，不访问模型、数据库或语料。"""

from __future__ import annotations

import json
from copy import deepcopy
from io import StringIO

import pytest

from linkrag_eval.golden.opensource.coverage import (
    join_candidate_qrels,
    summarize_label_coverage,
)
from linkrag_eval.golden.opensource.datasets import parse_t2_qrels


def _qrels(*rows: tuple[str, str, int]):
    return parse_t2_qrels(
        StringIO("qid\t-\tpid\trel\n" + "".join(
            f"{qid}\t0\t{pid}\t{grade}\n" for qid, pid, grade in rows
        ))
    )


def test_join_keeps_four_grades_unknown_and_connection_problems_separate():
    keys = [(7, name) for name in (
        "zero", "one", "two", "three", "unknown", "conflict", "missing", "ambiguous"
    )]
    rows = [(7, name, f"p-{name}") for name in (
        "zero", "one", "two", "three", "unknown", "conflict"
    )] + [(7, "ambiguous", "p-a"), (7, "ambiguous", "p-b")]
    qrels = _qrels(
        ("001", "p-zero", 0), ("001", "p-one", 1),
        ("001", "p-two", 2), ("001", "p-three", 3),
        ("001", "p-conflict", 1), ("001", "p-conflict", 3),
        ("another-query", "p-unknown", 3),
    )
    original = deepcopy((keys, rows, qrels))

    joined = join_candidate_qrels(
        source_query_id="001", candidate_keys=keys, source_rows=iter(rows), qrels=qrels
    )

    assert joined.source_query_id == "001"
    assert joined.candidate_keys == tuple(keys)
    assert joined.grades == {
        (7, "zero"): 0, (7, "one"): 1, (7, "two"): 2, (7, "three"): 3,
    }
    assert joined.issues == {
        (7, "conflict"): "qrel_conflict",
        (7, "missing"): "mapping_missing",
        (7, "ambiguous"): "mapping_ambiguous",
    }
    assert (7, "unknown") not in joined.grades
    assert (7, "unknown") not in joined.issues
    assert (keys, rows, qrels) == original


@pytest.mark.parametrize("source_pid", [None, ""])
def test_absent_source_pid_is_mapping_missing_even_with_qrels(source_pid):
    joined = join_candidate_qrels(
        source_query_id="q", candidate_keys=[(1, "c")],
        source_rows=[(1, "c", source_pid)], qrels=_qrels(("q", "p", 3)),
    )
    assert joined.candidate_keys == ((1, "c"),)
    assert joined.grades == {}
    assert joined.issues == {(1, "c"): "mapping_missing"}


@pytest.mark.parametrize("source_pid", [None, ""])
def test_valid_and_missing_source_rows_cannot_silently_choose_valid_pid(source_pid):
    joined = join_candidate_qrels(
        source_query_id="q", candidate_keys=[(1, "c")],
        source_rows=[(1, "c", "p"), (1, "c", source_pid)],
        qrels=_qrels(("q", "p", 3)),
    )
    assert joined.grades == {}
    assert joined.issues == {(1, "c"): "mapping_ambiguous"}


def test_repeated_identical_mapping_does_not_create_ambiguity():
    joined = join_candidate_qrels(
        source_query_id="q", candidate_keys=[(1, "c")],
        source_rows=[(1, "c", "p"), (1, "c", "p")],
        qrels=_qrels(("q", "p", 0), ("q", "p", 0)),
    )
    assert joined.grades == {(1, "c"): 0}
    assert joined.issues == {}


def test_one_source_passage_cannot_inherit_grade_across_chunks_in_same_dataset():
    joined = join_candidate_qrels(
        source_query_id="q", candidate_keys=[(1, "c-a"), (1, "c-b")],
        source_rows=[(1, "c-a", "p"), (1, "c-b", "p")],
        qrels=_qrels(("q", "p", 2)),
    )
    assert joined.candidate_keys == ((1, "c-a"), (1, "c-b"))
    assert joined.grades == {}
    assert joined.issues == {
        (1, "c-a"): "mapping_ambiguous", (1, "c-b"): "mapping_ambiguous",
    }


def test_same_passage_in_separate_runtime_datasets_can_be_mapped_independently():
    joined = join_candidate_qrels(
        source_query_id="q", candidate_keys=[(1, "c"), (2, "c")],
        source_rows=[(1, "c", "p"), (2, "c", "p")],
        qrels=_qrels(("q", "p", 2)),
    )
    assert joined.grades == {(1, "c"): 2, (2, "c"): 2}
    assert joined.issues == {}


def test_shared_passage_across_queries_does_not_remove_queries_or_change_grades():
    qrels = _qrels(("q-positive", "shared", 3), ("q-zero", "shared", 0))
    joined = [
        join_candidate_qrels(
            source_query_id=qid, candidate_keys=[(1, "c")],
            source_rows=[(1, "c", "shared")], qrels=qrels,
        )
        for qid in ("q-positive", "q-zero", "q-unjudged")
    ]
    assert [row.grades for row in joined] == [{(1, "c"): 3}, {(1, "c"): 0}, {}]
    summary = summarize_label_coverage(joined)
    assert summary["query_count"] == 3
    assert [row["source_query_id"] for row in summary["per_query"]] == [
        "q-positive", "q-zero", "q-unjudged",
    ]
    assert summary["overall"]["pool"]["total"] == 3
    assert summary["overall"]["pool"]["grade_counts"] == {"0": 1, "1": 0, "2": 0, "3": 1}
    assert summary["overall"]["pool"]["unjudged"] == 1


@pytest.mark.parametrize("keys", [
    [(1, "c"), (1, "c")], [(True, "c")], [("1", "c")], [(1.0, "c")],
    [(1, "")], [(1, None)], [(1, 42)], [(1,)],
])
def test_invalid_or_repeated_candidate_keys_are_rejected(keys):
    with pytest.raises(ValueError):
        join_candidate_qrels(
            source_query_id="q", candidate_keys=keys, source_rows=[], qrels=_qrels()
        )


@pytest.fixture
def coverage_queries():
    qrels = _qrels(
        ("q1", "p-zero", 0), ("q1", "p-three", 3),
        ("q1", "p-conflict", 1), ("q1", "p-conflict", 2),
        ("q2", "p-one", 1), ("q2", "p-two", 2),
    )
    first = join_candidate_qrels(
        source_query_id="q1",
        candidate_keys=[(1, name) for name in (
            "zero", "three", "unknown", "missing", "ambiguous", "conflict"
        )],
        source_rows=[
            (1, "zero", "p-zero"), (1, "three", "p-three"),
            (1, "unknown", "p-unknown"), (1, "ambiguous", "p-a"),
            (1, "ambiguous", "p-b"), (1, "conflict", "p-conflict"),
        ], qrels=qrels,
    )
    second = join_candidate_qrels(
        source_query_id="q2", candidate_keys=[(1, "one"), (1, "two"), (1, "unknown")],
        source_rows=[(1, "one", "p-one"), (1, "two", "p-two"), (1, "unknown", "p-unknown")],
        qrels=qrels,
    )
    empty = join_candidate_qrels(
        source_query_id="empty", candidate_keys=[], source_rows=[], qrels=qrels,
    )
    return [first, second, empty]


def test_full_pool_and_explicit_top_k_have_independent_denominators(coverage_queries):
    orders = {
        "q1": [(1, "unknown"), (1, "zero"), (1, "conflict"), (1, "three")],
        "q2": [(1, "two"), (1, "one"), (1, "unknown")],
        "empty": [],
    }
    original = deepcopy((coverage_queries, orders))

    result = summarize_label_coverage(coverage_queries, baseline_orders=orders, k=3)

    assert result["query_count"] == 3
    assert result["k"] == 3
    assert [row["source_query_id"] for row in result["per_query"]] == ["q1", "q2", "empty"]
    first = result["per_query"][0]
    assert first["pool"] == {
        "total": 6, "grade_counts": {"0": 1, "1": 0, "2": 0, "3": 1},
        "judged": 2, "unjudged": 1,
        "issue_counts": {"mapping_missing": 1, "mapping_ambiguous": 1, "qrel_conflict": 1},
        "coverage": pytest.approx(2 / 6),
    }
    assert first["baseline_top_k"] == {
        "total": 3, "grade_counts": {"0": 1, "1": 0, "2": 0, "3": 0},
        "judged": 1, "unjudged": 1,
        "issue_counts": {"mapping_missing": 0, "mapping_ambiguous": 0, "qrel_conflict": 1},
        "coverage": pytest.approx(1 / 3),
    }
    assert result["overall"]["pool"] == {
        "total": 9, "grade_counts": {"0": 1, "1": 1, "2": 1, "3": 1},
        "judged": 4, "unjudged": 2,
        "issue_counts": {"mapping_missing": 1, "mapping_ambiguous": 1, "qrel_conflict": 1},
        "coverage": pytest.approx(4 / 9),
    }
    assert result["overall"]["baseline_top_k"] == {
        "total": 6, "grade_counts": {"0": 1, "1": 1, "2": 1, "3": 0},
        "judged": 3, "unjudged": 2,
        "issue_counts": {"mapping_missing": 0, "mapping_ambiguous": 0, "qrel_conflict": 1},
        "coverage": 0.5,
    }
    for scope in ("pool", "baseline_top_k"):
        assert result["per_query"][2][scope]["total"] == 0
        assert result["per_query"][2][scope]["coverage"] is None
    assert (coverage_queries, orders) == original
    json.dumps(result, allow_nan=False)


def test_omitting_baseline_leaves_top_k_absent_without_removing_empty_query(coverage_queries):
    result = summarize_label_coverage(coverage_queries)
    assert result["k"] is None
    assert result["query_count"] == 3
    assert result["overall"]["baseline_top_k"] is None
    assert all(row["baseline_top_k"] is None for row in result["per_query"])
    assert result["per_query"][2]["pool"]["coverage"] is None


def test_empty_query_collection_has_no_coverage_ratio():
    result = summarize_label_coverage([])
    assert result["query_count"] == 0
    assert result["per_query"] == []
    assert result["overall"]["pool"]["total"] == 0
    assert result["overall"]["pool"]["coverage"] is None


def test_top_k_larger_than_pool_uses_whole_pool(coverage_queries):
    query = coverage_queries[1]
    result = summarize_label_coverage(
        [query], baseline_orders={"q2": [(1, "two"), (1, "unknown"), (1, "one")]}, k=10,
    )
    assert result["per_query"][0]["baseline_top_k"] == result["per_query"][0]["pool"]


@pytest.mark.parametrize("kwargs", [
    {"k": 1}, {"baseline_orders": {"q2": [(1, "one")]}},
    *[{"k": bad, "baseline_orders": {"q2": [(1, "one")]}}
      for bad in (0, -1, True, 1.0, "1")],
])
def test_baseline_and_positive_integer_k_must_be_supplied_together(coverage_queries, kwargs):
    with pytest.raises(ValueError):
        summarize_label_coverage([coverage_queries[1]], **kwargs)


@pytest.mark.parametrize("orders", [
    {},
    {"q2": [(1, "one"), (1, "two")], "unexpected": []},
    {"q2": [(1, "one")]},
    {"q2": [(1, "one"), (1, "one")]},
    {"q2": [(1, "one"), (1, "outside-pool")]},
    {"q2": [(1, "one"), (1, "two"), (1, "one")]},
    {"q2": [(1, "one"), (1, "two"), (1, "outside-pool")]},
])
def test_invalid_baseline_orders_are_rejected_including_beyond_top_k(coverage_queries, orders):
    with pytest.raises(ValueError):
        summarize_label_coverage([coverage_queries[1]], baseline_orders=orders, k=2)


def test_exact_top_k_order_is_sufficient_without_reordering_entire_pool(coverage_queries):
    result = summarize_label_coverage(
        [coverage_queries[1]], baseline_orders={"q2": [(1, "two"), (1, "unknown")]}, k=2,
    )
    top = result["overall"]["baseline_top_k"]
    assert top["total"] == 2
    assert top["grade_counts"] == {"0": 0, "1": 0, "2": 1, "3": 0}
    assert top["coverage"] == 0.5


def test_duplicate_source_query_ids_are_rejected(coverage_queries):
    with pytest.raises(ValueError):
        summarize_label_coverage([coverage_queries[0], coverage_queries[0]])
