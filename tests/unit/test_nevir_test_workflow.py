"""Test handoff guards and continuous-score handling with synthetic data only."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def workflow():
    path = Path(__file__).resolve().parents[2] / "runs/post_recall/nevir-test-main-20260911/workflow.py"
    spec = importlib.util.spec_from_file_location("nevir_test_workflow", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_config_guard_requires_committed_exact_bytes(workflow, tmp_path, monkeypatch):
    monkeypatch.setattr(workflow, "ROOT", tmp_path)
    monkeypatch.setattr(workflow, "FOLDER", tmp_path / "run")
    (tmp_path / "run/bge").mkdir(parents=True)
    for name in ("frozen-config.json", "bge/execution-config.json"):
        (tmp_path / "run" / name).write_bytes(b"frozen\n")
    reply = SimpleNamespace(returncode=0, stdout=b"frozen\n")
    monkeypatch.setattr(workflow.subprocess, "run", lambda *args, **kwargs: reply)
    workflow.require_committed_configs()
    reply.stdout = b"older\n"
    with pytest.raises(RuntimeError, match="committed unchanged"):
        workflow.require_committed_configs()
    reply.returncode = 128
    with pytest.raises(RuntimeError, match="committed unchanged"):
        workflow.require_committed_configs()


def bge_row(cid="x", score=-3.125):
    return {"source_query_id": "q", "chunk_id": cid, "role": "test", "status": "available",
            "model": "fixed-bge", "revision": "rev", "score": score}


def test_bge_projection_keeps_raw_logits_and_ignores_other_level_items(workflow):
    items = [{"source_query_id": "q", "chunk_id": "x"}]
    raw = [bge_row(), bge_row("y", 9.75)]
    config = {"model": {"repository": "fixed-bge", "revision": "rev"}}
    assert workflow.select_bge_scores(items, raw, config) == {"q": {"x": -3.125}}


@pytest.mark.parametrize("change", [
    {"role": "confirmation"}, {"score": float("nan")}, {"score": True},
    {"revision": "other"}, {"status": "unavailable"},
])
def test_bge_projection_rejects_wrong_score_contract(workflow, change):
    config = {"model": {"repository": "fixed-bge", "revision": "rev"}}
    with pytest.raises(ValueError, match="frozen contract"):
        workflow.select_bge_scores(
            [{"source_query_id": "q", "chunk_id": "x"}], [dict(bge_row(), **change)], config,
        )


@pytest.mark.parametrize("raw", [[], [bge_row(), bge_row()]])
def test_bge_projection_rejects_missing_or_duplicate_identities(workflow, raw):
    with pytest.raises(ValueError, match="identities"):
        workflow.select_bge_scores(
            [{"source_query_id": "q", "chunk_id": "x"}], raw,
            {"model": {"repository": "fixed-bge", "revision": "rev"}},
        )


@pytest.mark.parametrize("returncode", [0, 17])
def test_remote_worker_records_exit_without_retry_and_refuses_second_start(
    workflow, tmp_path, monkeypatch, returncode,
):
    monkeypatch.setattr(workflow, "FOLDER", tmp_path)
    monkeypatch.setattr(workflow, "ROOT", tmp_path)
    monkeypatch.setattr(workflow, "read_config", lambda: {"experiment_driver": "driver.py"})
    calls = []

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=returncode)

    monkeypatch.setattr(workflow.subprocess, "run", run)
    assert workflow.qwen_worker("frozen-commit") == returncode
    record = json.loads((tmp_path / "process-exit.json").read_text())
    assert record["returncode"] == returncode
    assert record["code_commit"] == "frozen-commit"
    assert record["status"] == ("completed" if returncode == 0 else "failed_no_retry")
    with pytest.raises(FileExistsError):
        workflow.qwen_worker("frozen-commit")
    assert len(calls) == 1
