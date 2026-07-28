"""Golden V2 labeling:候选池 + fake judge → judgments。"""

from __future__ import annotations

import json
import asyncio

import pytest

from linkrag_eval.golden_v2 import label_candidate_pool


class _FakeJudge:
    model = "deepseek-test"

    async def generate_json(self, **kwargs):
        prompt = kwargs["prompt"]
        if "办理时限" in prompt:
            return {"relevant": True, "grade": 2, "evidence_span": "办理时限", "reason": "直接相关"}
        return {"relevant": False, "grade": 0, "reason": "无关"}


class _FailingJudge:
    model = "deepseek-timeout-test"

    async def generate_json(self, **kwargs):
        raise TimeoutError("simulated timeout")


class _ConcurrentJudge:
    model = "deepseek-concurrent-test"

    def __init__(self) -> None:
        self.active = 0
        self.peak = 0

    async def generate_json(self, **kwargs):
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        return {"relevant": False, "grade": 0, "reason": "无关"}


def _write_jsonl(path, rows) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


async def test_label_candidate_pool_writes_judgments(tmp_path) -> None:
    pool = tmp_path / "candidate_pool.jsonl"
    _write_jsonl(
        pool,
        [
            {
                "query_id": "q1",
                "query": "多久办完",
                "role": "realistic",
                "source": "spark_pregen",
                "candidates": [
                    {
                        "chunk_id": "c1",
                        "doc_id": 1,
                        "dataset_id": 990901,
                        "content": "政策办理时限为 7 个工作日。",
                        "sources": ["bm25_local"],
                        "rank_by_source": {"bm25_local": 1},
                    }
                ],
            }
        ],
    )

    report = await label_candidate_pool(
        pool,
        out=tmp_path / "judgments.jsonl",
        judge_client=_FakeJudge(),
        report_out=tmp_path / "report.json",
    )

    assert report.judged == 1
    assert report.relevant == 1
    row = json.loads((tmp_path / "judgments.jsonl").read_text(encoding="utf-8"))
    assert row["relevant"] is True
    assert row["grade"] == 2
    assert row["judge_failed"] is False
    assert row["judge_model"] == "deepseek-test"


async def test_label_candidate_pool_records_failed_judge(tmp_path) -> None:
    pool = tmp_path / "candidate_pool.jsonl"
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
                        "dataset_id": 990901,
                        "content": "政策办理时限为 7 个工作日。",
                    }
                ],
            }
        ],
    )

    report = await label_candidate_pool(
        pool,
        out=tmp_path / "judgments.jsonl",
        judge_client=_FailingJudge(),
        report_out=tmp_path / "report.json",
    )

    assert report.judged == 1
    assert report.relevant == 0
    assert report.failed == 1
    assert report.unresolved_queries == 1
    row = json.loads((tmp_path / "judgments.jsonl").read_text(encoding="utf-8"))
    assert row["judge_failed"] is True
    assert row["reason"] == "judge_call_failed:TimeoutError"


async def test_label_candidate_pool_streams_completed_rows_before_later_error(tmp_path) -> None:
    pool = tmp_path / "candidate_pool.jsonl"
    out = tmp_path / "judgments.jsonl"
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
                        "dataset_id": 990901,
                        "content": "政策办理时限为 7 个工作日。",
                    },
                    {
                        "chunk_id": "c2",
                        "dataset_id": 990901,
                        "content": "缺少 doc_id,用于模拟后续候选结构错误。",
                    },
                ],
            }
        ],
    )

    with pytest.raises(KeyError):
        await label_candidate_pool(pool, out=out, judge_client=_FakeJudge())

    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["candidate"]["chunk_id"] == "c1"


async def test_label_candidate_pool_limits_per_query_concurrency(tmp_path) -> None:
    pool = tmp_path / "candidate_pool.jsonl"
    _write_jsonl(
        pool,
        [{
            "query_id": "q1",
            "query": "多久办完",
            "candidates": [
                {"chunk_id": f"c{i}", "doc_id": i, "dataset_id": 990901, "content": "候选"}
                for i in range(5)
            ],
        }],
    )
    judge = _ConcurrentJudge()

    report = await label_candidate_pool(
        pool,
        out=tmp_path / "judgments.jsonl",
        judge_client=judge,
        max_concurrency=2,
    )

    assert report.judged == 5
    assert judge.peak == 2
