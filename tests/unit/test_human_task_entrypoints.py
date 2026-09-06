from __future__ import annotations

import json
import runpy
import shutil
from pathlib import Path

import pytest

from linkrag_eval.human_task_entrypoints import (
    validate_human_task_entrypoints,
)


def _write_csv(path: Path, rows: int) -> None:
    lines = ["id,value", *(f"{index},x" for index in range(rows))]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    guide_source = tmp_path / "docs/plans/guide.html"
    guide_source.parent.mkdir(parents=True)
    guide_source.write_text(
        "human_tasks/review-task/relation/ human_tasks/review-task/relation/submission.csv",
        encoding="utf-8",
    )

    canonical = tmp_path / "runs/canonical/relation"
    canonical.mkdir(parents=True)
    for name in ("README.txt", "package_manifest.json"):
        (canonical / name).write_text("x\n", encoding="utf-8")
    _write_csv(canonical / "cases.csv", 2)
    _write_csv(canonical / "submission_template.csv", 2)

    human_task = tmp_path / "human_tasks/review-task"
    human_task.mkdir(parents=True)
    (human_task / "START_HERE.html").symlink_to("../../docs/plans/guide.html")
    (human_task / "relation").symlink_to("../../runs/canonical/relation")

    registry = {
        "schema_version": 1,
        "record_id": "fixture",
        "visible_root": "human_tasks",
        "max_visible_file_components": 4,
        "forbidden_guide_tokens": ["/Users/", "runs/", "data/", "docs/plans/"],
        "active_tasks": [
            {
                "task_id": "review-task",
                "guide": "human_tasks/review-task/START_HERE.html",
                "guide_source": "docs/plans/guide.html",
                "workspaces": [
                    {
                        "name": "relation",
                        "entry": "human_tasks/review-task/relation",
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
                "touchpoint_id": "blind-curation-review",
                "entrypoint_pattern": "human_tasks/blind-curator-<role>",
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
    entry = tmp_path / "human_tasks/review-task/relation"
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


def test_empty_current_registry_does_not_open_historical_workspaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import linkrag_eval.human_task_entrypoints as entrypoints

    def reject_csv_read(path: Path) -> int:
        raise AssertionError(f"empty registry must not open CSV inputs: {path}")

    monkeypatch.setattr(entrypoints, "_csv_data_rows", reject_csv_read)
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "record_id": "empty-fixture",
                "visible_root": "human_tasks",
                "max_visible_file_components": 4,
                "forbidden_guide_tokens": [],
                "active_tasks": [],
                "planned_human_touchpoints": [],
            }
        ),
        encoding="utf-8",
    )
    result = validate_human_task_entrypoints(
        repo_root=tmp_path, registry_path=registry_path, before_handoff=True
    )
    assert result["active_task_count"] == 0
    assert result["workspace_count"] == 0
    assert result["checked_input_count"] == 0
    assert result["planned_touchpoint_count"] == 0


def test_checker_defaults_to_current_registry_without_running_it() -> None:
    root = Path(__file__).resolve().parents[2]
    namespace = runpy.run_path(
        str(root / "scripts/check_human_task_entrypoints.py"),
        run_name="check_entrypoints_test",
    )
    assert namespace["DEFAULT_REGISTRY"] == root / "human_tasks/registry.json"


def test_pre_handoff_rejects_existing_submission(tmp_path: Path) -> None:
    registry_path, _ = _fixture(tmp_path)
    (tmp_path / "runs/canonical/relation/submission.csv").write_text("id,answer\n")
    with pytest.raises(RuntimeError, match="pre-handoff output already exists"):
        validate_human_task_entrypoints(
            repo_root=tmp_path, registry_path=registry_path, before_handoff=True
        )


def test_workspace_rejects_unexpected_files(tmp_path: Path) -> None:
    registry_path, _ = _fixture(tmp_path)
    (tmp_path / "runs/canonical/relation/private-labels.txt").write_text("fixture")
    with pytest.raises(RuntimeError, match="exposes unexpected files"):
        validate_human_task_entrypoints(repo_root=tmp_path, registry_path=registry_path)


def _forbid_csv_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    import linkrag_eval.human_task_entrypoints as entrypoints

    def reject_csv_read(path: Path) -> int:
        raise AssertionError(f"invalid workspace must fail before any CSV read: {path}")

    monkeypatch.setattr(entrypoints, "_csv_data_rows", reject_csv_read)


@pytest.mark.parametrize("file_name", ["cases.csv", "package_manifest.json", "submission.csv"])
@pytest.mark.parametrize("destination", ["other_role", "outside_repo"])
def test_declared_file_symlinks_cannot_escape_workspace_before_csv_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, file_name: str, destination: str
) -> None:
    repo = tmp_path / "repo"
    registry_path, _ = _fixture(repo)
    if destination == "other_role":
        target = repo / "runs/canonical/other-role/private.csv"
    else:
        target = tmp_path / "external/private.csv"
    target.parent.mkdir(parents=True)
    _write_csv(target, 2)
    entry = repo / "runs/canonical/relation" / file_name
    entry.unlink(missing_ok=True)
    entry.symlink_to(target)
    _forbid_csv_reads(monkeypatch)

    with pytest.raises(RuntimeError, match="outside canonical workspace"):
        validate_human_task_entrypoints(repo_root=repo, registry_path=registry_path)


@pytest.mark.parametrize("file_name", ["cases.csv", "submission.csv"])
@pytest.mark.parametrize("target_kind", ["dangling", "directory"])
def test_declared_symlinks_must_resolve_to_existing_files_before_csv_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, file_name: str, target_kind: str
) -> None:
    registry_path, _ = _fixture(tmp_path)
    canonical = tmp_path / "runs/canonical/relation"
    entry = canonical / file_name
    entry.unlink(missing_ok=True)
    target = canonical / "missing" if target_kind == "dangling" else canonical
    entry.symlink_to(target)
    _forbid_csv_reads(monkeypatch)

    with pytest.raises(RuntimeError, match="must resolve to (an existing|a) file"):
        validate_human_task_entrypoints(repo_root=tmp_path, registry_path=registry_path)


@pytest.mark.parametrize("file_name", [".", ".."])
@pytest.mark.parametrize("field", ["required_inputs", "expected_output"])
def test_dot_file_names_are_rejected_before_csv_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, file_name: str, field: str
) -> None:
    registry_path, _ = _fixture(tmp_path)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    workspace = registry["active_tasks"][0]["workspaces"][0]
    if field == "required_inputs":
        workspace[field].append(file_name)
    else:
        workspace[field] = file_name
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    _forbid_csv_reads(monkeypatch)

    with pytest.raises(RuntimeError, match="must be a single file name"):
        validate_human_task_entrypoints(repo_root=tmp_path, registry_path=registry_path)


def test_all_workspaces_are_validated_before_any_csv_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path, guide_source = _fixture(tmp_path)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    canonical = tmp_path / "runs/canonical"
    shutil.copytree(canonical / "relation", canonical / "similarity")
    (tmp_path / "human_tasks/review-task/similarity").symlink_to(
        "../../runs/canonical/similarity"
    )
    workspaces = registry["active_tasks"][0]["workspaces"]
    workspaces.append(
        {
            **workspaces[0],
            "name": "similarity",
            "entry": "human_tasks/review-task/similarity",
            "canonical_target": "runs/canonical/similarity",
        }
    )
    guide_source.write_text(
        guide_source.read_text(encoding="utf-8")
        + " human_tasks/review-task/similarity/"
        + " human_tasks/review-task/similarity/submission.csv",
        encoding="utf-8",
    )
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    (canonical / "similarity/cases.csv").unlink()
    (canonical / "similarity/cases.csv").symlink_to("../relation/cases.csv")
    _forbid_csv_reads(monkeypatch)

    with pytest.raises(RuntimeError, match="outside canonical workspace"):
        validate_human_task_entrypoints(repo_root=tmp_path, registry_path=registry_path)


def test_file_symlinks_inside_canonical_workspace_are_valid(tmp_path: Path) -> None:
    registry_path, _ = _fixture(tmp_path)
    canonical = tmp_path / "runs/canonical/relation"
    (canonical / "cases.csv").unlink()
    (canonical / "cases.csv").symlink_to("submission_template.csv")
    (canonical / "submission.csv").symlink_to("submission_template.csv")

    result = validate_human_task_entrypoints(repo_root=tmp_path, registry_path=registry_path)
    assert result["status"] == "PASS"
    assert result["checked_input_count"] == 4
