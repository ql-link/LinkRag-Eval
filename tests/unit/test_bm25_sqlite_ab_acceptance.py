"""SQLite BM25 最终 A/B 报告的强制验收门禁。"""

from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/render_bm25_sqlite_ab_acceptance.py"


def _module():
    spec = importlib.util.spec_from_file_location("bm25_ab_acceptance", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _result(run_id: str, *, bm25: bool, recall: float, mrr: float) -> dict:
    return {
        "run_id": run_id,
        "snapshot": {
            "run_id": run_id,
            "git_sha": "abc123",
            "git_dirty": True,
            "git_worktree_sha256": "worktree-sha",
            "sparse_vector_provider": "ark:sparse-v1",
            "top_k": 10,
            "score_threshold": 0.1,
            "enabled_sources": ["dense", "sparse", *(["bm25"] if bm25 else [])],
            "rrf_k": 60,
            "rerank_top_n": None,
            "chat_model": "",
            "judge_model": "",
            "generator_model": "",
            "token_budget": 0,
            "prompt_version": "v1",
            "route_score_thresholds": {"dense": 0.3, "sparse": 0.1},
            "route_top_ks": {"dense": 150, "sparse": 50, "bm25": 100},
            "fusion_strategy": "weighted_score",
            "fusion_weights": {"dense": 0.7, "sparse": 0.15, "bm25": 0.15},
            "bm25_mode": "sqlite_fts5",
            "bm25_sidecar_identity": {
                "backend": "sqlite_fts5",
                "path": "/tmp/eval-bm25.sqlite3",
                "exists": True,
                "schema_version": 1,
                "chunk_count": 20000,
                "dataset_counts": {
                    "992000": 5000,
                    "992001": 5000,
                    "992002": 5000,
                    "992003": 5000,
                },
                "content_sha256": "a" * 64,
            },
            "computer_fingerprint": {"dense": {"model": "dense-v1"}},
            "feature_version": "recall_pipeline_v1",
        },
        "metrics": [
            {
                "name": "recall_chunk",
                "k": 10,
                "mean": recall,
                "by_type": {"keyword": recall},
            },
            {"name": "mrr_chunk", "k": None, "mean": mrr, "by_type": {}},
        ],
        "per_sample": [
            {
                "sample_id": "q1",
                "elapsed_ms": 100 if not bm25 else 120,
                "failed_sources": [],
                "n_ranked": 10,
            }
        ],
    }


def test_build_report_accepts_same_sidecar_clean_runs() -> None:
    module = _module()
    report = module.build_report(
        _result("off", bm25=False, recall=0.4, mrr=0.2),
        _result("on", bm25=True, recall=0.5, mrr=0.25),
        expected_dataset_ids=[992000, 992001, 992002, 992003],
    )

    assert report["status"] == "passed"
    assert report["delta"]["recall_at_10"] == pytest.approx(0.1)
    assert report["delta"]["mrr"] == pytest.approx(0.05)
    assert report["delta"]["latency_mean_ms"] == pytest.approx(20)
    assert "PASS" in module.render_html(report)


def test_build_report_rejects_non_clean_or_changed_sidecar() -> None:
    module = _module()
    off = _result("off", bm25=False, recall=0.4, mrr=0.2)
    on = deepcopy(_result("on", bm25=True, recall=0.5, mrr=0.25))
    on["per_sample"][0]["failed_sources"] = ["bm25"]
    on["snapshot"]["bm25_sidecar_identity"]["content_sha256"] = "b" * 64

    with pytest.raises(ValueError, match="不是 clean run"):
        module.build_report(
            off,
            on,
            expected_dataset_ids=[992000, 992001, 992002, 992003],
        )
