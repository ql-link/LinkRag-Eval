from __future__ import annotations

import importlib.util
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
        assert report.relative_to(ROOT).as_posix() in content
