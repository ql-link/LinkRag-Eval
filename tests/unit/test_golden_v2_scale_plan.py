"""Golden V2 scale plan。"""

from __future__ import annotations

import json

import pytest

from linkrag_eval.golden_v2 import build_scale_plan, count_jsonl


def test_build_scale_plan_writes_batches_and_estimates(tmp_path) -> None:
    report = build_scale_plan(
        stage="scale_100k",
        target_chunks=10_000,
        existing_chunks=2_500,
        batch_chunks=3_000,
        dataset_id_start=991000,
        out_dir=tmp_path,
        query_seed_target=100,
        route_top_n=10,
        random_n=5,
        max_candidates_per_query=30,
        avg_chars_per_chunk=800,
        chars_per_token=2.0,
        judge_input_tokens_per_candidate=500,
        judge_output_tokens_per_candidate=80,
        alt_embedding_batch=128,
    )

    assert report.dataset_ids == [991000, 991001, 991002]
    assert [batch.target_chunks for batch in report.batches] == [3000, 3000, 1500]
    assert report.estimate.missing_chunks == 7500
    assert report.estimate.expected_candidates_per_query == 30
    assert report.estimate.estimated_judge_items == 3000
    assert report.estimate.estimated_alt_embedding_batches == 79
    assert (tmp_path / "scale_plan.json").exists()
    assert (tmp_path / "scale_plan.md").exists()
    assert (tmp_path / "batch_specs.jsonl").exists()

    payload = json.loads((tmp_path / "scale_plan.json").read_text(encoding="utf-8"))
    assert payload["batches"][0]["dataset_id"] == 991000
    assert "linkrag-eval ingest" in "\n".join(payload["batches"][0]["commands"])


def test_build_scale_plan_all_existing_has_no_batches(tmp_path) -> None:
    report = build_scale_plan(
        stage="medium_20k",
        target_chunks=20_000,
        existing_chunks=20_000,
        batch_chunks=5_000,
        dataset_id_start=991100,
        out_dir=tmp_path,
        write_markdown=False,
    )

    assert report.batches == []
    assert report.dataset_ids == []
    assert report.estimate.missing_chunks == 0
    assert report.markdown_path is None
    assert (tmp_path / "scale_plan.json").exists()
    assert (tmp_path / "batch_specs.jsonl").read_text(encoding="utf-8") == ""


def test_count_jsonl_counts_non_empty_lines(tmp_path) -> None:
    path = tmp_path / "chunks.jsonl"
    path.write_text('{"a":1}\n\n{"a":2}\n', encoding="utf-8")

    assert count_jsonl(path) == 2


def test_build_scale_plan_rejects_invalid_values(tmp_path) -> None:
    with pytest.raises(ValueError, match="target_chunks"):
        build_scale_plan(
            stage="bad",
            target_chunks=0,
            dataset_id_start=1,
            out_dir=tmp_path,
        )
