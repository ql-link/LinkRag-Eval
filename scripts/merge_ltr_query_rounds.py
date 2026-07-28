#!/usr/bin/env python3
"""Merge independently generated and judged LTR query rounds for final selection."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round", dest="rounds", type=Path, action="append", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    targets: list[dict] = []
    queries: list[dict] = []
    pools: list[dict] = []
    if args.out_dir.exists():
        shutil.rmtree(args.out_dir)
    decisions_out = args.out_dir / "validation" / "decisions"
    decisions_out.mkdir(parents=True)
    for round_index, root in enumerate(args.rounds, start=1):
        targets.extend(_read(root / "targets.jsonl"))
        queries.extend(_read(root / "generated_queries.jsonl"))
        pools.extend(_read(root / "validation" / "blinded_pools.jsonl"))
        for path in sorted((root / "validation" / "decisions").glob("pool_*.jsonl")):
            shutil.copy2(path, decisions_out / f"pool_round_{round_index:02d}_{path.stem}.jsonl")

    target_ids = [str(row["query_id"]) for row in targets]
    query_ids = [str(row["query_id"]) for row in queries]
    pool_ids = [str(row["query_id"]) for row in pools]
    if not (set(target_ids) == set(query_ids) == set(pool_ids)):
        raise SystemExit("round target/query/pool coverage mismatch")
    if len(target_ids) != len(set(target_ids)):
        raise SystemExit("duplicate query IDs across rounds")

    _write(args.out_dir / "targets.jsonl", targets)
    _write(args.out_dir / "generated_queries.jsonl", queries)
    _write(args.out_dir / "validation" / "blinded_pools.jsonl", pools)
    report = {
        "rounds": [str(path) for path in args.rounds],
        "queries": len(targets),
        "decision_files": len(list(decisions_out.glob("*.jsonl"))),
        "decision_rows": sum(len(_read(path)) for path in decisions_out.glob("*.jsonl")),
    }
    (args.out_dir / "merge_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
