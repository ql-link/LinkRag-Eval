#!/usr/bin/env python3
"""Select unused, dataset-balanced grounded exact targets for reserve labeling."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from prepare_grounded_exact_targets import select_targets


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", action="append", type=Path, required=True)
    parser.add_argument("--existing-targets", type=Path, required=True)
    parser.add_argument("--per-dataset", type=int, default=4)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=4)
    args = parser.parse_args()

    existing = {row["chunk_id"] for row in _read_jsonl(args.existing_targets)}
    candidates = select_targets(args.chunks, per_dataset=60)
    selected = []
    counts: dict[int, int] = {}
    for row in candidates:
        dataset_id = int(row["dataset_id"])
        if row["chunk_id"] in existing or counts.get(dataset_id, 0) >= args.per_dataset:
            continue
        counts[dataset_id] = counts.get(dataset_id, 0) + 1
        selected.append(row)
    expected = args.per_dataset * 4
    if len(selected) != expected or set(counts.values()) != {args.per_dataset}:
        raise SystemExit(f"expected {expected} balanced unused targets, got {len(selected)}")
    for index, row in enumerate(selected, start=1):
        row["query_id"] = f"balanced-exact-grounded-extra-{index:04d}"

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected),
        encoding="utf-8",
    )
    args.batch_dir.mkdir(parents=True, exist_ok=True)
    for old in args.batch_dir.glob("targets_*.jsonl"):
        old.unlink()
    for index, offset in enumerate(range(0, len(selected), args.batch_size), start=1):
        batch = selected[offset : offset + args.batch_size]
        (args.batch_dir / f"targets_{index:03d}.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in batch),
            encoding="utf-8",
        )
    report = {"targets": len(selected), "per_dataset": counts, "batches": len(selected) // args.batch_size}
    (args.out.parent / "prepare_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
