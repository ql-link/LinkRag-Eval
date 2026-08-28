"""生产 ``candidate_difference_v3`` 的跨仓固定样本契约。

Gate A 把 LTR-v3 作为强基线。这里直接读取所安装 LinkRag 精确提交中的生产
bundle，并重放其冻结测试向量，防止特征顺序、浮点字节、模型或排序结果在升级时
静默漂移。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import lightgbm
import pytest

pytest.importorskip("src.core", reason="需安装冻结的 toLink-Rag 提交")
pytestmark = pytest.mark.contract

from src.core.pipeline.ltr.features import (
    FEATURE_NAMES,
    FEATURE_VERSION,
    ROUTES,
    build_online_features,
    feature_signature,
    weighted_fallback_order,
)
from src.core.pipeline.recall.models import RetrieverHit

MODEL_VERSION = "candidate-difference-v3-20260728-final33"
EXPECTED_FEATURE_SIGNATURE = (
    "52a69c3b8ae5e6a5988f62e0a87a775137a4f16ea769bc66829ec664b8782d7b"
)


def _contract_bundle() -> Path:
    # 评测仓中的六个文件是生产 bundle 的冻结镜像；CI 安装 production package 时
    # 未必把仓库级 models/ 一并打入 site-packages，因此契约不能依赖偶然的 checkout 路径。
    bundle = Path(__file__).resolve().parents[2] / "models" / MODEL_VERSION
    if not bundle.is_dir():
        pytest.fail(f"冻结 LTR-v3 契约 bundle 不存在: {bundle}")
    return bundle


def _rank(chunk_ids: list[str], scores) -> list[str]:
    return [
        item[0]
        for item in sorted(zip(chunk_ids, scores), key=lambda item: (-float(item[1]), item[0]))
    ]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_ltr_v3_bundle_replays_frozen_feature_and_ranking_vectors() -> None:
    bundle = _contract_bundle()
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))

    assert FEATURE_VERSION == "candidate_difference_v3"
    assert len(FEATURE_NAMES) == 38
    assert feature_signature() == EXPECTED_FEATURE_SIGNATURE
    assert manifest["model_version"] == MODEL_VERSION
    assert manifest["feature_signature"] == EXPECTED_FEATURE_SIGNATURE
    assert manifest["feature_names"] == FEATURE_NAMES
    assert _sha256(bundle / "model.txt") == manifest["model_file_sha256"]
    assert lightgbm.__version__ == manifest["lightgbm_version"]

    model = lightgbm.Booster(model_file=str(bundle / "model.txt"))
    payload = json.loads((bundle / "test_vectors.json").read_text(encoding="utf-8"))
    assert len(payload["vectors"]) == 3
    for vector in payload["vectors"]:
        inputs = vector["input"]
        routes = {
            source: [
                RetrieverHit(source=source, **hit)
                for hit in inputs["routes"].get(source, [])
            ]
            for source in ROUTES
        }
        chunk_ids, features = build_online_features(
            query=inputs["query"],
            routes=routes,
            candidate_contents=inputs["candidate_contents"],
        )
        expected = vector["expected"]

        assert chunk_ids == expected["candidate_chunk_ids"], vector["id"]
        assert hashlib.sha256(features.tobytes()).hexdigest() == (
            expected["feature_matrix_sha256"]
        ), vector["id"]
        assert _rank(
            chunk_ids,
            model.predict(features, num_threads=1),
        ) == expected["ltr_ranked_chunk_ids"], vector["id"]
        assert weighted_fallback_order(chunk_ids, features) == (
            expected["weighted_score_ranked_chunk_ids"]
        ), vector["id"]
