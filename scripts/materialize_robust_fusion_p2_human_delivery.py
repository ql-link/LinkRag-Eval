#!/usr/bin/env python3
"""从冻结的 P2 管理员包生成全新、空白、盲化的双人人工交付目录。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import prepare_robust_fusion_p2_calibration_replay as package

DELIVERY_VERSION = "ROBUST-FUSION-P2-HUMAN-DELIVERY-2026-08-29-v1"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def materialize(repo_root: Path, master_dir: Path, work_root: Path) -> dict[str, Any]:
    if not master_dir.is_dir():
        raise RuntimeError(f"管理员包不存在：{master_dir}")
    if work_root.exists():
        raise RuntimeError(
            "人工工作目录已存在；为保护提交历史，本脚本拒绝覆盖。"
            "请改用新的 --work-root。"
        )

    key_rows = [
        json.loads(line)
        for line in (master_dir / "facilitator_key.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    package.validate_cases(key_rows)
    work_root.mkdir(parents=True)
    package.write_role_package(master_dir, work_root / "annotator_a", key_rows, "A")
    package.write_role_package(master_dir, work_root / "annotator_b", key_rows, "B")
    (work_root / "FACILITATOR_README.md").write_text(
        """# P2 双人人工校准交付说明

本目录是正式团队人工入口，与任何 DeepSeek、模型或工具试填目录相互独立。

1. 将 `annotator_a/` 与 `annotator_b/` 分别交给两名真实标注员；每人只能查看自己的目录。
2. 两人提交前不得互相讨论，也不得接触管理员包中的 `facilitator_key.jsonl`。
3. 每人须完成 12 条案例资格、13 条候选和 1 条候选对；不得增删或换序。
4. 主持人在查看答案键前先锁定两份提交；后续审查只能读取锁定快照。
5. 本包只做 P2 构念校准，不是 Gate A/B 数据或结果。

旧的模型/工具试填不能复制到本目录，也不能计作双人人工提交。
""",
        encoding="utf-8",
    )
    validation = package.validate_existing(repo_root, master_dir, work_root)
    manifest = {
        "delivery_version": DELIVERY_VERSION,
        "formal_human_entry": True,
        "prior_model_or_tool_fills_eligible": False,
        "facilitator_key_included": False,
        "generator": {
            "path": str(Path(__file__).resolve().relative_to(repo_root)),
            "sha256": package.sha256_file(Path(__file__).resolve()),
        },
        **validation,
    }
    write_json(work_root / "delivery_manifest.json", manifest)
    manifest_hash = package.sha256_file(work_root / "delivery_manifest.json")
    (work_root / "delivery_manifest.sha256").write_text(
        f"{manifest_hash}  delivery_manifest.json\n",
        encoding="utf-8",
    )
    return {**manifest, "delivery_manifest_sha256": manifest_hash}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--master-dir",
        type=Path,
        default=Path("data/robust_fusion/derived/p2_calibration_v2"),
    )
    parser.add_argument(
        "--work-root",
        type=Path,
        default=Path("runs/robust_fusion/p2_human_calibration_v2"),
    )
    return parser.parse_args()


def resolve(repo_root: Path, path: Path) -> Path:
    return (path if path.is_absolute() else repo_root / path).resolve()


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    result = materialize(
        repo_root,
        resolve(repo_root, args.master_dir),
        resolve(repo_root, args.work_root),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
