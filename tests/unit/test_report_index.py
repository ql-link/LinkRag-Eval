from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/build_report_index.py"


def _module():
    spec = importlib.util.spec_from_file_location("build_report_index", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stage_classification_is_not_captured_by_golden_v2_root() -> None:
    module = _module()

    corpus = ROOT / "runs/golden_v2/scale_100k_991004/batch/corpus/export_report.json"
    evaluation = ROOT / "runs/golden_v2/eval_pilot/results/pilot.json"
    candidate = ROOT / "runs/golden_v2/candidates/candidate_pool_report.json"

    assert module._stage(corpus).startswith("01 ")
    assert module._stage(candidate).startswith("02 ")
    assert module._stage(evaluation).startswith("03 ")


def test_render_index_links_every_discovered_report() -> None:
    module = _module()
    reports = module.discover_reports()
    content = module.render_index(reports)

    assert reports
    assert f"当前共收录 **{len(reports)}**" in content
    for report in reports:
        target = Path(os.path.relpath(report, ROOT / "docs/reports")).as_posix()
        assert f"(<{target}>)" in content


def test_report_choices_distinguish_development_diagnostics_and_historical_delivery() -> None:
    module = _module()
    reports = [ROOT / "docs/reports" / name for name in (
        "nevir_english_features_2026_09_07.md",
        "nevir_offline_diagnostic_2026_09_07.md",
        "blind_v5_production_contract_acceptance_2026_07_28.md",
    )]
    content = module.render_index(reports)

    assert "## 英文研究与 NevIR" in content
    assert "## 历史工程交付与恢复" in content
    assert "同监督、同配置的开发对照；不属于独立验证" in content
    assert "§7 为中文／英文基线；机械诊断" in content
    assert "中文基线的原生产契约如何验收" in content
    assert "阶段说明或人读版结果摘要" not in content


def test_markdown_and_html_variants_share_one_choice_and_keep_both_links() -> None:
    module = _module()
    reports = [ROOT / "docs/reports" / f"fusion_strategy_comparison_2026_07_02.{suffix}"
               for suffix in ("html", "md")]
    content = module.render_index(reports)

    assert "当前共收录 **2** 个产物，按 **1** 个题目展示" in content
    rows = [line for line in content.splitlines() if "RRF 与 weighted_score 怎样比较" in line]
    assert len(rows) == 1
    assert "[MD](<fusion_strategy_comparison_2026_07_02.md>)" in rows[0]
    assert "[HTML](<fusion_strategy_comparison_2026_07_02.html>)" in rows[0]


def test_unreviewed_report_is_not_assumed_to_be_current_evidence() -> None:
    module = _module()
    report = ROOT / "docs/reports/nevir_future_experiment.md"
    content = module.render_index([report])

    assert "## 待补选读说明" in content
    assert "尚未填写实验范围与证据用途" in content
    assert "nevir_future_experiment.md" in content
    assert "## 英文研究与 NevIR" not in content


def test_same_named_machine_artifacts_in_different_runs_stay_separate() -> None:
    module = _module()
    reports = [ROOT / f"runs/golden_v2/{run}/summary.json" for run in ("first", "second")]
    content = module.render_index(reports, ROOT / "custom-index.md")

    assert "按 **2** 个题目展示" in content
    for run in ("first", "second"):
        assert f"(<runs/golden_v2/{run}/summary.json>)" in content
    assert "[当前状态](docs/CURRENT_STATUS.md)" in content


def test_check_detects_changes_without_writing_reports_or_index(tmp_path, monkeypatch) -> None:
    module = _module()
    source = tmp_path / "docs/reports"
    source.mkdir(parents=True)
    report = source / "new-study.md"
    report.write_text("# Original result\n")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "REPORT_ROOTS", (source,))
    output = source / "REPORT_INDEX.md"
    command = [str(SCRIPT), "--output", str(output)]
    monkeypatch.setattr(sys, "argv", command + ["--check"])
    assert module.main() == 1
    assert not output.exists()

    monkeypatch.setattr(sys, "argv", command)
    assert module.main() == 0
    saved = output.read_bytes()
    monkeypatch.setattr(sys, "argv", command + ["--check"])
    assert module.main() == 0
    (source / "another-study.md").write_text("# Another result\n")
    assert module.main() == 1
    assert output.read_bytes() == saved
    assert report.read_text() == "# Original result\n"
