"""Synthetic checks for no-repeat recovery and honest interrupted-result handling."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def recovery():
    path = Path(__file__).resolve().parents[2] / "runs/post_recall/nevir-test-main-20260911/recover_qwen.py"
    spec = importlib.util.spec_from_file_location("test_recovery_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def incident(recovery, tmp_path):
    metadata = {"prompt_version": "judge_prompt_v1", "model": "synthetic", "effort": "think"}
    items = [{"source_query_id": f"q{i}", "chunk_id": f"c{i}", "pair_id": f"p{i}",
              "query": f"Synthetic question {i}", "passage": f"Synthetic passage {i}",
              "level": "l2"} for i in range(4)]
    original = tmp_path / "original"
    (original / "judge-cache").mkdir(parents=True)
    batches = recovery.driver.plan_batches(items, batch_size=1, seed=7)
    for index, batch in enumerate(batches[:3], 1):
        folder = original / f"batch-{index:05d}"
        folder.mkdir()
        key = recovery.driver.cache_key(batch[0], metadata)
        (folder / "prompt.txt").write_text(recovery.driver.prompt_for(batch))
        recovery.driver.write_json(folder / "schema.json", recovery.driver.SCHEMA)
        recovery.driver.write_rows(folder / "mapping.jsonl", [{"key": key}])
        if index < 3:
            recovery.driver.write_json(folder / "metadata.json", {"request_attempts": 1})
            recovery.driver.write_rows(original / "judge-cache" / f"batch-{index:05d}.jsonl", [
                dict(metadata, key=key, score=4 if index == 1 else None, reason="",
                     status="available" if index == 1 else "unavailable"),
            ])
    return items, metadata, original


def test_recovery_only_calls_never_started_and_preserves_missing_and_duplicate_rows(
    recovery, incident, tmp_path,
):
    items, metadata, original = incident
    completed, interrupted, pending = recovery.inspect_original(items, original, metadata, 7)
    assert (len(completed), len(interrupted), len(pending)) == (2, 1, 1)
    assert pending[0]["index"] == 4
    calls = []

    def run(prompt, folder):
        calls.append(folder.name)
        return {"items": [{"id": "i01", "score": 2, "reason": "synthetic"}]}

    runner = SimpleNamespace(metadata=metadata, run=run)
    output = tmp_path / "continuation"
    recovery.continue_unstarted(pending, runner, original, output, workers=1)
    assert calls == ["batch-00004"]
    rows = recovery.assemble(items + [items[0]], original, output, interrupted, metadata)
    assert len(rows) == 5 and rows[0] == rows[-1]
    by_key = {row["key"]: row for row in rows}
    assert by_key[interrupted[0]["key"]]["recovery_provenance"] == "interrupted_without_receipt"
    assert by_key[interrupted[0]["key"]]["score"] is None
    assert sum(row["status"] == "unavailable" for row in by_key.values()) == 2
    with pytest.raises(FileExistsError):
        recovery.continue_unstarted(pending, runner, original, output, workers=1)
    assert len(calls) == 1


def test_started_input_cannot_be_submitted_again(recovery, incident, tmp_path):
    items, metadata, original = incident
    _, interrupted, _ = recovery.inspect_original(items, original, metadata, 7)
    runner = SimpleNamespace(metadata=metadata, run=lambda *_: pytest.fail("must not request"))
    with pytest.raises(ValueError, match="already has an original"):
        recovery.continue_unstarted(interrupted, runner, original, tmp_path / "new", workers=1)


@pytest.mark.parametrize("failure", ["prompt", "mapping", "attempts", "orphan"])
def test_audit_rejects_inconsistent_original_evidence(recovery, incident, failure):
    items, metadata, original = incident
    folder = original / "batch-00001"
    if failure == "prompt":
        (folder / "prompt.txt").write_text("changed")
    elif failure == "mapping":
        (folder / "mapping.jsonl").write_text(json.dumps({"key": "wrong"}) + "\n")
    elif failure == "attempts":
        (folder / "metadata.json").write_text('{"request_attempts":2}')
    else:
        (original / "judge-cache/batch-00004.jsonl").write_text('{}\n')
    with pytest.raises(ValueError):
        recovery.inspect_original(items, original, metadata, 7)


def test_assembly_rejects_repeated_result_across_segments(recovery, incident, tmp_path):
    items, metadata, original = incident
    continuation = tmp_path / "continuation"
    (continuation / "judge-cache").mkdir(parents=True)
    path = original / "judge-cache/batch-00001.jsonl"
    (continuation / "judge-cache/batch-00001.jsonl").write_bytes(path.read_bytes())
    with pytest.raises(ValueError, match="Duplicate"):
        recovery.assemble(items, original, continuation, [], metadata)


def test_assembly_rejects_uncovered_population(recovery, incident, tmp_path):
    items, metadata, original = incident
    continuation = tmp_path / "continuation"
    (continuation / "judge-cache").mkdir(parents=True)
    with pytest.raises(ValueError, match="fixed population"):
        recovery.assemble(items, original, continuation, [], metadata)
