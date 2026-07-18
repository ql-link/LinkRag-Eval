"""reporters.emit 落盘收口单测(纯 IO,无 rag/活栈):

- write_retrieval_reports:出 <run_id>.html + <run_id>.json,JSON 可解析含台账 rows。
- write_cleaning_reports:出 <run_id>.cleaning.html + .jsonl,明细逐行可解析。
"""

from __future__ import annotations

import json

from linkrag_eval.metrics import cleaning as M
from linkrag_eval.models import (
    CleaningBucket,
    CleaningPair,
    CleaningQcReport,
    EvalResult,
    Layer,
    MetricResult,
    QuestionType,
    Snapshot,
)
from linkrag_eval.reporters.emit import (
    write_cleaning_reports,
    write_retrieval_reports,
)


def _snapshot(run_id: str) -> Snapshot:
    return Snapshot(
        run_id=run_id, git_sha="abc", sparse_vector_provider="bge_m3", top_k=10,
        score_threshold=0.0, enabled_sources=["dense", "sparse"], rrf_k=60,
        rerank_top_n=None, chat_model="", judge_model="", generator_model="",
        token_budget=0, prompt_version="v1",
    )


def _result(run_id: str) -> EvalResult:
    metrics = [
        MetricResult(
            name="recall", layer=Layer.RETRIEVAL, k=10, mean=0.9, n=50,
            by_type={QuestionType.KEYWORD: 0.9}, by_type_n={QuestionType.KEYWORD: 50},
        )
    ]
    return EvalResult(run_id=run_id, snapshot=_snapshot(run_id), metrics=metrics)


class TestRetrievalReports:
    def test_writes_html_and_json(self, tmp_path):
        write_retrieval_reports(
            _result("r1"), tmp_path, run_id="r1", dataset="dur"
        )
        assert (tmp_path / "r1.html").exists()
        assert (tmp_path / "r1.json").exists()
        payload = json.loads((tmp_path / "r1.json").read_text(encoding="utf-8"))
        assert payload["run_id"] == "r1"
        assert payload["dataset"] == "dur"
        assert payload["rows"]  # 台账非空

    def test_baseline_diff_in_json(self, tmp_path):
        # current 比 baseline 跌 0.9→0.8,JSON 应含 deltas
        cur = _result("cur")
        base = EvalResult(
            run_id="base", snapshot=_snapshot("base"),
            metrics=[MetricResult(
                name="recall", layer=Layer.RETRIEVAL, k=10, mean=0.95, n=50,
                by_type={QuestionType.KEYWORD: 0.95},
                by_type_n={QuestionType.KEYWORD: 50},
            )],
        )
        write_retrieval_reports(cur, tmp_path, run_id="cur", baseline=base)
        payload = json.loads((tmp_path / "cur.json").read_text(encoding="utf-8"))
        assert payload["baseline_run_id"] == "base"
        assert payload["deltas"]


class TestCleaningReports:
    def test_writes_html_and_detail(self, tmp_path):
        pair = CleaningPair(ref="# 标题\n正文", produced="# 标题\n正文", ok=True)
        item = M.score_pair(
            pair, sample_id="s1", fmt="html", pdf_backend=None,
            clean_ms=12, ok=True,
        )
        report = CleaningQcReport(
            run_id="c1",
            buckets=[CleaningBucket(format="html", pdf_backend=None, n=1,
                                    metrics={"text_similarity": 1.0})],
        )
        write_cleaning_reports(report, [item], tmp_path, run_id="c1")
        assert (tmp_path / "c1.cleaning.html").exists()
        lines = (tmp_path / "c1.cleaning.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        row = json.loads(lines[0])
        assert row["sample_id"] == "s1"
        assert row["format"] == "html"
