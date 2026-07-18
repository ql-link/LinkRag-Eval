#!/usr/bin/env python3
"""Freeze reusable original-query benchmarks for paired rewrite evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DATASET_IDS = [992000, 992001, 992002, 992003]
SMOKE_HINTS = ("keyword", "alias", "number_time", "multi_constraint", "similar_docs")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stable_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _note_field(row: dict[str, Any], key: str) -> str:
    match = re.search(rf"(?:^|;\s*){re.escape(key)}=([^;]*)", str(row.get("note") or ""))
    return match.group(1).strip() if match else ""


def _validate(rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise SystemExit("source benchmark is empty")
    ids = [str(row.get("id") or "") for row in rows]
    queries = [str(row.get("query") or "").strip() for row in rows]
    if "" in ids or len(ids) != len(set(ids)):
        raise SystemExit("source contains blank or duplicate ids")
    if "" in queries or len(queries) != len(set(queries)):
        raise SystemExit("source contains blank or duplicate queries")
    for row in rows:
        if row.get("dataset_ids") != DATASET_IDS:
            raise SystemExit(f"unexpected dataset scope: {row.get('id')}")
        if not row.get("expected_chunk_ids"):
            raise SystemExit(f"missing chunk reference: {row.get('id')}")
        if not row.get("expected_doc_ids"):
            raise SystemExit(f"missing doc reference: {row.get('id')}")


def _smoke_rows(rows: list[dict[str, Any]], per_hint: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if len(row["expected_chunk_ids"]) != 1:
            continue
        grouped[_note_field(row, "type_hint")].append(row)

    selected: list[dict[str, Any]] = []
    for hint in SMOKE_HINTS:
        candidates = sorted(grouped[hint], key=lambda row: _stable_key(str(row["id"])))
        if len(candidates) < per_hint:
            raise SystemExit(
                f"insufficient single-chunk smoke rows for {hint}: {len(candidates)} < {per_hint}"
            )
        selected.extend(candidates[:per_hint])
    return sorted(selected, key=lambda row: str(row["id"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--smoke-per-hint", type=int, default=8)
    args = parser.parse_args()

    rows = _read_jsonl(args.source)
    _validate(rows)
    single_rows = [row for row in rows if len(row["expected_chunk_ids"]) == 1]
    smoke_rows = _smoke_rows(rows, args.smoke_per_hint)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    full_path = args.out_dir / "original_full_272.jsonl"
    single_path = args.out_dir / "original_single_chunk_206.jsonl"
    smoke_path = args.out_dir / "original_smoke_40.jsonl"
    _write_jsonl(full_path, rows)
    _write_jsonl(single_path, single_rows)
    _write_jsonl(smoke_path, smoke_rows)

    hint_counts = Counter(_note_field(row, "type_hint") for row in rows)
    smoke_hint_counts = Counter(_note_field(row, "type_hint") for row in smoke_rows)
    manifest = {
        "benchmark_id": "query_rewrite_benchmark_v1",
        "purpose": "paired original-vs-rewrite retrieval evaluation",
        "source": str(args.source),
        "source_sha256": _sha256(args.source),
        "dataset_ids": DATASET_IDS,
        "rules": {
            "same_sample_ids": True,
            "same_qrels": True,
            "same_dataset_scope": True,
            "rewrite_input_must_not_include_target_chunk_content": True,
            "primary_metrics_full": ["hit_rate_chunk@10", "mrr_chunk"],
            "primary_metrics_single_chunk": ["recall_chunk@10", "hit_rate_chunk@10", "mrr_chunk"],
        },
        "artifacts": {
            full_path.name: {
                "count": len(rows),
                "sha256": _sha256(full_path),
                "usage": "complete paired tune benchmark",
            },
            single_path.name: {
                "count": len(single_rows),
                "sha256": _sha256(single_path),
                "usage": "single canonical chunk paired headline",
            },
            smoke_path.name: {
                "count": len(smoke_rows),
                "sha256": _sha256(smoke_path),
                "usage": "fast implementation smoke benchmark",
            },
        },
        "source_distribution": {
            "question_type": dict(sorted(Counter(row["type"] for row in rows).items())),
            "type_hint": dict(sorted(hint_counts.items())),
            "chunk_reference_count": {
                str(key): value
                for key, value in sorted(
                    Counter(len(row["expected_chunk_ids"]) for row in rows).items()
                )
            },
        },
        "smoke_distribution": {
            "type_hint": dict(sorted(smoke_hint_counts.items())),
            "all_single_chunk": all(len(row["expected_chunk_ids"]) == 1 for row in smoke_rows),
        },
    }
    manifest_path = args.out_dir / "benchmark_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
