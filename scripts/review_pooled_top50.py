#!/usr/bin/env python3
"""用官方 qrels + 独立模型复核冻结 Top50 pool，并对分歧作第三方仲裁。"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from linkrag_eval.config import get_settings
from linkrag_eval.judge.eval_llm import EvalChatClient


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()


def write_official_review(pool_path: Path, golden_paths: list[Path], out: Path) -> None:
    relevant: dict[str, dict[str, int]] = {}
    for path in golden_paths:
        for row in _read_jsonl(path):
            relevant[str(row["id"])] = {
                str(chunk_id): int((row.get("relevance_grades") or {}).get(chunk_id, 1))
                for chunk_id in row.get("expected_chunk_ids") or []
            }
    rows = []
    for item in _read_jsonl(pool_path):
        grade = relevant.get(str(item["query_id"]), {}).get(str(item["chunk_id"]), 0)
        rows.append(
            {
                "review_id": item["review_id"],
                "reviewer_id": "official_t2retrieval_qrels",
                "relevant": grade > 0,
                "grade": grade,
                "reason": "official_qrels" if grade else "not_in_official_qrels",
            }
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _prompt(rows: list[dict[str, Any]]) -> str:
    payload = [
        {
            "review_id": row["review_id"],
            "query": row["query"],
            "candidate": row["content"],
        }
        for row in rows
    ]
    return (
        "独立判断每个候选段落是否能直接回答查询或提供不可缺少的关键证据。"
        "不要猜测候选来源、召回路由或原排名。grade:0不相关,1弱相关,2关键证据,3直接完整回答。"
        "只输出JSON对象，格式为 {\"decisions\":[{\"review_id\":\"...\","
        "\"relevant\":true,\"grade\":0,\"reason\":\"简短理由\"}]}，不得漏项。\n"
        + json.dumps(payload, ensure_ascii=False)
    )


async def model_review(
    pool_path: Path,
    out: Path,
    *,
    model: str,
    reviewer_id: str,
    batch_size: int,
    concurrency: int,
    only_review_ids: set[str] | None = None,
) -> None:
    settings = get_settings()
    client = EvalChatClient(
        base_url=settings.judge_base_url,
        api_key=settings.judge_api_key,
        model=model,
        timeout_s=settings.judge_timeout_s,
        max_retries=settings.judge_max_retries,
        concurrency=concurrency,
    )
    existing = {
        str(row["review_id"])
        for row in (_read_jsonl(out) if out.exists() else [])
        if row.get("reviewer_id") == reviewer_id
    }
    pending = [
        row
        for row in _read_jsonl(pool_path)
        if str(row["review_id"]) not in existing
        and (only_review_ids is None or str(row["review_id"]) in only_review_ids)
    ]
    batches = [pending[index : index + batch_size] for index in range(0, len(pending), batch_size)]
    semaphore = asyncio.Semaphore(concurrency)

    async def judge(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
        expected = {str(row["review_id"]) for row in batch}
        for attempt in range(3):
            async with semaphore:
                parsed = await client.generate_json(
                    prompt=_prompt(batch),
                    system_prompt="你是与原始 qrels 标注过程隔离的检索相关性复核员。只输出严格 JSON。",
                    temperature=0.0,
                    max_tokens=max(1200, len(batch) * 300),
                )
            decisions = (parsed or {}).get("decisions") or []
            by_id = {str(row.get("review_id")): row for row in decisions}
            if set(by_id) == expected:
                result = []
                for review_id in sorted(expected):
                    row = by_id[review_id]
                    relevant = bool(row.get("relevant"))
                    grade = max(1, min(3, int(row.get("grade", 1)))) if relevant else 0
                    result.append(
                        {
                            "review_id": review_id,
                            "reviewer_id": reviewer_id,
                            "relevant": relevant,
                            "grade": grade,
                            "reason": str(row.get("reason") or ""),
                            "model": model,
                        }
                    )
                return result
            if attempt == 2 and len(batch) > 1:
                midpoint = len(batch) // 2
                left, right = await asyncio.gather(
                    judge(batch[:midpoint]),
                    judge(batch[midpoint:]),
                )
                return [*left, *right]
            if attempt == 2:
                review_id = next(iter(expected))
                return [
                    {
                        "review_id": review_id,
                        "reviewer_id": reviewer_id,
                        "relevant": False,
                        "grade": 0,
                        "reason": "reviewer_abstained_after_schema_retries",
                        "model": model,
                        "abstained": True,
                    }
                ]
        raise AssertionError("unreachable")

    try:
        for offset in range(0, len(batches), concurrency):
            results = await asyncio.gather(*(judge(batch) for batch in batches[offset : offset + concurrency]))
            for rows in results:
                _append_jsonl(out, rows)
            print(f"{reviewer_id}: {min(offset + concurrency, len(batches))}/{len(batches)} batches")
    finally:
        await client.aclose()


def disagreement_ids(first: Path, second: Path) -> set[str]:
    a = {str(row["review_id"]): row for row in _read_jsonl(first)}
    b = {str(row["review_id"]): row for row in _read_jsonl(second)}
    return {
        review_id
        for review_id in a.keys() & b.keys()
        if bool(a[review_id].get("abstained"))
        or bool(b[review_id].get("abstained"))
        or bool(a[review_id]["relevant"]) != bool(b[review_id]["relevant"])
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", required=True)
    parser.add_argument("--golden", action="append", default=[])
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--review-model", default="deepseek-v4-flash")
    parser.add_argument("--arbitrator-model", default="deepseek-v4-pro")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--phase", choices=("official", "review", "arbitrate", "all"), default="all")
    args = parser.parse_args()
    pool = Path(args.pool)
    root = Path(args.out_dir)
    official = root / "review_official.jsonl"
    independent = root / "review_independent.jsonl"
    arbitration = root / "review_arbitration.jsonl"
    if args.phase in ("official", "all"):
        if not args.golden:
            raise ValueError("official phase requires --golden")
        write_official_review(pool, [Path(value) for value in args.golden], official)
    if args.phase in ("review", "all"):
        await model_review(
            pool,
            independent,
            model=args.review_model,
            reviewer_id=f"independent:{args.review_model}",
            batch_size=args.batch_size,
            concurrency=args.concurrency,
        )
    if args.phase in ("arbitrate", "all"):
        ids = disagreement_ids(official, independent)
        print(f"disagreements={len(ids)}")
        await model_review(
            pool,
            arbitration,
            model=args.arbitrator_model,
            reviewer_id=f"arbitrator:{args.arbitrator_model}",
            batch_size=args.batch_size,
            concurrency=args.concurrency,
            only_review_ids=ids,
        )


if __name__ == "__main__":
    asyncio.run(main())
