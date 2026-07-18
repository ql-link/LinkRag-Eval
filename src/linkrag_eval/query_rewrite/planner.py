"""LLM-backed route-specific query rewrite planner."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Iterable

from linkrag_eval.golden.schema import GoldenSample
from linkrag_eval.judge.eval_llm import EvalChatClient
from linkrag_eval.query_rewrite.schema import QueryRewritePlan


SYSTEM_PROMPT = """你是RAG检索规划器。只根据用户原始Query生成检索计划。
禁止假设答案、禁止补造用户没有给出的实体/编号/时间、禁止输出推理过程。
必须输出单个JSON对象，不要Markdown。

字段:
- query_type: short_keyword | exact_identifier | long_multi_constraint |
  semantic_paraphrase | general
- queries.dense: 语义完整、适合稠密向量的自然语言Query
- queries.sparse: 保留实体/动作/条件/同义词的关键词Query
- queries.bm25: 尽量保留原编号、日期、版本、专名和精确短语的词法Query
- weights: dense/sparse/bm25，非负且总和大于0
- protected_candidates: dense/sparse/bm25，各为0到10的整数
- confidence: 0到1
- reason_code: 一个短标签，不要解释性长文本

原始Query必须被视为不可丢失的兜底。尤其不能丢失否定词、数字、日期、版本和编号。"""

SYSTEM_PROMPT += """

按以下候选策略给出初始权重和保护名额，不要自行改成均权:
- short_keyword: weights=0.45/0.40/0.15，protected sparse=3
- exact_identifier: weights=0.30/0.35/0.35，protected sparse=3,bm25=3
- long_multi_constraint: weights=0.45/0.40/0.15，protected sparse=3
- semantic_paraphrase: weights=0.70/0.20/0.10，protected dense=4
- general: weights=0.70/0.15/0.15，不设保护
权重顺序固定为 dense/sparse/bm25。"""


class QueryRewritePlanner:
    def __init__(
        self,
        client: EvalChatClient,
        *,
        model: str,
        prompt_version: str = "query-rewrite-v1",
        temperature: float = 0.0,
        max_tokens: int = 900,
    ) -> None:
        self.client = client
        self.model = model
        self.prompt_version = prompt_version
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def plan(self, sample: GoldenSample) -> QueryRewritePlan:
        prompt = json.dumps(
            {
                "sample_id": sample.id,
                "original_query": sample.query,
                "question_type": sample.type.value,
            },
            ensure_ascii=False,
        )
        raw = await self.client.generate_json(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        if not isinstance(raw, dict):
            return QueryRewritePlan.fallback_plan(
                sample_id=sample.id,
                original_query=sample.query,
                model=self.model,
                prompt_version=self.prompt_version,
                reason_code="invalid_or_unavailable_response",
            )
        try:
            return QueryRewritePlan.from_model_dict(
                raw,
                sample_id=sample.id,
                original_query=sample.query,
                model=self.model,
                prompt_version=self.prompt_version,
            )
        except (KeyError, TypeError, ValueError):
            return QueryRewritePlan.fallback_plan(
                sample_id=sample.id,
                original_query=sample.query,
                model=self.model,
                prompt_version=self.prompt_version,
                reason_code="schema_validation_failed",
            )


def _read_existing(path: Path) -> dict[str, QueryRewritePlan]:
    if not path.exists():
        return {}
    plans: dict[str, QueryRewritePlan] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            plan = QueryRewritePlan.from_dict(json.loads(line))
            plans[plan.sample_id] = plan
    return plans


async def generate_rewrite_plans(
    samples: Iterable[GoldenSample],
    *,
    planner: QueryRewritePlanner,
    out: Path,
    report_out: Path | None = None,
    concurrency: int = 4,
    resume: bool = True,
    progress: Any | None = None,
) -> dict[str, Any]:
    items = list(samples)
    existing = _read_existing(out) if resume else {}
    sample_by_id = {sample.id: sample for sample in items}
    existing = {
        sample_id: plan
        for sample_id, plan in existing.items()
        if sample_id in sample_by_id
        and plan.original_query == sample_by_id[sample_id].query
        and not plan.fallback
    }
    sem = asyncio.Semaphore(max(1, concurrency))
    completed = 0

    async def _one(sample: GoldenSample) -> QueryRewritePlan:
        nonlocal completed
        if sample.id in existing:
            return existing[sample.id]
        async with sem:
            plan = await planner.plan(sample)
        completed += 1
        if progress and (completed % 10 == 0 or completed == len(items) - len(existing)):
            progress(f"rewrite plans {completed}/{len(items) - len(existing)}")
        return plan

    plans = await asyncio.gather(*[_one(sample) for sample in items])
    by_id = {plan.sample_id: plan for plan in plans}
    ordered = [by_id[sample.id] for sample in items]
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_suffix(out.suffix + ".tmp")
    temp.write_text(
        "".join(json.dumps(plan.to_dict(), ensure_ascii=False) + "\n" for plan in ordered),
        encoding="utf-8",
    )
    temp.replace(out)

    report = {
        "samples": len(items),
        "generated": len(items) - len(existing),
        "resumed": len(existing),
        "fallback": sum(plan.fallback for plan in ordered),
        "model": planner.model,
        "prompt_version": planner.prompt_version,
        "output": str(out),
    }
    if report_out:
        report_out.parent.mkdir(parents=True, exist_ok=True)
        report_out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return report
