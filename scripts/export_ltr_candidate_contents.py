#!/usr/bin/env python3
"""Export eval-owned chunk contents required by LambdaMART candidate features."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from linkrag_eval.store.corpus_repo import EvalCorpusRepo


def _candidate_ids(paths: list[Path]) -> set[str]:
    chunk_ids: set[str] = set()
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            for hits in row.get("routes", {}).values():
                chunk_ids.update(str(hit["chunk_id"]) for hit in hits)
    return chunk_ids


def _ids_sha256(chunk_ids: list[str]) -> str:
    return hashlib.sha256("\n".join(chunk_ids).encode()).hexdigest()


def _local_contents(paths: list[Path]) -> dict[str, str]:
    contents: dict[str, str] = {}
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            content = row.get("content")
            if isinstance(content, str) and content.strip():
                contents[str(row["chunk_id"])] = content
    return contents


async def main_async(args: argparse.Namespace) -> int:
    chunk_ids = sorted(_candidate_ids(args.caches))
    partial_path = args.out.with_suffix(args.out.suffix + ".partial")
    local = _local_contents(args.corpus)
    contents: dict[str, str] = {
        chunk_id: local[chunk_id] for chunk_id in chunk_ids if chunk_id in local
    }
    if contents:
        print(f"content export from frozen corpus: {len(contents)}/{len(chunk_ids)}")
    if partial_path.exists():
        partial = json.loads(partial_path.read_text(encoding="utf-8"))
        if partial.get("candidate_ids_sha256") == _ids_sha256(chunk_ids):
            contents.update(partial.get("contents", {}))
            print(f"content export resumed: {len(contents)}/{len(chunk_ids)}")
    for offset in range(0, len(chunk_ids), args.batch_size):
        batch = [
            chunk_id
            for chunk_id in chunk_ids[offset : offset + args.batch_size]
            if chunk_id not in contents
        ]
        if not batch:
            continue
        for attempt in range(1, args.retries + 1):
            try:
                contents.update(await EvalCorpusRepo().fetch_contents_by_ids(batch))
                break
            except Exception as exc:
                if attempt == args.retries:
                    raise
                print(
                    f"content export retry {attempt}/{args.retries}: "
                    f"{type(exc).__name__}"
                )
                await asyncio.sleep(args.retry_delay * attempt)
        partial_path.parent.mkdir(parents=True, exist_ok=True)
        partial_path.write_text(
            json.dumps(
                {
                    "candidate_ids_sha256": _ids_sha256(chunk_ids),
                    "contents": contents,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"content export: {len(contents)}/{len(chunk_ids)}")
    missing = sorted(set(chunk_ids).difference(contents))
    if missing:
        raise RuntimeError(f"missing {len(missing)} candidate contents, examples: {missing[:5]}")
    payload = {
        "schema_version": 1,
        "source": "frozen corpus artifacts with eval MySQL fallback",
        "input_caches": [str(path) for path in args.caches],
        "frozen_corpus": [str(path) for path in args.corpus],
        "chunk_count": len(contents),
        "contents": dict(sorted(contents.items())),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    partial_path.unlink(missing_ok=True)
    print(json.dumps({"out": str(args.out), "chunk_count": len(contents)}, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", dest="caches", type=Path, action="append", required=True)
    parser.add_argument("--corpus", type=Path, action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--retries", type=int, default=8)
    parser.add_argument("--retry-delay", type=float, default=2.0)
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
