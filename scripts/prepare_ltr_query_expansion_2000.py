#!/usr/bin/env python3
"""Prepare grounded target chunks and same-scenario hard negatives for LTR expansion."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel


GENERATE_QUOTAS = {
    "number_time": 240,
    "exact_identifier": 85,
    "similar_docs": 720,
    "multi_constraint": 350,
    "alias": 190,
    "dense_paraphrase": 160,
    "short_keyword": 105,
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _stable(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _excluded_chunks(paths: list[Path]) -> set[str]:
    excluded: set[str] = set()
    for path in paths:
        for row in _read_jsonl(path):
            excluded.update(str(chunk_id) for chunk_id in row.get("expected_chunk_ids", []))
            target = row.get("target")
            if isinstance(target, dict) and target.get("chunk_id"):
                excluded.add(str(target["chunk_id"]))
    return excluded


def _nearest_by_scenario(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        metadata = row.get("metadata") or {}
        key = f"{row['dataset_id']}::{metadata.get('scenario') or metadata.get('domain')}"
        groups[key].append(row)

    negatives: dict[str, list[dict[str, Any]]] = {}
    for group in groups.values():
        if len(group) < 4:
            continue
        matrix = TfidfVectorizer(analyzer="char", ngram_range=(2, 4), min_df=1).fit_transform(
            [str(row["content"]) for row in group]
        )
        similarities = linear_kernel(matrix, matrix)
        for index, row in enumerate(group):
            order = sorted(
                range(len(group)),
                key=lambda candidate: (
                    -float(similarities[index, candidate]),
                    str(group[candidate]["chunk_id"]),
                ),
            )
            selected = [
                group[candidate]
                for candidate in order
                if candidate != index and group[candidate]["doc_id"] != row["doc_id"]
            ][:3]
            if len(selected) == 3:
                negatives[str(row["chunk_id"])] = selected
    return negatives


def _select_targets(
    rows: list[dict[str, Any]],
    *,
    excluded: set[str],
    nearest: dict[str, list[dict[str, Any]]],
    quotas: dict[str, int],
    id_prefix: str,
) -> list[dict[str, Any]]:
    eligible = [
        row
        for row in rows
        if str(row["chunk_id"]) not in excluded
        and str(row["chunk_id"]) in nearest
        and len(str(row.get("content") or "")) >= 140
    ]
    by_dataset: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in eligible:
        by_dataset[int(row["dataset_id"])].append(row)
    for dataset_id, dataset_rows in by_dataset.items():
        dataset_rows.sort(key=lambda row: _stable(f"{dataset_id}:{row['chunk_id']}"))
    numeric_by_dataset = {
        dataset_id: [
            row
            for row in dataset_rows
            if any(char.isdigit() for char in str(row["content"]))
        ]
        for dataset_id, dataset_rows in by_dataset.items()
    }

    selected: list[dict[str, Any]] = []
    used: set[str] = set()
    counters = {dataset_id: 0 for dataset_id in sorted(by_dataset)}
    numeric_counters = {dataset_id: 0 for dataset_id in sorted(by_dataset)}
    for type_hint, total in quotas.items():
        dataset_ids = sorted(by_dataset)
        if type_hint in {"number_time", "exact_identifier"}:
            picked = 0
            while picked < total:
                progressed = False
                for dataset_id in dataset_ids:
                    rows_for_dataset = numeric_by_dataset[dataset_id]
                    while numeric_counters[dataset_id] < len(rows_for_dataset):
                        target = rows_for_dataset[numeric_counters[dataset_id]]
                        numeric_counters[dataset_id] += 1
                        chunk_id = str(target["chunk_id"])
                        if chunk_id in used:
                            continue
                        used.add(chunk_id)
                        picked += 1
                        progressed = True
                        query_id = f"{id_prefix}-{type_hint.replace('_', '-')}-{len(selected) + 1:04d}"
                        selected.append(
                            {
                                "query_id": query_id,
                                "type_hint": type_hint,
                                "hard_reason": "hard_negative_same_scenario",
                                "target": {
                                    key: target[key]
                                    for key in ("chunk_id", "doc_id", "dataset_id", "content")
                                },
                                "hard_negatives": [
                                    {
                                        key: negative[key]
                                        for key in (
                                            "chunk_id",
                                            "doc_id",
                                            "dataset_id",
                                            "content",
                                        )
                                    }
                                    for negative in nearest[chunk_id]
                                ],
                                "domain": (target.get("metadata") or {}).get("domain"),
                                "source_scenario": (target.get("metadata") or {}).get(
                                    "scenario"
                                ),
                            }
                        )
                        break
                    if picked == total:
                        break
                if not progressed:
                    raise SystemExit(f"insufficient numeric targets for {type_hint}")
            continue
        base, remainder = divmod(total, len(dataset_ids))
        for dataset_index, dataset_id in enumerate(dataset_ids):
            quota = base + int(dataset_index < remainder)
            picked = 0
            rows_for_dataset = by_dataset[dataset_id]
            while picked < quota:
                if counters[dataset_id] >= len(rows_for_dataset):
                    raise SystemExit(f"insufficient targets for dataset {dataset_id}")
                target = rows_for_dataset[counters[dataset_id]]
                counters[dataset_id] += 1
                chunk_id = str(target["chunk_id"])
                if chunk_id in used:
                    continue
                if type_hint in {"number_time", "exact_identifier"} and not any(
                    char.isdigit() for char in str(target["content"])
                ):
                    continue
                used.add(chunk_id)
                picked += 1
                query_id = f"{id_prefix}-{type_hint.replace('_', '-')}-{len(selected) + 1:04d}"
                selected.append(
                    {
                        "query_id": query_id,
                        "type_hint": type_hint,
                        "hard_reason": (
                            "similar_docs"
                            if type_hint == "similar_docs"
                            else "hard_negative_same_scenario"
                        ),
                        "target": {
                            key: target[key]
                            for key in ("chunk_id", "doc_id", "dataset_id", "content")
                        },
                        "hard_negatives": [
                            {
                                key: negative[key]
                                for key in ("chunk_id", "doc_id", "dataset_id", "content")
                            }
                            for negative in nearest[chunk_id]
                        ],
                        "domain": (target.get("metadata") or {}).get("domain"),
                        "source_scenario": (target.get("metadata") or {}).get("scenario"),
                    }
                )
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", action="append", type=Path, required=True)
    parser.add_argument("--exclude-golden", action="append", type=Path, default=[])
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument(
        "--quota",
        action="append",
        default=[],
        metavar="SCENARIO=COUNT",
        help="override generation quotas; repeat for each requested scenario",
    )
    parser.add_argument("--id-prefix", default="ltr2k")
    parser.add_argument(
        "--exclude-hard-negatives",
        action="store_true",
        help="also exclude exposed chunks from same-scenario hard-negative candidates",
    )
    args = parser.parse_args()

    quotas = dict(GENERATE_QUOTAS)
    if args.quota:
        quotas = {}
        for item in args.quota:
            scenario, separator, raw_count = item.partition("=")
            if not separator or scenario not in GENERATE_QUOTAS:
                raise SystemExit(f"invalid quota: {item}")
            count = int(raw_count)
            if count < 0:
                raise SystemExit(f"invalid quota count: {item}")
            quotas[scenario] = count

    rows = [row for path in args.chunks for row in _read_jsonl(path)]
    excluded = _excluded_chunks(args.exclude_golden)
    nearest_rows = (
        [row for row in rows if str(row["chunk_id"]) not in excluded]
        if args.exclude_hard_negatives
        else rows
    )
    nearest = _nearest_by_scenario(nearest_rows)
    selected = _select_targets(
        rows,
        excluded=excluded,
        nearest=nearest,
        quotas=quotas,
        id_prefix=args.id_prefix,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "targets.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected),
        encoding="utf-8",
    )
    batches = args.out_dir / "generation_batches"
    batches.mkdir(exist_ok=True)
    for old in batches.glob("targets_*.jsonl"):
        old.unlink()
    for index, offset in enumerate(range(0, len(selected), args.batch_size), start=1):
        (batches / f"targets_{index:03d}.jsonl").write_text(
            "".join(
                json.dumps(row, ensure_ascii=False) + "\n"
                for row in selected[offset : offset + args.batch_size]
            ),
            encoding="utf-8",
        )
    report = {
        "requested": sum(quotas.values()),
        "prepared": len(selected),
        "excluded_chunks": len(excluded),
        "hard_negative_candidates_per_query": 3,
        "generation_quotas": quotas,
        "id_prefix": args.id_prefix,
        "excluded_hard_negatives": args.exclude_hard_negatives,
        "batch_size": args.batch_size,
        "batches": (len(selected) + args.batch_size - 1) // args.batch_size,
    }
    (args.out_dir / "prepare_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
