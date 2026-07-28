"""测试套件级依赖门禁。"""

from __future__ import annotations

import importlib.util
import os

import pytest


def pytest_configure() -> None:
    """CI 要求生产契约依赖真实存在，禁止 contract 测试静默跳过。"""

    require_rag = os.getenv("LINKRAG_EVAL_REQUIRE_RAG", "").strip().lower()
    if require_rag not in {"1", "true", "yes", "on"}:
        return
    if importlib.util.find_spec("src.core") is None:
        raise pytest.UsageError(
            "LINKRAG_EVAL_REQUIRE_RAG=1，但未安装固定版本的 toLink-Rag（缺少 src.core）"
        )
