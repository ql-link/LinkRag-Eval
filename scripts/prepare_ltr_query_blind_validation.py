#!/usr/bin/env python3
"""Build shuffled same-scenario candidate pools for independent query validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=25)
    args = parser.parse_args()

    targets = {row["query_id"]: row for row in _read_jsonl(args.targets)}
    queries = {row["query_id"]: row for row in _read_jsonl(args.queries)}
    if set(targets) != set(queries):
        raise SystemExit("target/query coverage mismatch")

    pools = []
    for query_id in sorted(targets):
        target = targets[query_id]
        candidates = [target["target"], *target["hard_negatives"]]
        rng = random.Random(
            int(hashlib.sha256(query_id.encode("utf-8")).hexdigest()[:16], 16)
        )
        rng.shuffle(candidates)
        pools.append(
            {
                "query_id": query_id,
                "query": queries[query_id]["query"],
                "type_hint": target["type_hint"],
                "hard_reason": target["hard_reason"],
                "candidates": candidates,
            }
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "blinded_pools.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in pools),
        encoding="utf-8",
    )
    batches = args.out_dir / "batches"
    batches.mkdir(exist_ok=True)
    for old in batches.glob("pool_*.jsonl"):
        old.unlink()
    for index, offset in enumerate(range(0, len(pools), args.batch_size), start=1):
        (batches / f"pool_{index:03d}.jsonl").write_text(
            "".join(
                json.dumps(row, ensure_ascii=False) + "\n"
                for row in pools[offset : offset + args.batch_size]
            ),
            encoding="utf-8",
        )
    report = {
        "queries": len(pools),
        "candidates_per_query": 4,
        "batch_size": args.batch_size,
        "batches": (len(pools) + args.batch_size - 1) // args.batch_size,
        "target_identity_hidden": True,
    }
    (args.out_dir / "prepare_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
