from __future__ import annotations

import json

import pytest

from linkrag_eval.golden_v2.blind_v4 import (
    claim_blind_v4_run,
    freeze_blind_v4,
    seal_blind_v4_result,
)


def _write(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


def test_blind_v4_can_only_run_once(tmp_path) -> None:
    samples = tmp_path / "samples.jsonl"
    _write(
        samples,
        [
            {"id": f"b{i}", "query": f"blind {i}", "provenance": {"source_kind": "opensource"}}
            for i in range(3)
        ],
    )
    tune = tmp_path / "tune.jsonl"
    _write(tune, [{"id": "t1", "query": "tune"}])
    config = tmp_path / "config.json"
    config.write_text("{}")
    out = tmp_path / "blind"
    freeze_blind_v4(
        samples, tune_paths=[tune], frozen_config_paths=[config], out_dir=out, min_samples=3
    )
    claim_blind_v4_run(out, run_id="once")
    with pytest.raises(RuntimeError, match="禁止第二次"):
        claim_blind_v4_run(out, run_id="twice")
    result = tmp_path / "result.json"
    result.write_text("{}")
    assert seal_blind_v4_result(out, result_path=result)["result_sha256"]
