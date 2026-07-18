#!/usr/bin/env python3
"""Prepare grounded rewrites for target chunks not yet used by accepted qrels."""

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
    parser.add_argument("--base-golden", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--quota", action="append", required=True, help="SCENARIO=COUNT")
    parser.add_argument("--id-prefix", required=True)
    parser.add_argument("--batch-size", type=int, default=5)
    args = parser.parse_args()

    quotas: dict[str, int] = {}
    for item in args.quota:
        scenario, raw_count = item.split("=", 1)
        quotas[scenario] = int(raw_count)

    targets = {row["query_id"]: row for row in _read(args.source_round / "targets.jsonl")}
    queries = {
        row["query_id"]: row for row in _read(args.source_round / "generated_queries.jsonl")
    }
    pools = {
        row["query_id"]: row
        for row in _read(args.source_round / "validation" / "blinded_pools.jsonl")
    }
    decisions = {
        row["query_id"]: row
        for path in sorted((args.source_round / "validation" / "decisions").glob("pool_*.jsonl"))
        for row in _read(path)
    }
    if not (set(targets) == set(queries) == set(pools) == set(decisions)):
        raise SystemExit("source round must be fully generated and judged")

    used_chunks = {
        str(chunk_id)
        for row in _read(args.base_golden)
        for chunk_id in row.get("expected_chunk_ids", [])
    }
    for query_id in sorted(decisions, key=_stable):
        selected = decisions[query_id].get("relevant_chunk_id")
        if selected is not None:
            used_chunks.add(str(selected))

    candidates: dict[str, dict] = {}
    rejected_queries: dict[str, list[str]] = {}
    for query_id in sorted(targets, key=_stable):
        target = targets[query_id]
        scenario = str(target["type_hint"])
        chunk_id = str(target["target"]["chunk_id"])
        if scenario not in quotas or chunk_id in used_chunks:
            continue
        candidates.setdefault(chunk_id, target)
        rejected_queries.setdefault(chunk_id, []).append(str(queries[query_id]["query"]))

    selected: list[dict] = []
    counts = Counter()
    for chunk_id in sorted(candidates, key=_stable):
        target = candidates[chunk_id]
        scenario = str(target["type_hint"])
        if counts[scenario] >= quotas[scenario]:
            continue
        rewritten = dict(target)
        rewritten["query_id"] = (
            f"{args.id_prefix}-{scenario.replace('_', '-')}-{counts[scenario] + 1:04d}"
        )
        rewritten["rewrite_context"] = {
            "rejected_queries": rejected_queries[chunk_id],
            "instruction": (
                "Write a narrower query directly answered by target.content. Preserve the exact "
                "identifier, number, date, threshold, object, and decisive outcome. Do not reuse any "
                "listed rejected query."
            ),
        }
        selected.append(rewritten)
        counts[scenario] += 1

    missing = {scenario: count - counts[scenario] for scenario, count in quotas.items() if counts[scenario] < count}
    if missing:
        raise SystemExit(f"insufficient unused target chunks: {missing}")

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
        "quotas": quotas,
        "targets": len(selected),
        "counts": dict(counts),
        "excluded_used_chunks": len(used_chunks),
        "batch_size": args.batch_size,
    }
    (args.out_dir / "prepare_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
