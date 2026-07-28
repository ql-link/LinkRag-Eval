#!/usr/bin/env python3
"""Freeze all historical query and evidence exposure before creating a new Blind set."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _sha256(values: set[str]) -> str:
    return hashlib.sha256("\n".join(sorted(values)).encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan-root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--include-generation-targets",
        action="store_true",
        help="treat rejected/unselected generation targets as positive-label exposure",
    )
    args = parser.parse_args()

    out_dir = args.out_dir.resolve()
    chunk_ids: set[str] = set()
    queries: set[str] = set()
    query_ids: set[str] = set()
    source_files: list[str] = []
    rows_scanned = 0
    for path in sorted(args.scan_root.rglob("*.jsonl")):
        resolved = path.resolve()
        if out_dir == resolved or out_dir in resolved.parents:
            continue
        used = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows_scanned += 1
            expected = row.get("expected_chunk_ids")
            if isinstance(expected, list):
                chunk_ids.update(str(value) for value in expected)
                used = used or bool(expected)
            if args.include_generation_targets:
                target = row.get("target")
                if isinstance(target, dict) and target.get("chunk_id") is not None:
                    chunk_ids.add(str(target["chunk_id"]))
                    used = True
            query = row.get("query")
            if isinstance(query, str) and query.strip():
                queries.add(query.strip())
                used = True
            query_id = row.get("query_id", row.get("id", row.get("sample_id")))
            if query_id is not None:
                query_ids.add(str(query_id))
                used = True
        if used:
            source_files.append(str(path))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    references_path = args.out_dir / "exposed_references.jsonl"
    references_path.write_text(
        "".join(
            json.dumps({"expected_chunk_ids": [chunk_id]}, ensure_ascii=False) + "\n"
            for chunk_id in sorted(chunk_ids)
        ),
        encoding="utf-8",
    )
    queries_path = args.out_dir / "exposed_queries.jsonl"
    queries_path.write_text(
        "".join(
            json.dumps({"query": query}, ensure_ascii=False) + "\n"
            for query in sorted(queries)
        ),
        encoding="utf-8",
    )
    manifest = {
        "scan_root": str(args.scan_root),
        "source_files": len(source_files),
        "rows_scanned": rows_scanned,
        "exposed_chunk_ids": len(chunk_ids),
        "exposed_queries": len(queries),
        "exposed_query_ids": len(query_ids),
        "positive_exposure_definition": "expected_chunk_ids",
        "includes_rejected_generation_targets": args.include_generation_targets,
        "chunk_ids_sha256": _sha256(chunk_ids),
        "queries_sha256": _sha256(queries),
        "query_ids_sha256": _sha256(query_ids),
        "references_path": str(references_path),
        "queries_path": str(queries_path),
    }
    (args.out_dir / "exposure_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
