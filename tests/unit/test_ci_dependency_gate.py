from __future__ import annotations

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
