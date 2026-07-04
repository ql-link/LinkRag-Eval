"""报告/diff/回归判据 + ledger 长表单测(搬迁自源仓库 test_reporters.py 的报告部分)。

TestFilesystemStore 依赖完整的 FilesystemResultStore(save_result/ledger 往返),随该存储
后端后续迁移;本文件覆盖 reporters + ledger_rows。
"""

from __future__ import annotations

import json

import pytest

from linkrag_eval.models import (
    EvalResult,
    Layer,
    MetricResult,
    QuestionType,
    Snapshot,
)
from linkrag_eval.reporters import (
    HtmlReporter,
    JsonReporter,
    RegressionCriteria,
    diff_metrics,
)
from linkrag_eval.store.ledger import ledger_rows
def make_snapshot(run_id: str, **overrides) -> Snapshot:
    defaults = dict(
        run_id=run_id, git_sha="abc1234", sparse_vector_provider="bge_m3",
        top_k=20, score_threshold=0.0, enabled_sources=["bm25", "dense", "sparse"],
        rrf_k=60, rerank_top_n=8, chat_model="N/A", judge_model="N/A",
        generator_model="N/A", token_budget=4000, prompt_version="N/A",
    )
    defaults.update(overrides)
    return Snapshot(**defaults)


def mr(name: str, mean: float, k: int | None = 10, n: int = 50) -> MetricResult:
    return MetricResult(
        name=name, layer=Layer.RETRIEVAL, k=k, mean=mean, n=n,
        by_type={QuestionType.KEYWORD: mean}, by_type_n={QuestionType.KEYWORD: n},
    )


def make_result(run_id: str, metrics, **snap_overrides) -> EvalResult:
    return EvalResult(
        run_id=run_id, snapshot=make_snapshot(run_id, **snap_overrides), metrics=metrics,
    )


class TestDiff:
    def test_regression_detected(self):
        baseline = make_result("base", [mr("recall", 0.80)])
        current = make_result("cur", [mr("recall", 0.75)])
        diff = diff_metrics(current, baseline)
        assert diff.comparable
        assert len(diff.regressions) == 1
        assert diff.regressions[0].delta == pytest.approx(-0.05)

    def test_small_drop_not_regression(self):
        baseline = make_result("base", [mr("recall", 0.80)])
        current = make_result("cur", [mr("recall", 0.79)])
        assert diff_metrics(current, baseline).regressions == []

    def test_ndcg_threshold(self):
        baseline = make_result("base", [mr("ndcg_binary", 0.70)])
        current = make_result("cur", [mr("ndcg_binary", 0.67)])
        assert len(diff_metrics(current, baseline).regressions) == 1

    def test_small_n_never_triggers(self):
        baseline = make_result("base", [mr("recall", 0.80, n=10)])
        current = make_result("cur", [mr("recall", 0.50, n=10)])
        diff = diff_metrics(current, baseline)
        assert diff.regressions == []  # n < min_n 仅定性
        assert diff.deltas[0].delta == pytest.approx(-0.30)

    def test_provider_mismatch_incomparable(self):
        baseline = make_result("base", [mr("recall", 0.80)])
        current = make_result(
            "cur", [mr("recall", 0.40)], sparse_vector_provider="remote_bge_m3"
        )
        diff = diff_metrics(current, baseline)
        assert not diff.comparable
        assert diff.regressions == []  # 不同口径不触发回归
        assert any("sparse_vector_provider" in r for r in diff.incomparable_reasons)

    def test_criteria_configurable(self):
        baseline = make_result("base", [mr("recall", 0.80)])
        current = make_result("cur", [mr("recall", 0.79)])
        crit = RegressionCriteria(recall_drop=0.005)
        assert len(diff_metrics(current, baseline, crit).regressions) == 1


class TestHtmlReporter:
    def test_render_contains_key_elements(self):
        result = make_result("cur", [mr("recall", 0.81), mr("mrr", 0.6, k=None)])
        html = HtmlReporter(dataset="golden-v1").render(result)
        assert "golden-v1" in html
        assert "PASS" in html
        assert "recall" in html
        assert "top_k=20" in html
        assert "RECALL_RESULT_LIMIT" in html  # 口径脚注

    def test_render_with_regression_banner(self):
        baseline = make_result("base", [mr("recall", 0.80)])
        current = make_result("cur", [mr("recall", 0.70)])
        html = HtmlReporter().render(current, baseline)
        assert "检出回归" in html
        assert "检出 1 项回归" in html

    def test_incomparable_banner(self):
        baseline = make_result("base", [mr("recall", 0.80)])
        current = make_result("cur", [mr("recall", 0.70)], top_k=50)
        html = HtmlReporter().render(current, baseline)
        assert "口径与基线不一致" in html

    def test_small_bucket_labeled(self):
        result = make_result("cur", [mr("recall", 0.8, n=5)])
        html = HtmlReporter().render(result)
        assert "样本不足" in html

    def test_escapes_values(self):
        result = make_result("cur", [mr("recall", 0.8)], chat_model="<script>x")
        html = HtmlReporter().render(result)
        assert "<script>x" not in html

    def test_render_run_quality_from_per_sample(self):
        result = make_result("cur", [mr("recall", 0.8)])
        result.per_sample = [
            {"sample_id": "q1", "failed_sources": [], "n_ranked": 10, "elapsed_ms": 10},
            {"sample_id": "q2", "failed_sources": ["dense"], "n_ranked": 0, "elapsed_ms": 20},
            {"sample_id": "q3", "failed_sources": ["sparse"], "n_ranked": 10, "elapsed_ms": 30},
        ]
        html = HtmlReporter().render(result)
        assert "运行质量" in html
        assert "non-clean run" in html
        assert "dense=1" in html
        assert "sparse=1" in html
        assert "零结果样本" in html


class TestJsonReporterAndLedger:
    def test_ledger_rows_schema(self):
        result = make_result("cur", [mr("recall", 0.8)])
        rows = ledger_rows(result, dataset="golden-v1", ts="2026-06-13T00:00:00")
        assert len(rows) == 2  # __all__ + keyword 桶
        row = rows[0]
        for col in [
            "run_id", "ts", "git_sha", "dataset", "layer", "metric", "k",
            "relevance_scale", "type_bucket", "value", "n",
            "sparse_provider", "top_k", "score_threshold", "enabled_sources",
            "rrf_k", "route_top_ks", "fusion_strategy", "fusion_weights",
            "rerank_top_n", "chat_model", "judge_model", "generator_model",
        ]:
            assert col in row, f"缺列 {col}"
        assert row["type_bucket"] == "__all__"
        assert rows[1]["type_bucket"] == "keyword"
        assert row["relevance_scale"] == "binary"

    def test_graded_scale_flagged(self):
        result = make_result("cur", [mr("ndcg_graded", 0.7)])
        rows = ledger_rows(result, dataset="d", ts="t")
        assert rows[0]["relevance_scale"] == "graded"

    def test_json_reporter_with_baseline(self):
        baseline = make_result("base", [mr("recall", 0.80)])
        current = make_result("cur", [mr("recall", 0.70)])
        payload = json.loads(JsonReporter(dataset="d").render(current, baseline))
        assert payload["baseline_run_id"] == "base"
        assert payload["comparable"] is True
        assert payload["deltas"][0]["is_regression"] is True
        assert payload["rows"]
