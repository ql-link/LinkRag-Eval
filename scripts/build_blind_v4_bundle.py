#!/usr/bin/env python3
"""合并真实搜索与结构化场景，生成 Tune/Blind v4 冻结前 bundle。"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _normalized_query(value: str) -> str:
    return " ".join(value.casefold().split())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tune", action="append", required=True)
    parser.add_argument("--blind", action="append", required=True)
    parser.add_argument("--contents", action="append", required=True)
    parser.add_argument("--chunks", action="append", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    tune = [row for path in args.tune for row in _read_jsonl(Path(path))]
    blind = [row for path in args.blind for row in _read_jsonl(Path(path))]
    tune_ids = {str(row["id"]) for row in tune}
    blind_ids = {str(row["id"]) for row in blind}
    if len(tune_ids) != len(tune) or len(blind_ids) != len(blind):
        raise ValueError("Tune/Blind 内 sample id 重复")
    if tune_ids & blind_ids:
        raise ValueError("Tune/Blind sample id 泄漏")
    tune_queries = {_normalized_query(str(row["query"])) for row in tune}
    overlap = [row["id"] for row in blind if _normalized_query(str(row["query"])) in tune_queries]
    if overlap:
        raise ValueError(f"Tune/Blind query 文本泄漏:{overlap[:3]}")
    contents: dict[str, str] = {}
    for path in args.contents:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        for chunk_id, content in payload.get("contents", payload).items():
            previous = contents.setdefault(str(chunk_id), str(content))
            if previous != str(content):
                raise ValueError(f"chunk content 冲突:{chunk_id}")
    chunks = [row for path in args.chunks for row in _read_jsonl(Path(path))]
    if len({row["chunk_id"] for row in chunks}) != len(chunks):
        raise ValueError("chunk_id 重复")
    out = Path(args.out_dir)
    tune_path = out / "tune_frozen.jsonl"
    blind_path = out / "blind_v4_candidate.jsonl"
    contents_path = out / "candidate_contents.json"
    chunks_path = out / "chunk_records.jsonl"
    _write_jsonl(tune_path, tune)
    _write_jsonl(blind_path, blind)
    _write_jsonl(chunks_path, chunks)
    contents_path.write_text(json.dumps(contents, ensure_ascii=False), encoding="utf-8")
    sources = Counter(
        str((row.get("provenance") or {}).get("source_kind") or "unknown")
        for row in [*tune, *blind]
    )
    scenarios = Counter(
        str(
            row.get("scenario")
            or (row.get("provenance") or {}).get("scenario")
            or "unknown"
        )
        for row in [*tune, *blind]
    )
    manifest = {
        "tune_count": len(tune),
        "blind_count": len(blind),
        "chunk_count": len(chunks),
        "query_sources": dict(sorted(sources.items())),
        "scenarios": dict(sorted(scenarios.items())),
        "multi_positive_tune": sum(len(row.get("expected_chunk_ids") or []) > 1 for row in tune),
        "multi_positive_blind": sum(len(row.get("expected_chunk_ids") or []) > 1 for row in blind),
        "sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (tune_path, blind_path, chunks_path, contents_path)
        },
    }
    (out / "bundle_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
