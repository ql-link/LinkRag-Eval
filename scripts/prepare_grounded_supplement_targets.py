#!/usr/bin/env python3
"""Prepare unused source chunks for balanced scenario supplements."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCENARIO_COUNTS = {
    "short_keyword": 28,
    "dense_paraphrase": 12,
    "long_sparse": 72,
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _stable_key(scenario: str, row: dict[str, Any]) -> str:
    raw = f"{scenario}:{row['dataset_id']}:{row['chunk_id']}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _quotas(total: int, dataset_ids: list[int]) -> dict[int, int]:
    base, remainder = divmod(total, len(dataset_ids))
    return {
        dataset_id: base + int(index < remainder)
        for index, dataset_id in enumerate(dataset_ids)
    }


def select_targets(
    chunk_paths: list[Path],
    *,
    excluded_chunk_ids: set[str],
    scenario_counts: dict[str, int],
) -> dict[str, list[dict[str, Any]]]:
    chunks = [row for path in chunk_paths for row in _read_jsonl(path)]
    dataset_ids = sorted({int(row["dataset_id"]) for row in chunks})
    used = set(excluded_chunk_ids)
    result: dict[str, list[dict[str, Any]]] = {}
    for scenario, count in scenario_counts.items():
        selected: list[dict[str, Any]] = []
        for dataset_id, quota in _quotas(count, dataset_ids).items():
            eligible = [
                row
                for row in chunks
                if int(row["dataset_id"]) == dataset_id
                and row["chunk_id"] not in used
                and len(str(row.get("content") or "")) >= 120
            ]
            eligible.sort(key=lambda row: _stable_key(scenario, row))
            picked = []
            seen_scenarios: set[str] = set()
            for row in eligible:
                source_scenario = str(row.get("metadata", {}).get("scenario") or "")
                if source_scenario and source_scenario in seen_scenarios:
                    continue
                picked.append(row)
                seen_scenarios.add(source_scenario)
                if len(picked) == quota:
                    break
            if len(picked) < quota:
                for row in eligible:
                    if row not in picked:
                        picked.append(row)
                        if len(picked) == quota:
                            break
            if len(picked) < quota:
                raise SystemExit(f"{scenario}/{dataset_id}: insufficient target chunks")
            selected.extend(picked)
            used.update(str(row["chunk_id"]) for row in picked)

        prefix = {
            "short_keyword": "short",
            "dense_paraphrase": "dense",
            "long_sparse": "long",
        }[scenario]
        result[scenario] = [
            {
                "query_id": f"balanced-{prefix}-supp-{index:04d}",
                "dataset_id": int(row["dataset_id"]),
                "doc_id": int(row["doc_id"]),
                "chunk_id": str(row["chunk_id"]),
                "content": str(row["content"]),
                "domain": row.get("metadata", {}).get("domain"),
                "scenario": row.get("metadata", {}).get("scenario"),
                "type_hint": scenario,
            }
            for index, row in enumerate(selected, start=1)
        ]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", action="append", type=Path, required=True)
    parser.add_argument("--exclude-targets", action="append", type=Path, default=[])
    parser.add_argument("--exclude-judgments", action="append", type=Path, default=[])
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=5)
    args = parser.parse_args()

    excluded = {
        str(row.get("chunk_id") or row.get("target_chunk_id"))
        for path in args.exclude_targets
        for row in _read_jsonl(path)
    }
    for path in args.exclude_judgments:
        for row in _read_jsonl(path):
            if row.get("relevant") and int(row.get("grade", 0) or 0) > 0:
                excluded.add(str(row["candidate"]["chunk_id"]))

    selected = select_targets(
        args.chunks,
        excluded_chunk_ids=excluded,
        scenario_counts=SCENARIO_COUNTS,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    report = {"excluded_chunks": len(excluded), "scenarios": {}}
    for scenario, rows in selected.items():
        scenario_dir = args.out_dir / scenario
        scenario_dir.mkdir(parents=True, exist_ok=True)
        target_path = scenario_dir / "targets.jsonl"
        target_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
        for old in scenario_dir.glob("targets_*.jsonl"):
            old.unlink()
        for index, offset in enumerate(range(0, len(rows), args.batch_size), start=1):
            (scenario_dir / f"targets_{index:03d}.jsonl").write_text(
                "".join(
                    json.dumps(row, ensure_ascii=False) + "\n"
                    for row in rows[offset : offset + args.batch_size]
                ),
                encoding="utf-8",
            )
        report["scenarios"][scenario] = {
            "targets": len(rows),
            "batches": (len(rows) + args.batch_size - 1) // args.batch_size,
        }
    (args.out_dir / "prepare_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
