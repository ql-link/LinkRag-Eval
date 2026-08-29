#!/usr/bin/env python3
"""将 Internal v6 DeepSeek 生成与恢复链合并为 A/B 双人盲审包。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from linkrag_eval.robust_fusion.internal_v6_review import materialize_review_package

DEFAULT_RUNS = [
    Path("runs/robust_fusion/internal_v6_deepseek_pilot_v2"),
    Path("runs/robust_fusion/internal_v6_deepseek_pilot_v2_recovery_v1"),
    Path("runs/robust_fusion/internal_v6_deepseek_pilot_v2_recovery_v2"),
    Path("runs/robust_fusion/internal_v6_deepseek_pilot_v2_recovery_v3"),
    Path("runs/robust_fusion/internal_v6_deepseek_pilot_v2_recovery_v4"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("runs/robust_fusion/internal_v6_deepseek_pilot_v2_human_review_v1"),
    )
    parser.add_argument("--run", action="append", type=Path, dest="runs")
    parser.add_argument(
        "--history-root",
        type=Path,
        default=Path("runs/robust_fusion/recovery/blind_v5_structured_v2_rebuild_v1"),
    )
    args = parser.parse_args()
    report = materialize_review_package(
        output_dir=args.output,
        run_roots=args.runs or DEFAULT_RUNS,
        history_root=args.history_root,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
