#!/usr/bin/env python3
"""Prepare a new grounded generation round from judge-null LTR queries."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _stable(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-round", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--scenario", action="append", required=True)
    parser.add_argument("--id-prefix", required=True)
    parser.add_argument("--batch-size", type=int, default=20)
    args = parser.parse_args()

    targets = {row["query_id"]: row for row in _read(args.source_round / "targets.jsonl")}
    queries = {
        row["query_id"]: row for row in _read(args.source_round / "generated_queries.jsonl")
    }
    decisions = {
        row["query_id"]: row
        for path in sorted((args.source_round / "validation" / "decisions").glob("pool_*.jsonl"))
        for row in _read(path)
    }
    if set(targets) != set(queries) or set(targets) != set(decisions):
        raise SystemExit("source round must be fully generated and judged")

    selected = []
    counts = Counter()
    for query_id in sorted(targets, key=_stable):
        target = targets[query_id]
        decision = decisions[query_id]
        type_hint = str(target["type_hint"])
        if type_hint not in args.scenario or decision.get("relevant_chunk_id") is not None:
            continue
        rewritten = dict(target)
        rewritten["query_id"] = (
            f"{args.id_prefix}-{type_hint.replace('_', '-')}-{len(selected) + 1:04d}"
        )
        rewritten["rewrite_context"] = {
            "rejected_query": queries[query_id]["query"],
            "judge_reason": decision.get("reason"),
            "instruction": (
                "Replace the rejected query with a narrower query directly answered by target.content. "
                "Keep the decisive number, condition, object, and outcome explicit."
            ),
        }
        selected.append(rewritten)
        counts[type_hint] += 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "targets.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected),
        encoding="utf-8",
    )
    batches = args.out_dir / "generation_batches"
    batches.mkdir(exist_ok=True)
    for path in batches.glob("targets_*.jsonl"):
        path.unlink()
    for index, offset in enumerate(range(0, len(selected), args.batch_size), start=1):
        (batches / f"targets_{index:03d}.jsonl").write_text(
            "".join(
                json.dumps(row, ensure_ascii=False) + "\n"
                for row in selected[offset : offset + args.batch_size]
            ),
            encoding="utf-8",
        )
    report = {
        "source_round": str(args.source_round),
        "scenarios": args.scenario,
        "targets": len(selected),
        "counts": dict(counts),
        "batch_size": args.batch_size,
    }
    (args.out_dir / "prepare_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
