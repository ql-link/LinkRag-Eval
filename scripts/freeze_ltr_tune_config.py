#!/usr/bin/env python3
"""Freeze final LambdaMART iterations and protection using Tune OOF only."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from linkrag_eval.retrieval.candidate_routing import (
    BASELINE_THRESHOLDS,
    FROZEN_ROUTING_DEPTHS,
    GLOBAL_FALLBACK_DEPTHS,
)
from linkrag_eval.retrieval.learning_to_rank.experiment import tune_hybrid_protection


def freeze_config(cv: dict, *, seed: int) -> dict:
    iterations = [
        int(row["best_iteration"]) for row in cv["fold_reports"] if int(row["best_iteration"]) > 0
    ]
    if not iterations:
        raise ValueError("cross-validation report has no positive best_iteration")
    protection = tune_hybrid_protection(cv["predictions"])
    return {
        "selection_source": "Tune OOF only",
        "feature_version": cv["feature_version"],
        "seed": seed,
        "n_estimators": max(1, round(statistics.median(iterations))),
        "fold_best_iterations": iterations,
        "blend_alpha": float(protection["best"]["blend_alpha"]),
        "protect_baseline_top_k": int(protection["best"]["protect_baseline_top_k"]),
        "tune_protection_result": protection,
        "candidate_routing": {
            "global_fallback": GLOBAL_FALLBACK_DEPTHS.as_dict(),
            "profiles": {key: value.as_dict() for key, value in FROZEN_ROUTING_DEPTHS.items()},
            "thresholds": BASELINE_THRESHOLDS,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cv-report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260720)
    args = parser.parse_args()

    config = freeze_config(
        json.loads(args.cv_report.read_text(encoding="utf-8")),
        seed=args.seed,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(config, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
