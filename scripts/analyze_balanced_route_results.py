#!/usr/bin/env python3
"""Analyze frozen-route results on the balanced scenario blind set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROUTES = ("dense", "sparse", "bm25", "hybrid")
SCENARIOS = ("short_keyword", "exact_identifier", "long_sparse", "dense_paraphrase")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _value_at_10(sample: dict[str, Any]) -> float:
    return next(
        float(value["value"])
        for value in sample["values"]
        if value["name"] == "recall_chunk" and value["k"] == 10
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden-dir", type=Path, required=True)
    parser.add_argument("--dense", type=Path, required=True)
    parser.add_argument("--sparse", type=Path, required=True)
    parser.add_argument("--bm25", type=Path, required=True)
    parser.add_argument("--hybrid", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    scenario_by_id = {
        row["id"]: scenario
        for scenario in SCENARIOS
        for row in _read_jsonl(args.golden_dir / f"{scenario}_blind_45.jsonl")
    }
    result_paths = {route: getattr(args, route) for route in ROUTES}
    hits: dict[str, dict[str, float]] = {}
    overall: dict[str, dict[str, float]] = {}
    for route, path in result_paths.items():
        data = _read_json(path)
        route_hits = {row["sample_id"]: _value_at_10(row) for row in data["per_sample"]}
        if set(route_hits) != set(scenario_by_id):
            raise SystemExit(f"sample mismatch for {route}")
        hits[route] = route_hits
        metric = next(
            row for row in data["metrics"] if row["name"] == "recall_chunk" and row["k"] == 10
        )
        mrr = next(row for row in data["metrics"] if row["name"] == "mrr_chunk")
        overall[route] = {"n": int(metric["n"]), "recall_at_10": metric["mean"], "mrr": mrr["mean"]}

    scenarios: dict[str, dict[str, Any]] = {}
    rows = []
    for scenario in SCENARIOS:
        ids = sorted(sample_id for sample_id, value in scenario_by_id.items() if value == scenario)
        route_recall = {
            route: sum(hits[route][sample_id] for sample_id in ids) / len(ids) for route in ROUTES
        }
        single_oracle = sum(
            any(hits[route][sample_id] for route in ("dense", "sparse", "bm25"))
            for sample_id in ids
        ) / len(ids)
        hybrid_lost = sum(
            not hits["hybrid"][sample_id]
            and any(hits[route][sample_id] for route in ("dense", "sparse", "bm25"))
            for sample_id in ids
        )
        hybrid_unique = sum(
            hits["hybrid"][sample_id]
            and not any(hits[route][sample_id] for route in ("dense", "sparse", "bm25"))
            for sample_id in ids
        )
        best_single = max(("dense", "sparse", "bm25"), key=lambda route: route_recall[route])
        scenarios[scenario] = {
            "n": len(ids),
            **route_recall,
            "best_single": best_single,
            "best_single_recall": route_recall[best_single],
            "single_route_oracle": single_oracle,
            "hybrid_missed_but_single_hit": hybrid_lost,
            "hybrid_unique_hits": hybrid_unique,
        }
        for sample_id in ids:
            rows.append(
                {
                    "id": sample_id,
                    "scenario": scenario,
                    "hit_at_10": {route: hits[route][sample_id] for route in ROUTES},
                }
            )

    output = {
        "overall": overall,
        "scenarios": scenarios,
        "rows": rows,
        "parameters": {
            "fusion": "weighted_score",
            "weights": {"dense": 0.70, "sparse": 0.15, "bm25": 0.15},
            "route_top_k": {"dense": 150, "sparse": 50, "bm25": 100},
            "thresholds": {"dense": 0.30, "sparse": 0.20, "bm25": 0.0},
            "final_top_k": 10,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"overall": overall, "scenarios": scenarios}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
