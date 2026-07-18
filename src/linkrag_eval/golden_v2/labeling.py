"""Golden V2 DeepSeek 相关性标注模块。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LabelReport:
    queries: int
    judged: int
    relevant: int
    failed: int
    unresolved_queries: int
    output_path: str
    report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        return (
            f"DeepSeek 标注完成: queries={self.queries} judged={self.judged} "
            f"relevant={self.relevant} failed={self.failed} unresolved={self.unresolved_queries}"
        )


async def label_candidate_pool(
    candidate_pool_path: str | Path,
    *,
    out: str | Path,
    judge_client: Any,
    report_out: str | Path | None = None,
    max_candidates_per_query: int | None = None,
    limit_queries: int | None = None,
    max_concurrency: int = 8,
) -> LabelReport:
    if max_concurrency < 1:
        raise ValueError("max_concurrency 必须大于 0")
    pools = _read_jsonl(Path(candidate_pool_path), label="candidate_pool")
    if limit_queries is not None:
        pools = pools[:limit_queries]
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    unresolved = 0
    failed = 0
    judged = 0
    relevant_total = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for pool in pools:
            query = str(pool["query"])
            candidates = list(pool.get("candidates") or [])
            if max_candidates_per_query is not None:
                candidates = candidates[:max_candidates_per_query]
            relevant_for_query = 0
            semaphore = asyncio.Semaphore(max_concurrency)

            async def judge_candidate(candidate: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
                async with semaphore:
                    return candidate, await _judge_one(judge_client, query=query, candidate=candidate)

            results = await asyncio.gather(*(judge_candidate(candidate) for candidate in candidates))
            for candidate, result in results:
                judge_failed = bool(result.pop("_judge_failed", False))
                failed += 1 if judge_failed else 0
                relevant = bool(result.get("relevant", False))
                grade = int(result.get("grade", 1 if relevant else 0))
                if relevant and grade <= 0:
                    grade = 1
                if not relevant:
                    grade = 0
                relevant_for_query += 1 if relevant else 0
                judged += 1
                relevant_total += 1 if relevant else 0
                row = {
                    "query_id": pool["query_id"],
                    "query": query,
                    "role": pool.get("role", "realistic"),
                    "source": pool.get("source"),
                    "type_hint": pool.get("type_hint"),
                    "hard_reason": pool.get("hard_reason"),
                    "candidate": {
                        "chunk_id": candidate["chunk_id"],
                        "doc_id": candidate["doc_id"],
                        "dataset_id": candidate["dataset_id"],
                        "sources": candidate.get("sources", []),
                        "rank_by_source": candidate.get("rank_by_source", {}),
                    },
                    "relevant": relevant,
                    "grade": grade,
                    "evidence_span": str(result.get("evidence_span") or ""),
                    "reason": str(result.get("reason") or ""),
                    "judge_failed": judge_failed,
                    "judge_model": getattr(judge_client, "model", "unknown"),
                }
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
            if relevant_for_query == 0:
                unresolved += 1
    report = LabelReport(
        queries=len(pools),
        judged=judged,
        relevant=relevant_total,
        failed=failed,
        unresolved_queries=unresolved,
        output_path=str(out_path),
        report_path=str(report_out) if report_out else None,
    )
    if report_out:
        path = Path(report_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


async def _judge_one(judge_client: Any, *, query: str, candidate: dict[str, Any]) -> dict[str, Any]:
    prompt = (
        "请判断候选 chunk 是否能直接回答用户问题或提供关键证据。"
        "只输出 JSON,字段为 relevant(boolean)、grade(0-3)、evidence_span、reason。\n\n"
        f"用户问题:\n{query}\n\n"
        f"候选 chunk:\n{candidate.get('content', '')}"
    )
    try:
        parsed = await judge_client.generate_json(
            prompt=prompt,
            system_prompt="你是检索评测标注员。只判断给定 chunk 与 query 的证据相关性。",
            temperature=0.0,
            max_tokens=500,
        )
    except Exception as exc:  # pragma: no cover - defensive for third-party judge clients
        return {
            "relevant": False,
            "grade": 0,
            "reason": f"judge_call_failed:{type(exc).__name__}",
            "_judge_failed": True,
        }
    if not isinstance(parsed, dict):
        return {
            "relevant": False,
            "grade": 0,
            "reason": "judge_json_parse_failed",
            "_judge_failed": True,
        }
    return parsed


def _read_jsonl(path: Path, *, label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno} {label} JSONL 非法:{exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{lineno} {label} 行必须是 object")
            rows.append(row)
    return rows
