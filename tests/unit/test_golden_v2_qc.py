"""Golden V2 judgment QC。"""

from __future__ import annotations

import json

from linkrag_eval.golden_v2 import (
    adjudicate_judgments,
    build_review_queue,
    label_review_queue,
    qc_judgments,
)


class _FakeReviewer:
    model = "reviewer-test"

    async def generate_json(self, **kwargs):
        prompt = kwargs["prompt"]
        if "办理时限" in prompt:
            return {"relevant": True, "grade": 2, "evidence_span": "办理时限", "reason": "复核相关"}
        return {"relevant": False, "grade": 0, "reason": "复核无关"}


def _write_jsonl(path, rows) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_qc_judgments_passes_with_low_random_rate(tmp_path) -> None:
    judgments = tmp_path / "judgments.jsonl"
    _write_jsonl(
        judgments,
        [
            {
                "query_id": "q1",
                "query": "多久办完",
                "candidate": {"chunk_id": "c1", "sources": ["current_dense"]},
                "relevant": True,
                "grade": 2,
            },
            {
                "query_id": "q1",
                "query": "多久办完",
                "candidate": {"chunk_id": "r1", "sources": ["random_neighbor"]},
                "relevant": False,
                "grade": 0,
            },
            {
                "query_id": "q2",
                "query": "别名",
                "candidate": {"chunk_id": "a1", "sources": ["alt_embedding:model"]},
                "relevant": True,
                "grade": 1,
            },
        ],
    )

    report = qc_judgments(
        [judgments],
        report_out=tmp_path / "qc.json",
        markdown_out=tmp_path / "qc.md",
    )

    assert report.status == "pass"
    assert report.total_queries == 2
    assert report.random_relevant_rate == 0.0
    assert report.unresolved_rate == 0.0
    assert (tmp_path / "qc.json").exists()
    assert (tmp_path / "qc.md").exists()


def test_qc_judgments_fails_on_random_relevant_rate(tmp_path) -> None:
    judgments = tmp_path / "judgments.jsonl"
    _write_jsonl(
        judgments,
        [
            {
                "query_id": "q1",
                "query": "问题",
                "candidate": {"chunk_id": "r1", "sources": ["random_neighbor"]},
                "relevant": True,
                "grade": 1,
            }
        ],
    )

    report = qc_judgments([judgments], max_random_relevant_rate=0.05)

    assert report.status == "fail"
    assert report.random_relevant_rate == 1.0
    assert any("random_relevant_rate" in item for item in report.failures)


def test_qc_judgments_ignores_hybrid_random_source_for_random_rate(tmp_path) -> None:
    judgments = tmp_path / "judgments.jsonl"
    _write_jsonl(
        judgments,
        [
            {
                "query_id": "q1",
                "query": "问题",
                "candidate": {"chunk_id": "r1", "sources": ["current_dense", "random_neighbor"]},
                "relevant": True,
                "grade": 1,
            },
            {
                "query_id": "q2",
                "query": "问题 2",
                "candidate": {"chunk_id": "a1", "sources": ["alt_embedding:model"]},
                "relevant": True,
                "grade": 1,
            },
        ],
    )

    report = qc_judgments([judgments], max_random_relevant_rate=0.05)

    assert report.status == "warn"
    assert report.random_candidates == 0
    assert report.random_relevant_rate == 0.0
    assert not any("random_relevant_rate" in item for item in report.failures)


def test_build_review_queue_extracts_high_risk_rows(tmp_path) -> None:
    judgments = tmp_path / "judgments.jsonl"
    _write_jsonl(
        judgments,
        [
            {
                "query_id": "q1",
                "query": "随机相关",
                "candidate": {"chunk_id": "r1", "sources": ["random_neighbor"]},
                "relevant": True,
                "grade": 1,
                "judge_model": "deepseek",
            },
            {
                "query_id": "q2",
                "query": "无答案",
                "candidate": {"chunk_id": "n1", "sources": ["current_dense"]},
                "relevant": False,
                "grade": 0,
            },
            {
                "query_id": "q3",
                "query": "无 alt 支持",
                "candidate": {"chunk_id": "p1", "sources": ["current_dense"]},
                "relevant": True,
                "grade": 2,
            },
        ],
    )

    report = build_review_queue(
        [judgments],
        out=tmp_path / "review_queue.jsonl",
        report_out=tmp_path / "review_report.json",
    )

    assert report.total_items == 4
    assert report.reason_counts == {
        "no_alt_positive_support": 2,
        "random_relevant": 1,
        "unresolved_query": 1,
    }
    rows = [
        json.loads(line)
        for line in (tmp_path / "review_queue.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert {row["review_reason"] for row in rows} == {
        "random_relevant",
        "unresolved_query",
        "no_alt_positive_support",
    }


def test_build_review_queue_ignores_hybrid_random_source_for_random_review(tmp_path) -> None:
    judgments = tmp_path / "judgments.jsonl"
    _write_jsonl(
        judgments,
        [
            {
                "query_id": "q1",
                "query": "混合来源相关",
                "candidate": {"chunk_id": "r1", "sources": ["current_dense", "random_neighbor"]},
                "relevant": True,
                "grade": 1,
                "judge_model": "deepseek",
            },
            {
                "query_id": "q2",
                "query": "alt 相关",
                "candidate": {"chunk_id": "a1", "sources": ["alt_embedding:model"]},
                "relevant": True,
                "grade": 1,
                "judge_model": "deepseek",
            },
        ],
    )

    report = build_review_queue([judgments], out=tmp_path / "review_queue.jsonl")

    assert report.reason_counts == {"no_alt_positive_support": 1}
    rows = [
        json.loads(line)
        for line in (tmp_path / "review_queue.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [row["review_reason"] for row in rows] == ["no_alt_positive_support"]


async def test_label_review_queue_hydrates_content_and_writes_review(tmp_path) -> None:
    queue = tmp_path / "review_queue.jsonl"
    pool = tmp_path / "candidate_pool.jsonl"
    _write_jsonl(
        queue,
        [
            {
                "review_reason": "random_relevant",
                "query_id": "q1",
                "query": "多久办完",
                "candidate": {"chunk_id": "c1", "sources": ["random_neighbor"]},
                "original_relevant": True,
                "original_grade": 1,
            }
        ],
    )
    _write_jsonl(
        pool,
        [
            {
                "query_id": "q1",
                "query": "多久办完",
                "candidates": [
                    {
                        "chunk_id": "c1",
                        "doc_id": 1,
                        "dataset_id": 1,
                        "content": "政策办理时限为 7 个工作日。",
                    }
                ],
            }
        ],
    )

    report = await label_review_queue(
        queue,
        candidate_pool_paths=[pool],
        out=tmp_path / "review_judgments.jsonl",
        judge_client=_FakeReviewer(),
        report_out=tmp_path / "review_report.json",
    )

    assert report.reviewed == 1
    assert report.relevant == 1
    row = json.loads((tmp_path / "review_judgments.jsonl").read_text(encoding="utf-8"))
    assert row["review_relevant"] is True
    assert row["review_grade"] == 2
    assert row["review_reason"] == "random_relevant"
    assert row["reviewer_reason"] == "复核相关"
    assert row["reviewer_model"] == "reviewer-test"


async def test_label_review_queue_marks_missing_content(tmp_path) -> None:
    queue = tmp_path / "review_queue.jsonl"
    pool = tmp_path / "candidate_pool.jsonl"
    _write_jsonl(
        queue,
        [{"review_reason": "random_relevant", "query_id": "q1", "query": "q", "candidate": {"chunk_id": "missing"}}],
    )
    _write_jsonl(pool, [])

    report = await label_review_queue(
        queue,
        candidate_pool_paths=[pool],
        out=tmp_path / "review_judgments.jsonl",
        judge_client=_FakeReviewer(),
    )

    assert report.missing_content == 1
    row = json.loads((tmp_path / "review_judgments.jsonl").read_text(encoding="utf-8"))
    assert row["review_relevant"] is False
    assert row["review_reason"] == "random_relevant"
    assert row["reviewer_reason"] == "missing_candidate_content"


def test_adjudicate_judgments_review_overrides(tmp_path) -> None:
    judgments = tmp_path / "judgments.jsonl"
    reviews = tmp_path / "review_judgments.jsonl"
    _write_jsonl(
        judgments,
        [
            {
                "query_id": "q1",
                "query": "随机相关",
                "candidate": {"chunk_id": "c1", "doc_id": 1, "dataset_id": 1},
                "relevant": True,
                "grade": 2,
            },
            {
                "query_id": "q2",
                "query": "确认相关",
                "candidate": {"chunk_id": "c2", "doc_id": 2, "dataset_id": 1},
                "relevant": True,
                "grade": 1,
            },
        ],
    )
    _write_jsonl(
        reviews,
        [
            {
                "query_id": "q1",
                "candidate": {"chunk_id": "c1"},
                "review_relevant": False,
                "review_grade": 0,
                "reviewer_model": "reviewer",
                "review_reason": "复核无关",
            },
            {
                "query_id": "q2",
                "candidate": {"chunk_id": "c2"},
                "review_relevant": True,
                "review_grade": 2,
                "reviewer_model": "reviewer",
                "review_reason": "复核相关",
            },
        ],
    )

    report = adjudicate_judgments(
        [judgments],
        review_paths=[reviews],
        out=tmp_path / "adjudicated.jsonl",
        report_out=tmp_path / "adjudication_report.json",
    )

    assert report.changed == 2
    assert report.unique_review_items == 2
    assert report.duplicate_reviews == 0
    rows = [
        json.loads(line)
        for line in (tmp_path / "adjudicated.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    by_id = {row["query_id"]: row for row in rows}
    assert by_id["q1"]["relevant"] is False
    assert by_id["q1"]["grade"] == 0
    assert by_id["q1"]["adjudication_status"] == "review_changed"
    assert by_id["q2"]["relevant"] is True
    assert by_id["q2"]["grade"] == 2


def test_adjudicate_judgments_counts_duplicate_reviews(tmp_path) -> None:
    judgments = tmp_path / "judgments.jsonl"
    reviews = tmp_path / "review_judgments.jsonl"
    _write_jsonl(
        judgments,
        [
            {
                "query_id": "q1",
                "query": "q",
                "candidate": {"chunk_id": "c1", "doc_id": 1, "dataset_id": 1},
                "relevant": True,
                "grade": 1,
            }
        ],
    )
    _write_jsonl(
        reviews,
        [
            {"query_id": "q1", "candidate": {"chunk_id": "c1"}, "review_relevant": True, "review_grade": 1},
            {"query_id": "q1", "candidate": {"chunk_id": "c1"}, "review_relevant": False, "review_grade": 0},
        ],
    )

    report = adjudicate_judgments([judgments], review_paths=[reviews], out=tmp_path / "out.jsonl")

    assert report.review_items == 2
    assert report.unique_review_items == 1
    assert report.duplicate_reviews == 1


def test_adjudicate_judgments_manual_on_conflict_keeps_original(tmp_path) -> None:
    judgments = tmp_path / "judgments.jsonl"
    reviews = tmp_path / "review_judgments.jsonl"
    _write_jsonl(
        judgments,
        [
            {
                "query_id": "q1",
                "query": "q",
                "candidate": {"chunk_id": "c1", "doc_id": 1, "dataset_id": 1},
                "relevant": True,
                "grade": 2,
            },
            {
                "query_id": "q2",
                "query": "q2",
                "candidate": {"chunk_id": "c2", "doc_id": 2, "dataset_id": 1},
                "relevant": True,
                "grade": 1,
            },
        ],
    )
    _write_jsonl(
        reviews,
        [
            {
                "query_id": "q1",
                "candidate": {"chunk_id": "c1"},
                "review_relevant": False,
                "review_grade": 0,
                "reviewer_model": "reviewer",
            },
            {
                "query_id": "q2",
                "candidate": {"chunk_id": "c2"},
                "review_relevant": True,
                "review_grade": 1,
                "reviewer_model": "reviewer",
            },
        ],
    )

    report = adjudicate_judgments(
        [judgments],
        review_paths=[reviews],
        out=tmp_path / "adjudicated.jsonl",
        conflict_out=tmp_path / "conflicts.jsonl",
        policy="manual_on_conflict",
    )

    assert report.changed == 0
    assert report.kept == 1
    assert report.conflicts == 1
    rows = [
        json.loads(line)
        for line in (tmp_path / "adjudicated.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    by_id = {row["query_id"]: row for row in rows}
    assert by_id["q1"]["relevant"] is True
    assert by_id["q1"]["grade"] == 2
    assert by_id["q1"]["adjudication_status"] == "needs_manual_review"
    assert by_id["q2"]["adjudication_status"] == "review_confirmed"
    conflicts = [
        json.loads(line)
        for line in (tmp_path / "conflicts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [row["query_id"] for row in conflicts] == ["q1"]
