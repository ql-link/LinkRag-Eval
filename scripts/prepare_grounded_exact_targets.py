#!/usr/bin/env python3
"""Select balanced source chunks containing grounded exact expressions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


EXACT_RE = re.compile(
    r"(?:v\d+(?:\.\d+){0,3}|\d{4}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?|"
    r"\d+(?:\.\d+)?\s*(?:%|元|小时|分钟|天|次|个|份|MB|GB|kg|工作日))",
    flags=re.IGNORECASE,
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _stable_key(row: dict[str, Any]) -> str:
    raw = f"{row['dataset_id']}:{row['chunk_id']}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def select_targets(paths: list[Path], *, per_dataset: int) -> list[dict[str, Any]]:
    by_dataset: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for path in paths:
        for row in _read_jsonl(path):
            expressions = sorted(set(EXACT_RE.findall(str(row["content"]))))
            if expressions:
                by_dataset[int(row["dataset_id"])].append(
                    {**row, "exact_expressions": expressions}
                )

    selected: list[dict[str, Any]] = []
    for dataset_id, rows in sorted(by_dataset.items()):
        by_scenario: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            scenario = str(row.get("metadata", {}).get("scenario") or row["chunk_id"])
            by_scenario[scenario].append(row)
        for scenario_rows in by_scenario.values():
            scenario_rows.sort(key=_stable_key)

        ordered: list[dict[str, Any]] = []
        scenario_names = sorted(by_scenario)
        depth = 0
        while len(ordered) < per_dataset:
            added = False
            for scenario in scenario_names:
                scenario_rows = by_scenario[scenario]
                if depth < len(scenario_rows):
                    ordered.append(scenario_rows[depth])
                    added = True
                    if len(ordered) == per_dataset:
                        break
            if not added:
                break
            depth += 1
        if len(ordered) < per_dataset:
            raise SystemExit(
                f"dataset {dataset_id} only has {len(ordered)} grounded chunks; "
                f"required {per_dataset}"
            )
        selected.extend(ordered)

    result = []
    for index, row in enumerate(selected, start=1):
        result.append(
            {
                "query_id": f"balanced-exact-grounded-{index:04d}",
                "dataset_id": int(row["dataset_id"]),
                "doc_id": int(row["doc_id"]),
                "chunk_id": str(row["chunk_id"]),
                "content": str(row["content"]),
                "exact_expressions": row["exact_expressions"],
                "domain": row.get("metadata", {}).get("domain"),
                "scenario": row.get("metadata", {}).get("scenario"),
            }
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", action="append", type=Path, required=True)
    parser.add_argument("--per-dataset", type=int, default=45)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=5)
    args = parser.parse_args()

    rows = select_targets(args.chunks, per_dataset=args.per_dataset)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    args.batch_dir.mkdir(parents=True, exist_ok=True)
    for old in args.batch_dir.glob("targets_*.jsonl"):
        old.unlink()
    for index, offset in enumerate(range(0, len(rows), args.batch_size), start=1):
        path = args.batch_dir / f"targets_{index:03d}.jsonl"
        path.write_text(
            "".join(
                json.dumps(row, ensure_ascii=False) + "\n"
                for row in rows[offset : offset + args.batch_size]
            ),
            encoding="utf-8",
        )
    report = {
        "targets": len(rows),
        "per_dataset": args.per_dataset,
        "datasets": sorted({row["dataset_id"] for row in rows}),
        "batches": (len(rows) + args.batch_size - 1) // args.batch_size,
        "output": str(args.out),
    }
    (args.batch_dir / "prepare_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
