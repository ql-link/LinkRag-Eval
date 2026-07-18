"""Golden V2 pilot preflight/plan。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from linkrag_eval.golden_v2 import build_pilot_plan, run_pilot_preflight


def _write_jsonl(path, n: int) -> None:
    rows = [{"seed_id": f"q{i}", "query": f"问题 {i}", "source": "log"} for i in range(n)]
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _settings(**overrides):
    base = {
        "db_name": "tolink_rag_eval_db",
        "qdrant_prefix": "eval_kb_bucket",
        "judge_base_url": "https://judge/chat/completions",
        "judge_api_key": "secret",
        "judge_model": "deepseek",
        "embed_model": "current-embed",
        "alt_embed_provider": "openai",
        "alt_embed_base_url": "https://alt/embeddings",
        "alt_embed_api_key": "secret",
        "alt_embed_model": "alt-embed",
        "bm25_mode": "sqlite_fts5",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_pilot_preflight_passes_with_independent_alt_and_reviewer(tmp_path) -> None:
    seeds = tmp_path / "query_seeds.jsonl"
    _write_jsonl(seeds, 2)

    report = run_pilot_preflight(
        settings=_settings(),
        seeds_path=seeds,
        dataset_ids=[990901],
        reviewer_model="other-reviewer",
        min_seed_count=2,
        report_out=tmp_path / "preflight.json",
        markdown_out=tmp_path / "preflight.md",
    )

    assert report.status == "pass"
    assert any("bm25-backfill" in action for action in report.next_actions)
    assert any("candidate-pool-live" in action for action in report.next_actions)
    assert (tmp_path / "preflight.json").exists()
    assert (tmp_path / "preflight.md").exists()


def test_pilot_preflight_fails_without_alt_config(tmp_path) -> None:
    seeds = tmp_path / "query_seeds.jsonl"
    _write_jsonl(seeds, 2)

    report = run_pilot_preflight(
        settings=_settings(alt_embed_api_key="", alt_embed_model=""),
        seeds_path=seeds,
        dataset_ids=[990901],
        reviewer_model="deepseek",
        min_seed_count=2,
    )

    by_name = {check.name: check for check in report.checks}
    assert report.status == "fail"
    assert by_name["alt_embedding_config"].status == "fail"
    assert by_name["reviewer_model"].status == "warn"
    assert any("EVAL_ALT_EMBED_PROVIDER" in action for action in report.next_actions)


def test_pilot_preflight_accepts_bge_alt_without_key(tmp_path) -> None:
    seeds = tmp_path / "query_seeds.jsonl"
    _write_jsonl(seeds, 2)

    report = run_pilot_preflight(
        settings=_settings(
            alt_embed_provider="bge_m3_http",
            alt_embed_api_key="",
            alt_embed_base_url="http://bge/encode",
            alt_embed_model="BAAI/bge-m3",
        ),
        seeds_path=seeds,
        dataset_ids=[990901],
        reviewer_model="reviewer",
        min_seed_count=2,
    )

    assert report.status == "pass"


def test_build_pilot_plan_writes_commands_and_medium_plan_step(tmp_path) -> None:
    report = build_pilot_plan(
        out_dir=tmp_path / "pilot",
        dataset_ids=[990901],
        reviewer_model="reviewer-x",
        raw_query_input="data/raw_queries.jsonl",
        source="support",
        id_field="qid",
        limit_queries=20,
    )

    script = (tmp_path / "pilot" / "pilot_commands.sh").read_text(encoding="utf-8")
    assert report.dataset_ids == [990901]
    assert "golden-v2 seed-import" in script
    assert "golden-v2 pilot-preflight" in script
    assert "golden-v2 candidate-pool-live" in script
    assert "--sources bm25,dense,sparse,alt_embedding" in script
    assert "--alt-score-threshold -1.0" in script
    assert "golden-v2 adjudicate" in script
    assert "--policy manual_on_conflict" in script
    assert "golden-v2 scale-plan" in script
    assert "--stage medium_20k" in script
    assert "--limit-queries 20" in script
    assert (tmp_path / "pilot" / "pilot_plan.json").exists()


def test_build_pilot_plan_requires_input_or_seeds(tmp_path) -> None:
    with pytest.raises(ValueError, match="至少提供一个"):
        build_pilot_plan(
            out_dir=tmp_path,
            dataset_ids=[990901],
            reviewer_model="reviewer",
        )
