"""EvalSettings 配置默认值。"""

from __future__ import annotations

from linkrag_eval.config import EvalSettings


def test_recall_threshold_defaults() -> None:
    settings = EvalSettings(_env_file=None)

    assert settings.recall_dense_score_threshold == 0.20
    assert settings.recall_sparse_score_threshold == 0.40
    assert settings.recall_dense_top_k == 150
    assert settings.recall_sparse_top_k == 50
    assert settings.recall_fusion_strategy == "weighted_score"
    assert settings.recall_dense_weight == 0.90
    assert settings.recall_sparse_weight == 0.10
    assert settings.recall_bm25_weight == 0.0
