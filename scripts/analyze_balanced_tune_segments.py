#!/usr/bin/env python3
"""Aggregate cached tune route hits by the four balanced scenarios."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


SCENARIOS = ("short_keyword", "exact_identifier", "long_sparse", "dense_paraphrase")
ROUTE_KEYS = {
    "dense": "dense_only",
    "sparse": "sparse_only",
    "bm25": "bm25_only",
    "hybrid": "hybrid_070_015_015",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden-dir", type=Path, required=True)
    parser.add_argument("--route-analysis", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    scenario_by_id = {
        row["id"]: scenario
        for scenario in SCENARIOS
        for line in (args.golden_dir / f"{scenario}_tune_105.jsonl").read_text(encoding="utf-8").splitlines()
        if line
        for row in [json.loads(line)]
    }
    data = json.loads(args.route_analysis.read_text(encoding="utf-8"))
    scenarios = {}
    for scenario in SCENARIOS:
        rows = [row for row in data["rows"] if scenario_by_id[row["id"]] == scenario]
        n = len(rows)
        values = {
            route: sum(row["hit_at_10"][key] for row in rows) / n
            for route, key in ROUTE_KEYS.items()
        }
        values["oracle"] = sum(
            any(row["hit_at_10"][ROUTE_KEYS[route]] for route in ("dense", "sparse", "bm25"))
            for row in rows
        ) / n
        values["hybrid_missed_but_single_hit"] = sum(
            not row["hit_at_10"][ROUTE_KEYS["hybrid"]]
            and any(row["hit_at_10"][ROUTE_KEYS[route]] for route in ("dense", "sparse", "bm25"))
            for row in rows
        )
        scenarios[scenario] = {"n": n, **values}
    args.out.write_text(
        json.dumps({"scenarios": scenarios}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(scenarios, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
