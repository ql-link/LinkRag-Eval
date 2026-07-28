from __future__ import annotations

import json

import pytest

from linkrag_eval.golden_v2.pooled_review import merge_independent_reviews, prepare_blinded_pool


def _write(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


def test_two_reviewers_and_arbitrator_build_multi_positive_qrels(tmp_path) -> None:
    pool = tmp_path / "pool.jsonl"
    _write(
        pool,
        [
            {
                "query_id": "q1",
                "query": "问题",
                "candidates": [
                    {"chunk_id": "c1", "doc_id": 1, "dataset_id": 9, "content": "答案一"},
                    {"chunk_id": "c2", "doc_id": 2, "dataset_id": 9, "content": "答案二"},
                ],
            }
        ],
    )
    blinded = tmp_path / "blinded.jsonl"
    assert prepare_blinded_pool(pool, out=blinded, top_n=50, salt="frozen") == 2
    rows = [json.loads(line) for line in blinded.read_text().splitlines()]
    r1 = tmp_path / "r1.jsonl"
    r2 = tmp_path / "r2.jsonl"
    arb = tmp_path / "arb.jsonl"
    _write(
        r1,
        [
            {"review_id": r["review_id"], "reviewer_id": "a", "relevant": True, "grade": 3}
            for r in rows
        ],
    )
    _write(
        r2,
        [
            {"review_id": rows[0]["review_id"], "reviewer_id": "b", "relevant": True, "grade": 2},
            {"review_id": rows[1]["review_id"], "reviewer_id": "b", "relevant": False, "grade": 0},
        ],
    )
    _write(
        arb, [{"review_id": rows[1]["review_id"], "reviewer_id": "c", "relevant": True, "grade": 2}]
    )

    report = merge_independent_reviews(
        blinded,
        [r1, r2],
        out=tmp_path / "merged.jsonl",
        qrels_out=tmp_path / "qrels.jsonl",
        arbitration_path=arb,
    )

    qrel = json.loads((tmp_path / "qrels.jsonl").read_text())
    assert qrel["expected_chunk_ids"] == ["c1", "c2"]
    assert report.multi_positive_queries == 1
    assert report.disagreements == 1


def test_pool_requires_two_independent_reviewers(tmp_path) -> None:
    blinded = tmp_path / "b.jsonl"
    _write(
        blinded,
        [
            {
                "review_id": "x",
                "query_id": "q",
                "query": "q",
                "chunk_id": "c",
                "doc_id": 1,
                "dataset_id": 1,
            }
        ],
    )
    review = tmp_path / "r.jsonl"
    _write(review, [{"review_id": "x", "reviewer_id": "same", "relevant": True}])
    with pytest.raises(ValueError, match="两个不同"):
        merge_independent_reviews(blinded, [review], out=tmp_path / "o", qrels_out=tmp_path / "q")
