"""探索采集仅依赖注入响应和仓储，验证完整候选与缺口均保留。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from linkrag_eval.golden.opensource.coverage import (
    join_candidate_qrels,
    summarize_label_coverage,
)
from linkrag_eval.golden.opensource.datasets import parse_t2_qrels
from linkrag_eval.runners.exploration_input import collect_exploration_input


def hit(cid, score=0.5, *, dataset_id=1, doc_id=10):
    return SimpleNamespace(chunk_id=cid, dataset_id=dataset_id, doc_id=doc_id, score=score)


def response(routes, *, candidates=None, failed=()):
    if candidates is None:
        unique = {}
        for hits in routes.values():
            for h in hits:
                unique.setdefault((h.dataset_id, h.chunk_id), h)
        candidates = list(unique.values())
    return SimpleNamespace(
        route_hits=routes,
        candidate_hits=candidates,
        failed_sources=list(failed),
        hits=candidates[:1],  # 最终融合截断不能收窄交接候选。
    )


def corpus(cid, *, pid=None, content="  原样正文\t内容  ", doc_id=10, ordinal=0):
    return {
        "dataset_id": 1,
        "chunk_id": cid,
        "doc_id": doc_id,
        "content": content,
        "source_passage_id": f"p-{cid}" if pid is None else pid,
        "ordinal": ordinal,
    }


async def collect(resp, rows):
    async def execute(**kwargs):
        assert kwargs == {"query": " 原样问题？ ", "dataset_ids": [1]}
        return resp

    async def fetch(keys):
        return rows

    return await collect_exploration_input(
        source_query_id="001",
        query=" 原样问题？ ",
        dataset_ids=[1],
        execute_candidates=execute,
        fetch_candidate_rows=fetch,
    )


async def test_unlabelled_query_preserves_full_routes_scores_ties_and_contents():
    a, b, c = hit("a", 0.8), hit("b", 0.8), hit("c", 9.25, doc_id=12)
    resp = response({"dense": [b, a], "sparse": [a, c], "bm25": []})
    result = await collect(resp, [corpus("a"), corpus("b"), corpus("c", doc_id=12)])

    assert result["status"] == "ready"
    assert result["ranking_input_ready"] is True
    assert result["sample_id"] == result["source_query_id"] == "001"
    assert result["query"] == " 原样问题？ "
    assert [(r["chunk_id"], r["score"], r["rank"]) for r in result["routes"]["dense"]] == [
        ("b", 0.8, 0),
        ("a", 0.8, 1),
    ]
    assert [r["chunk_id"] for r in result["candidate_rows"]] == ["b", "a", "c"]
    assert all(r["content"] == "  原样正文\t内容  " for r in result["candidate_rows"])
    assert result["candidate_rows"][2]["doc_id"] == 12
    assert result["route_status"] == {"dense": "ok", "sparse": "ok", "bm25": "empty"}
    assert result["input_issues"] == []
    assert all("score" not in row and "rank" not in row for row in result["candidate_rows"])
    assert "expected_" not in json.dumps(result, ensure_ascii=False, allow_nan=False)


async def test_successful_empty_pool_is_distinct_from_failed_or_missing_route():
    empty = {"dense": [], "sparse": [], "bm25": []}
    empty_result = await collect(response(empty), [])
    assert empty_result["status"] == "empty"
    assert empty_result["ranking_input_ready"] is True
    failed = await collect(response(empty, failed=["sparse"]), [])
    assert failed["status"] == "incomplete"
    assert failed["ranking_input_ready"] is False
    assert failed["route_status"]["sparse"] == "failed"
    missing = await collect(response({"dense": [], "sparse": []}), [])
    assert missing["status"] == "incomplete"
    assert missing["ranking_input_ready"] is False
    assert missing["route_status"]["bm25"] == "missing"


async def test_request_exception_retains_query_without_leaking_message_or_retrying():
    calls = []

    async def execute(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("secret-url-or-body")

    async def fetch(keys):
        pytest.fail("failed request must not fetch corpus")

    result = await collect_exploration_input(
        source_query_id="q",
        sample_id="runtime-q",
        query="问",
        dataset_ids=[1],
        execute_candidates=execute,
        fetch_candidate_rows=fetch,
    )
    assert len(calls) == 1
    assert result["status"] == "failed"
    assert result["ranking_input_ready"] is False
    assert result["sample_id"] == "runtime-q"
    assert result["failed_sources"] == []  # 整请求异常无法据此归因到特定一路。
    assert set(result["route_status"].values()) == {"unavailable"}
    assert result["input_issues"] == [
        {"code": "candidate_execution_failed", "error_type": "RuntimeError"},
    ]
    assert "secret" not in json.dumps(result)


async def test_missing_body_source_and_row_do_not_drop_candidates_or_route_doc_id():
    resp = response({"dense": [hit("a"), hit("b"), hit("c")], "sparse": [], "bm25": []})
    result = await collect(resp, [corpus("a", content="", doc_id=999), corpus("b", pid="")])
    assert result["status"] == "incomplete"
    assert result["ranking_input_ready"] is False
    assert [r["chunk_id"] for r in result["candidate_rows"]] == ["a", "b", "c"]
    assert result["candidate_rows"][0]["content"] == ""
    assert result["candidate_rows"][0]["doc_id"] == 10
    assert result["candidate_rows"][2]["content"] is None
    assert {i["code"] for i in result["input_issues"]} == {
        "missing_content",
        "missing_source_passage_id",
        "missing_corpus_row",
        "corpus_doc_id_mismatch",
    }


async def test_pool_mismatch_keeps_candidates_from_both_views():
    resp = response({"dense": [hit("route")], "sparse": [], "bm25": []}, candidates=[hit("pool")])
    result = await collect(resp, [corpus("pool"), corpus("route")])
    assert result["status"] == "incomplete"
    assert result["ranking_input_ready"] is False
    assert {r["chunk_id"] for r in result["candidate_rows"]} == {"pool", "route"}
    assert result["input_issues"] == [
        {
            "code": "candidate_pool_mismatch",
            "route_only": [[1, "route"]],
            "candidate_only": [[1, "pool"]],
        },
    ]


async def test_mapping_ambiguity_never_leaves_one_apparently_valid_source_relation():
    resp = response({"dense": [hit("a"), hit("b"), hit("c")], "sparse": [], "bm25": []})
    result = await collect(
        resp, [corpus("a", pid="shared"), corpus("b", pid="shared"), corpus("c", ordinal=1)]
    )
    assert result["status"] == "incomplete"
    assert result["ranking_input_ready"] is True
    assert all(r["source_passage_id"] is None for r in result["candidate_rows"])
    assert result["source_rows"] == [
        [1, "a", "shared"],
        [1, "a", None],
        [1, "b", "shared"],
        [1, "b", None],
        [1, "c", "p-c"],
        [1, "c", None],
    ]


async def test_conflicting_corpus_rows_preserve_both_source_relations():
    resp = response({"dense": [hit("a")], "sparse": [], "bm25": []})
    result = await collect(resp, [corpus("a", pid="p1"), corpus("a", pid="p2")])
    assert result["candidate_rows"][0]["source_passage_id"] is None
    assert result["ranking_input_ready"] is True
    assert result["candidate_rows"][0]["content"] == "  原样正文\t内容  "
    assert result["source_rows"] == [[1, "a", None], [1, "a", "p1"], [1, "a", "p2"]]


async def test_unexpected_dataset_is_recorded_but_its_content_is_not_fetched():
    resp = response({"dense": [hit("x", dataset_id=2)], "sparse": [], "bm25": []})

    async def execute(**kwargs):
        return resp

    async def fetch(keys):
        pytest.fail("out-of-scope dataset must not be read")

    result = await collect_exploration_input(
        source_query_id="q",
        query="问",
        dataset_ids=[1],
        execute_candidates=execute,
        fetch_candidate_rows=fetch,
    )
    assert result["candidate_rows"][0]["chunk_id"] == "x"
    assert result["status"] == "incomplete"
    assert result["ranking_input_ready"] is False
    assert result["input_issues"] == [
        {"code": "unexpected_dataset", "dataset_id": 2, "chunk_id": "x"}
    ]


async def test_corpus_exception_preserves_candidate_keys():
    async def execute(**kwargs):
        return response({"dense": [hit("a")], "sparse": [], "bm25": []})

    async def fetch(keys):
        assert keys == [(1, "a")]
        raise OSError("private-detail")

    result = await collect_exploration_input(
        source_query_id="q",
        query="问",
        dataset_ids=[1],
        execute_candidates=execute,
        fetch_candidate_rows=fetch,
    )
    assert result["status"] == "incomplete"
    assert result["ranking_input_ready"] is False
    assert result["candidate_rows"][0]["chunk_id"] == "a"
    assert "private-detail" not in json.dumps(result)


async def test_no_scope_is_rejected_before_retrieval():
    with pytest.raises(ValueError, match="dataset_ids"):
        await collect_exploration_input(
            source_query_id="q",
            query="问",
            dataset_ids=[],
            execute_candidates=None,
            fetch_candidate_rows=None,
        )


async def test_missing_ordinal_preserves_ranking_input_and_unresolved_mapping():
    resp = response({"dense": [hit("a")], "sparse": [], "bm25": []})
    row = corpus("a")
    del row["ordinal"]
    result = await collect(resp, [row])
    assert result["status"] == "incomplete"
    assert result["ranking_input_ready"] is True
    assert result["source_query_id"] == "001"
    assert result["candidate_rows"][0]["chunk_id"] == "a"
    assert result["candidate_rows"][0]["content"] == "  原样正文\t内容  "
    assert result["source_rows"] == [[1, "a", "p-a"], [1, "a", None]]
    assert result["input_issues"][0] == {
        "code": "missing_source_fields",
        "dataset_id": 1,
        "chunk_id": "a",
        "missing_fields": ["ordinal"],
    }


@pytest.mark.parametrize("pid", [" p1", "p 1", "p1\t"])
async def test_invalid_source_id_is_not_normalized_or_sent_to_label_join(pid):
    resp = response({"dense": [hit("a")], "sparse": [], "bm25": []})
    result = await collect(resp, [corpus("a", pid=pid)])
    assert result["status"] == "incomplete"
    assert result["ranking_input_ready"] is True
    assert result["source_rows"] == [[1, "a", None]]
    assert result["candidate_rows"][0]["source_passage_id"] is None
    assert result["input_issues"] == [
        {
            "code": "invalid_source_passage_id",
            "source_passage_id": pid,
            "dataset_id": 1,
            "chunk_id": "a",
        },
    ]


async def test_conflicting_rows_with_invalid_pid_keep_only_valid_join_relations():
    resp = response({"dense": [hit("a")], "sparse": [], "bm25": []})
    result = await collect(resp, [corpus("a", pid="p1"), corpus("a", pid=" p2")])
    assert result["source_rows"] == [[1, "a", None], [1, "a", "p1"]]
    assert result["input_issues"][1]["source_passage_id"] == " p2"


async def test_runner_ambiguous_source_rows_join_without_assigning_available_qrels():
    resp = response(
        {
            "dense": [hit("a"), hit("b"), hit("split"), hit("valid")],
            "sparse": [],
            "bm25": [],
        }
    )
    result = await collect(
        resp,
        [
            corpus("a", pid="shared"),
            corpus("b", pid="shared"),
            corpus("split", ordinal=1),
            corpus("valid"),
        ],
    )
    keys = [(row["dataset_id"], row["chunk_id"]) for row in result["candidate_rows"]]
    assert result["ranking_input_ready"] is True
    qrels = parse_t2_qrels(
        [
            "001\t0\tshared\t3\n",
            "001\t0\tp-split\t2\n",
            "001\t0\tp-valid\t0\n",
        ]
    )

    joined = join_candidate_qrels(
        source_query_id=result["source_query_id"],
        candidate_keys=keys,
        source_rows=result["source_rows"],
        qrels=qrels,
    )

    assert joined.candidate_keys == tuple(keys)
    assert joined.grades == {(1, "valid"): 0}
    assert joined.issues == {
        (1, "a"): "mapping_ambiguous",
        (1, "b"): "mapping_ambiguous",
        (1, "split"): "mapping_ambiguous",
    }
    pool = summarize_label_coverage([joined])["overall"]["pool"]
    assert pool["total"] == 4
    assert pool["judged"] == 1
    assert pool["grade_counts"] == {"0": 1, "1": 0, "2": 0, "3": 0}
    assert pool["unjudged"] == 0
    assert pool["issue_counts"]["mapping_ambiguous"] == 3


async def test_runner_repeated_pid_and_none_reach_join_as_ambiguous_mapping():
    resp = response({"dense": [hit("a")], "sparse": [], "bm25": []})
    result = await collect(
        resp,
        [
            corpus("a", pid="p1"),
            corpus("a", pid="p1"),
            {**corpus("a"), "source_passage_id": None},
        ],
    )
    assert result["source_rows"] == [[1, "a", None], [1, "a", "p1"], [1, "a", "p1"]]
    assert result["ranking_input_ready"] is True

    joined = join_candidate_qrels(
        source_query_id=result["source_query_id"],
        candidate_keys=[(row["dataset_id"], row["chunk_id"]) for row in result["candidate_rows"]],
        source_rows=result["source_rows"],
        qrels=parse_t2_qrels(["001\t0\tp1\t3\n"]),
    )

    assert joined.candidate_keys == ((1, "a"),)
    assert joined.grades == {}
    assert joined.issues == {(1, "a"): "mapping_ambiguous"}
    pool = summarize_label_coverage([joined])["overall"]["pool"]
    assert pool["total"] == 1
    assert pool["judged"] == 0
    assert pool["unjudged"] == 0
    assert pool["issue_counts"]["mapping_ambiguous"] == 1


@pytest.mark.parametrize("missing_field", ["doc_id", "content"])
async def test_missing_ranking_fields_block_ranking_but_preserve_candidate(missing_field):
    row = corpus("a")
    del row[missing_field]
    result = await collect(response({"dense": [hit("a")], "sparse": [], "bm25": []}), [row])
    assert result["ranking_input_ready"] is False
    assert result["candidate_rows"][0]["chunk_id"] == "a"
    assert result["input_issues"][0]["code"] == "invalid_corpus_row"


@pytest.mark.parametrize("pid", [None, ""])
async def test_missing_source_pid_does_not_filter_ranking(pid):
    row = {**corpus("a"), "source_passage_id": pid}
    result = await collect(response({"dense": [hit("a")], "sparse": [], "bm25": []}), [row])
    assert result["status"] == "incomplete"
    assert result["ranking_input_ready"] is True
    assert result["candidate_rows"][0]["content"] == row["content"]
    assert result["source_rows"] == [[1, "a", None]]


async def test_absent_source_field_does_not_filter_ranking():
    row = corpus("a")
    del row["source_passage_id"]
    result = await collect(response({"dense": [hit("a")], "sparse": [], "bm25": []}), [row])
    assert result["status"] == "incomplete"
    assert result["ranking_input_ready"] is True
    assert result["source_rows"] == [[1, "a", None]]


@pytest.mark.parametrize("changed", [{"doc_id": 999}, {"content": "不同正文"}])
async def test_repeated_corpus_rows_with_conflicting_ranking_values_block_ranking(changed):
    resp = response({"dense": [hit("a")], "sparse": [], "bm25": []})
    result = await collect(resp, [corpus("a"), {**corpus("a"), **changed}])
    assert result["status"] == "incomplete"
    assert result["ranking_input_ready"] is False
    assert result["candidate_rows"][0]["chunk_id"] == "a"
    assert result["candidate_rows"][0]["content"] is None
    assert "conflicting_corpus_ranking_values" in {
        issue["code"] for issue in result["input_issues"]
    }


async def test_doc_id_disagreement_between_routes_blocks_ranking():
    resp = response({"dense": [hit("a")], "sparse": [hit("a", doc_id=999)], "bm25": []})
    result = await collect(resp, [corpus("a")])
    assert result["ranking_input_ready"] is False
    assert result["routes"]["dense"][0]["doc_id"] == 10
    assert result["routes"]["sparse"][0]["doc_id"] == 999
