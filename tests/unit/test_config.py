"""EvalSettings 配置默认值。"""

from __future__ import annotations

from linkrag_eval.config import EvalSettings


def test_recall_threshold_defaults() -> None:
    settings = EvalSettings(_env_file=None)

    assert settings.recall_dense_score_threshold == 0.0
    assert settings.recall_sparse_score_threshold == 0.30
