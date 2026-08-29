#!/usr/bin/env python3
"""准备或一次性执行 Internal Stress v6 adjudicated Dev 三路检索证据。"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from linkrag_eval.config import EvalSettings
from linkrag_eval.robust_fusion.internal_v6_route_evidence import (
    DEFAULT_DATASET_ID,
    execute_run,
    prepare_run,
)


def resolve_in_repo(repo_root: Path, path: Path) -> Path:
    resolved = (path if path.is_absolute() else repo_root / path).resolve()
    if not resolved.is_relative_to(repo_root):
        raise RuntimeError(f"路径必须位于仓库内：{resolved}")
    return resolved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="只做本地输入/配置校验并冻结脱敏执行计划")
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--dataset-id", type=int, default=DEFAULT_DATASET_ID)
    prepare.add_argument(
        "--release",
        type=Path,
        default=Path(
            "data/robust_fusion/internal_stress_v6/dev/releases/"
            "adjudicated_synthetic_v1"
        ),
    )
    prepare.add_argument("--output", type=Path, required=True)

    execute = sub.add_parser("execute", help="按 prepared plan 执行一次；失败不自动重试")
    execute.add_argument("--plan", type=Path, required=True)
    execute.add_argument("--confirmation", required=True)
    return parser.parse_args()


async def _execute(args: argparse.Namespace, repo_root: Path) -> dict:
    return await execute_run(
        repo_root=repo_root,
        plan_path=resolve_in_repo(repo_root, args.plan),
        confirmation=args.confirmation,
        settings=EvalSettings(),
        progress=lambda message: print(message, flush=True),
    )


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    if args.command == "prepare":
        result = prepare_run(
            repo_root=repo_root,
            release_root=resolve_in_repo(repo_root, args.release),
            output_root=resolve_in_repo(repo_root, args.output),
            run_id=args.run_id,
            dataset_id=args.dataset_id,
            settings=EvalSettings(),
        )
    else:
        result = asyncio.run(_execute(args, repo_root))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
