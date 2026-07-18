#!/usr/bin/env python3
"""Keep valid decisions and split pending validation pools into smaller batches."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path


def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _valid(pool: list[dict], decisions_path: Path) -> bool:
    if not decisions_path.exists():
        return False
    try:
        decisions = _read(decisions_path)
    except (json.JSONDecodeError, OSError):
        return False
    expected = {str(row["query_id"]) for row in pool}
    if len(decisions) != len(expected) or {str(row.get("query_id")) for row in decisions} != expected:
        return False
    candidates = {
        str(row["query_id"]): {str(candidate["chunk_id"]) for candidate in row["candidates"]}
        for row in pool
    }
    for row in decisions:
        selected = row.get("relevant_chunk_id")
        if selected is not None and str(selected) not in candidates[str(row["query_id"])]:
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=10)
    args = parser.parse_args()
    batches = args.validation_dir / "batches"
    decisions = args.validation_dir / "decisions"
    originals = args.validation_dir / "original_pending_batches"
    originals.mkdir(exist_ok=True)
    kept = split = 0
    for path in sorted(batches.glob("pool_*.jsonl")):
        if not re.fullmatch(r"pool_\d+\.jsonl", path.name):
            continue
        rows = _read(path)
        decision_path = decisions / path.name
        if _valid(rows, decision_path):
            kept += 1
            continue
        decision_path.unlink(missing_ok=True)
        original_path = originals / path.name
        shutil.move(path, original_path)
        for part_index, offset in enumerate(range(0, len(rows), args.batch_size), start=1):
            part = batches / f"{path.stem}_{part_index:02d}.jsonl"
            part.write_text(
                "".join(
                    json.dumps(row, ensure_ascii=False) + "\n"
                    for row in rows[offset : offset + args.batch_size]
                ),
                encoding="utf-8",
            )
            split += 1
    print(json.dumps({"kept_valid_batches": kept, "split_pending_batches": split}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
