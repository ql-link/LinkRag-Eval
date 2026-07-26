from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import conftest


def test_ci_dependency_gate_fails_when_rag_is_missing(monkeypatch) -> None:
    monkeypatch.setenv("LINKRAG_EVAL_REQUIRE_RAG", "1")
    monkeypatch.setattr(conftest.importlib.util, "find_spec", lambda _name: None)

    with pytest.raises(pytest.UsageError, match="缺少 src.core"):
        conftest.pytest_configure()


def test_ci_dependency_gate_is_optional_for_local_unit_runs(monkeypatch) -> None:
    monkeypatch.delenv("LINKRAG_EVAL_REQUIRE_RAG", raising=False)
    monkeypatch.setattr(conftest.importlib.util, "find_spec", lambda _name: None)

    conftest.pytest_configure()


def test_golden_package_sources_are_tracked() -> None:
    """防止源码目录再次被评测数据的 gitignore 规则误伤。"""
    repository = Path(__file__).resolve().parents[2]
    if not (repository / ".git").exists():
        pytest.skip("仅在 Git checkout 中校验源码跟踪状态")

    required = [
        "src/linkrag_eval/golden/__init__.py",
        "src/linkrag_eval/golden/corpus_io.py",
        "src/linkrag_eval/golden/loader.py",
        "src/linkrag_eval/golden/gen/gate.py",
        "src/linkrag_eval/golden/opensource/ingest.py",
        "src/linkrag_eval/golden/synth/compose.py",
    ]
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", *required],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
