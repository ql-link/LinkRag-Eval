#!/usr/bin/env python3
"""Check active human task entrypoints from the current registry.

The default registry does not reactivate historical research tasks. Explicitly
selecting a registry checks its declared files, including CSV input row counts;
this command does not adjudicate answers or execute research stages.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from linkrag_eval.human_task_entrypoints import validate_human_task_entrypoints

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "human_tasks/registry.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument(
        "--before-handoff",
        action="store_true",
        help="also require every expected submission output to be absent",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = validate_human_task_entrypoints(
        repo_root=args.repo_root,
        registry_path=args.registry,
        before_handoff=args.before_handoff,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
