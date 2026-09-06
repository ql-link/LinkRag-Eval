"""Validate registry-defined shallow, role-isolated human task entrypoints."""

from __future__ import annotations

import csv
import json
from pathlib import Path, PurePosixPath
from typing import Any


def _require_mapping(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{field} must be an object")
    return value


def _require_list(value: object, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError(f"{field} must be a list")
    return value


def _safe_relative(value: object, *, field: str) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{field} must be a non-empty relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise RuntimeError(f"{field} must not be absolute or traverse parents: {value}")
    return path


def _within_repo(repo_root: Path, path: Path, *, field: str) -> Path:
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(repo_root.resolve(strict=True))
    except ValueError as exc:
        raise RuntimeError(f"{field} resolves outside repository: {resolved}") from exc
    return resolved


def _file_name(value: object, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or "\x00" in value
    ):
        raise RuntimeError(f"{field} must be a single file name")
    return value


def _within_workspace_file(workspace: Path, path: Path, *, field: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RuntimeError(f"{field} must resolve to an existing file") from exc
    try:
        resolved.relative_to(workspace)
    except ValueError as exc:
        raise RuntimeError(f"{field} resolves outside canonical workspace: {resolved}") from exc
    if not resolved.is_file():
        raise RuntimeError(f"{field} must resolve to a file")
    return resolved


def _csv_data_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            next(reader)
        except StopIteration as exc:
            raise RuntimeError(f"CSV is empty: {path}") from exc
        return sum(1 for _ in reader)


def validate_human_task_entrypoints(
    *,
    repo_root: Path,
    registry_path: Path,
    before_handoff: bool = False,
) -> dict[str, object]:
    """Validate registered human-facing paths without parsing submission answers.

    Every declared input and present output must resolve to a file inside its
    own canonical workspace. All workspace paths are checked before any CSV row
    counts are read; existing or dangling output symlinks are checked as well.
    """

    root = repo_root.resolve(strict=True)
    registry = _require_mapping(
        json.loads(registry_path.read_text(encoding="utf-8")), field="registry"
    )
    if registry.get("schema_version") != 1:
        raise RuntimeError("registry schema_version must be 1")

    visible_root = _safe_relative(registry.get("visible_root"), field="visible_root")
    if len(visible_root.parts) != 1:
        raise RuntimeError("visible_root must be exactly one project-root directory")
    max_components = registry.get("max_visible_file_components")
    if not isinstance(max_components, int) or max_components < 3:
        raise RuntimeError("max_visible_file_components must be an integer >= 3")

    forbidden_tokens = _require_list(
        registry.get("forbidden_guide_tokens"), field="forbidden_guide_tokens"
    )
    if not all(isinstance(token, str) and token for token in forbidden_tokens):
        raise RuntimeError("forbidden_guide_tokens must contain non-empty strings")

    task_ids: set[str] = set()
    workspace_count = 0
    checked_inputs = 0
    csv_checks: list[tuple[Path, int, str]] = []
    active_tasks = _require_list(registry.get("active_tasks"), field="active_tasks")
    for task_index, raw_task in enumerate(active_tasks):
        task = _require_mapping(raw_task, field=f"active_tasks[{task_index}]")
        task_id = task.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise RuntimeError(f"active_tasks[{task_index}].task_id must be non-empty")
        if task_id in task_ids:
            raise RuntimeError(f"duplicate task_id: {task_id}")
        task_ids.add(task_id)

        guide_rel = _safe_relative(task.get("guide"), field=f"{task_id}.guide")
        source_rel = _safe_relative(task.get("guide_source"), field=f"{task_id}.guide_source")
        if guide_rel.parts[:1] != visible_root.parts:
            raise RuntimeError(f"{task_id}.guide must live under {visible_root}")
        if len(guide_rel.parts) > max_components:
            raise RuntimeError(f"human guide path is too deep: {guide_rel}")

        guide = root / guide_rel
        source = root / source_rel
        if not guide.is_symlink():
            raise RuntimeError(f"human guide must be a symlink, not a copy: {guide_rel}")
        if _within_repo(root, guide, field=f"{task_id}.guide") != _within_repo(
            root, source, field=f"{task_id}.guide_source"
        ):
            raise RuntimeError(f"human guide symlink target mismatch: {guide_rel}")
        guide_text = source.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            if token in guide_text:
                raise RuntimeError(f"human guide exposes forbidden path token {token!r}")

        workspaces = _require_list(task.get("workspaces"), field=f"{task_id}.workspaces")
        if not workspaces:
            raise RuntimeError(f"{task_id} must expose at least one workspace")
        workspace_names: set[str] = set()
        for workspace_index, raw_workspace in enumerate(workspaces):
            workspace = _require_mapping(
                raw_workspace, field=f"{task_id}.workspaces[{workspace_index}]"
            )
            name = workspace.get("name")
            if not isinstance(name, str) or not name or name in workspace_names:
                raise RuntimeError(f"{task_id} workspace names must be unique and non-empty")
            workspace_names.add(name)

            entry_rel = _safe_relative(workspace.get("entry"), field=f"{task_id}.{name}.entry")
            target_rel = _safe_relative(
                workspace.get("canonical_target"),
                field=f"{task_id}.{name}.canonical_target",
            )
            expected_prefix = visible_root.parts + (task_id,)
            if entry_rel.parts[:2] != expected_prefix:
                raise RuntimeError(
                    f"{task_id}.{name}.entry must be directly under human_tasks/{task_id}"
                )

            entry = root / entry_rel
            target = _within_repo(
                root, root / target_rel, field=f"{task_id}.{name}.canonical_target"
            )
            if not target.is_dir():
                raise RuntimeError(f"{task_id}.{name}.canonical_target must be a directory")
            if not entry.is_symlink():
                raise RuntimeError(f"human workspace must be a symlink, not a copy: {entry_rel}")
            if _within_repo(root, entry, field=f"{task_id}.{name}.entry") != target:
                raise RuntimeError(f"human workspace symlink target mismatch: {entry_rel}")

            required_inputs = _require_list(
                workspace.get("required_inputs"), field=f"{task_id}.{name}.required_inputs"
            )
            expected_output = _file_name(
                workspace.get("expected_output"), field=f"{task_id}.{name}.expected_output"
            )
            allowed_names = {expected_output}
            input_paths: dict[str, Path] = {}
            for raw_name in required_inputs:
                raw_name = _file_name(raw_name, field=f"{task_id}.{name} required input")
                allowed_names.add(raw_name)
                visible_file = PurePosixPath(entry_rel, raw_name)
                if len(visible_file.parts) > max_components:
                    raise RuntimeError(f"human-visible path is too deep: {visible_file}")
                input_paths[raw_name] = _within_workspace_file(
                    target, target / raw_name, field=f"{task_id}.{name}/{raw_name}"
                )
                checked_inputs += 1

            visible_output = PurePosixPath(entry_rel, expected_output)
            if len(visible_output.parts) > max_components:
                raise RuntimeError(f"human-visible output path is too deep: {visible_output}")
            output_path = target / expected_output
            if output_path.exists() or output_path.is_symlink():
                _within_workspace_file(
                    target, output_path, field=f"{task_id}.{name}/{expected_output}"
                )
                if before_handoff:
                    raise RuntimeError(
                        f"pre-handoff output already exists: {target_rel / expected_output}"
                    )

            actual_names = {path.name for path in target.iterdir()}
            unexpected_names = sorted(actual_names - allowed_names)
            if unexpected_names:
                raise RuntimeError(f"{task_id}.{name} exposes unexpected files: {unexpected_names}")

            expected_rows = workspace.get("expected_rows")
            if not isinstance(expected_rows, int) or expected_rows <= 0:
                raise RuntimeError(f"{task_id}.{name}.expected_rows must be positive")
            for csv_name in ("cases.csv", "submission_template.csv"):
                if csv_name not in required_inputs:
                    continue
                csv_checks.append(
                    (input_paths[csv_name], expected_rows, f"{task_id}.{name}/{csv_name}")
                )

            entry_text = entry_rel.as_posix()
            output_text = visible_output.as_posix()
            if entry_text not in guide_text or output_text not in guide_text:
                raise RuntimeError(
                    f"guide does not name shallow workspace/output for {task_id}.{name}"
                )
            workspace_count += 1

    planned_ids: set[str] = set()
    planned = _require_list(
        registry.get("planned_human_touchpoints"), field="planned_human_touchpoints"
    )
    for index, raw_touchpoint in enumerate(planned):
        touchpoint = _require_mapping(raw_touchpoint, field=f"planned_human_touchpoints[{index}]")
        touchpoint_id = touchpoint.get("touchpoint_id")
        if not isinstance(touchpoint_id, str) or not touchpoint_id:
            raise RuntimeError(f"planned_human_touchpoints[{index}] needs touchpoint_id")
        if touchpoint_id in planned_ids:
            raise RuntimeError(f"duplicate touchpoint_id: {touchpoint_id}")
        planned_ids.add(touchpoint_id)
        pattern = touchpoint.get("entrypoint_pattern")
        if not isinstance(pattern, str) or not pattern.startswith(f"{visible_root}/"):
            raise RuntimeError(
                f"planned entrypoint must start with {visible_root}/: {touchpoint_id}"
            )
        if touchpoint.get("human_entry_required_before_handoff") is not True:
            raise RuntimeError(f"planned touchpoint lacks required handoff gate: {touchpoint_id}")
        if "blind" in touchpoint_id and touchpoint.get("workspace_scope") != "curator_only":
            raise RuntimeError(f"Blind human task must be curator_only: {touchpoint_id}")

    for csv_path, expected_rows, field in csv_checks:
        actual_rows = _csv_data_rows(csv_path)
        if actual_rows != expected_rows:
            raise RuntimeError(f"{field} rows {actual_rows} != {expected_rows}")

    return {
        "status": "PASS",
        "record_id": registry.get("record_id"),
        "active_task_count": len(active_tasks),
        "workspace_count": workspace_count,
        "checked_input_count": checked_inputs,
        "planned_touchpoint_count": len(planned),
        "before_handoff": before_handoff,
    }
