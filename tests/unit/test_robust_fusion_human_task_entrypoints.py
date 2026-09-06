from __future__ import annotations

import json
from pathlib import Path

import pytest

from linkrag_eval.robust_fusion.human_task_entrypoints import (
    validate_human_task_entrypoints,
)


def _write_csv(path: Path, rows: int) -> None:
    lines = ["id,value", *(f"{index},x" for index in range(rows))]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    guide_source = tmp_path / "docs/plans/guide.html"
    guide_source.parent.mkdir(parents=True)
    guide_source.write_text(
        "human_tasks/r2-adjudication/relation/ human_tasks/r2-adjudication/relation/submission.csv",
        encoding="utf-8",
    )

    canonical = tmp_path / "runs/canonical/relation"
    canonical.mkdir(parents=True)
    for name in ("README.txt", "package_manifest.json"):
        (canonical / name).write_text("x\n", encoding="utf-8")
    _write_csv(canonical / "cases.csv", 2)
    _write_csv(canonical / "submission_template.csv", 2)

    human_task = tmp_path / "human_tasks/r2-adjudication"
    human_task.mkdir(parents=True)
    (human_task / "START_HERE.html").symlink_to("../../docs/plans/guide.html")
    (human_task / "relation").symlink_to("../../runs/canonical/relation")

    registry = {
        "schema_version": 1,
        "record_id": "fixture",
        "visible_root": "human_tasks",
        "max_visible_file_components": 4,
        "forbidden_guide_tokens": ["/Users/", "runs/", "data/robust_fusion/", "docs/plans/"],
        "active_tasks": [
            {
                "task_id": "r2-adjudication",
                "guide": "human_tasks/r2-adjudication/START_HERE.html",
                "guide_source": "docs/plans/guide.html",
                "workspaces": [
                    {
                        "name": "relation",
                        "entry": "human_tasks/r2-adjudication/relation",
                        "canonical_target": "runs/canonical/relation",
                        "required_inputs": [
                            "README.txt",
                            "cases.csv",
                            "package_manifest.json",
                            "submission_template.csv",
                        ],
                        "expected_output": "submission.csv",
                        "expected_rows": 2,
                    }
                ],
            }
        ],
        "planned_human_touchpoints": [
            {
                "touchpoint_id": "gateb-blind-curation-review",
                "entrypoint_pattern": "human_tasks/gateb-curator-<role>",
                "workspace_scope": "curator_only",
                "human_entry_required_before_handoff": True,
            }
        ],
    }
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    return registry_path, guide_source


def test_shallow_symlinked_entrypoint_passes(tmp_path: Path) -> None:
    registry_path, _ = _fixture(tmp_path)
    result = validate_human_task_entrypoints(
        repo_root=tmp_path,
        registry_path=registry_path,
        before_handoff=True,
    )
    assert result["status"] == "PASS"
    assert result["checked_input_count"] == 4


def test_guide_rejects_canonical_machine_path(tmp_path: Path) -> None:
    registry_path, guide_source = _fixture(tmp_path)
    guide_source.write_text("runs/canonical/relation/submission.csv", encoding="utf-8")
    with pytest.raises(RuntimeError, match="forbidden path token"):
        validate_human_task_entrypoints(repo_root=tmp_path, registry_path=registry_path)


def test_workspace_copy_is_rejected(tmp_path: Path) -> None:
    registry_path, _ = _fixture(tmp_path)
    entry = tmp_path / "human_tasks/r2-adjudication/relation"
    entry.unlink()
    entry.mkdir()
    with pytest.raises(RuntimeError, match="must be a symlink"):
        validate_human_task_entrypoints(repo_root=tmp_path, registry_path=registry_path)


def test_blind_touchpoint_requires_curator_only_scope(tmp_path: Path) -> None:
    registry_path, _ = _fixture(tmp_path)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["planned_human_touchpoints"][0]["workspace_scope"] = "shared_dev_workspace"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    with pytest.raises(RuntimeError, match="must be curator_only"):
        validate_human_task_entrypoints(repo_root=tmp_path, registry_path=registry_path)
