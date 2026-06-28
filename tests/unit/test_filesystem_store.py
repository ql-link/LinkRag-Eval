"""FilesystemResultStore 完整体单测:结构化结果落盘 + 基线往返(纯 IO,零 rag)。

覆盖源仓库当时未迁的 save_result/load_baseline:by_type + by_domain 全往返不丢,
读回的基线可直接喂 diff_metrics 出回归。
"""

from __future__ import annotations

from linkrag_eval.models import (
    EvalResult,
    Layer,
    MetricResult,
    QuestionType,
    Snapshot,
)
from linkrag_eval.reporters import diff_metrics
from linkrag_eval.store.filesystem import FilesystemResultStore


def _snapshot(run_id: str) -> Snapshot:
    return Snapshot(
        run_id=run_id, git_sha="abc1234", sparse_vector_provider="bge_m3", top_k=10,
        score_threshold=0.0, enabled_sources=["dense", "sparse"], rrf_k=60,
        rerank_top_n=8, chat_model="", judge_model="", generator_model="",
        token_budget=0, prompt_version="v1",
    )


def _result(run_id: str, recall: float) -> EvalResult:
    metrics = [
        MetricResult(
            name="recall", layer=Layer.RETRIEVAL, k=10, mean=recall, n=50,
            by_type={QuestionType.KEYWORD: recall, QuestionType.PARAPHRASE: recall - 0.05},
            by_type_n={QuestionType.KEYWORD: 30, QuestionType.PARAPHRASE: 20},
            by_domain={"medical": recall + 0.02, "legal": recall - 0.03},
            by_domain_n={"medical": 25, "legal": 25},
        )
    ]
    return EvalResult(
        run_id=run_id, snapshot=_snapshot(run_id), metrics=metrics,
        per_sample=[{"sample_id": "s1", "hit": True}],
    )


class TestFilesystemRoundtrip:
    def test_save_and_load_preserves_buckets(self, tmp_path):
        store = FilesystemResultStore(tmp_path, dataset="dur")
        store.save_result(_result("r1", 0.90), ts="2026-06-28T00:00:00")
        loaded = store.load_baseline("r1")

        assert loaded is not None
        assert loaded.run_id == "r1"
        assert loaded.snapshot.sparse_vector_provider == "bge_m3"
        m = loaded.metrics[0]
        assert m.name == "recall" and m.mean == 0.90 and m.k == 10
        # by_type / by_domain 键类型与值全往返
        assert m.by_type[QuestionType.KEYWORD] == 0.90
        assert m.by_type_n[QuestionType.PARAPHRASE] == 20
        assert m.by_domain == {"medical": 0.92, "legal": 0.87}
        assert m.by_domain_n == {"medical": 25, "legal": 25}
        assert loaded.per_sample == [{"sample_id": "s1", "hit": True}]

    def test_loaded_baseline_feeds_diff(self, tmp_path):
        store = FilesystemResultStore(tmp_path)
        store.save_result(_result("base", 0.90))
        baseline = store.load_baseline("base")
        current = _result("cur", 0.84)            # 跌 0.06 → 回归
        diff = diff_metrics(current, baseline)
        assert diff.comparable
        assert len(diff.regressions) == 1

    def test_missing_baseline_returns_none(self, tmp_path):
        assert FilesystemResultStore(tmp_path).load_baseline("nope") is None

    def test_writes_to_results_subdir(self, tmp_path):
        store = FilesystemResultStore(tmp_path)
        path = store.save_result(_result("r1", 0.9))
        assert path == tmp_path / "results" / "r1.json"
        store.save_snapshot(_result("r1", 0.9).snapshot)
        assert (tmp_path / "snapshots" / "r1.json").exists()
