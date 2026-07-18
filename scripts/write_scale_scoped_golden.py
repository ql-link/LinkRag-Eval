#!/usr/bin/env python3
"""Copy a chunk-level golden set with a larger eval-only dataset scope."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--last-dataset-id", required=True, type=int)
    args = parser.parse_args()

    dataset_ids = list(range(992000, args.last_dataset_id + 1))
    rows: list[str] = []
    for line in Path(args.source).open(encoding="utf-8"):
        if not line.strip():
            continue
        row = json.loads(line)
        row["dataset_ids"] = dataset_ids
        rows.append(json.dumps(row, ensure_ascii=False))
    Path(args.out).write_text("\n".join(rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
