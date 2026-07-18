"""EvalSettings 配置默认值。"""

from __future__ import annotations

from linkrag_eval.cli import _normalize_single_route_weight, _parse_enabled_sources
from linkrag_eval.config import EvalSettings


def test_recall_threshold_defaults() -> None:
    settings = EvalSettings(_env_file=None)

    assert settings.recall_dense_score_threshold == 0.30
    assert settings.recall_sparse_score_threshold == 0.20
    assert settings.recall_dense_top_k == 150
    assert settings.recall_sparse_top_k == 50
    assert settings.recall_bm25_top_k == 100
    assert settings.recall_fusion_strategy == "weighted_score"
    assert settings.recall_dense_weight == 0.70
    assert settings.recall_sparse_weight == 0.15
    assert settings.recall_bm25_weight == 0.15
    assert settings.qdrant_bm25_collection == "eval_bm25"
    assert settings.qdrant_bm25_vector_name == "bm25_text"
    assert settings.bm25_sqlite_path == "runs/bm25_eval.sqlite3"
    assert settings.alt_embed_provider == "openai"
    assert settings.alt_embed_base_url == ""
    assert settings.alt_embed_api_key == ""
    assert settings.alt_embed_model == ""
    assert settings.alt_embed_dim == 1024
    assert settings.alt_embed_sqlite_path == "runs/alt_embedding_eval.sqlite3"


def test_single_bm25_route_gets_a_valid_weight_for_weighted_score() -> None:
    settings = EvalSettings(_env_file=None)

    _normalize_single_route_weight(settings, _parse_enabled_sources("bm25"))

    assert settings.recall_bm25_weight == 1.0
    assert settings.recall_dense_weight == 0.70
    assert settings.recall_sparse_weight == 0.15


def test_multi_route_weights_remain_configured() -> None:
    settings = EvalSettings(_env_file=None)

    _normalize_single_route_weight(settings, _parse_enabled_sources("dense,bm25"))

    assert settings.recall_bm25_weight == 0.15
