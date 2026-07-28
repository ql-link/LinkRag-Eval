"""反向 QA：据已定位的事实生成 (query, golden_answer, type)。

golden_answer = FactUnit.answer（埋入事实即真值，构造保证可靠，优先于
LLM 判官）；expected_chunk_ids = 回定位结果。问题不得泄漏锚点原文
（避免问题=答案直给检索器），生成后机器校验，泄漏即重试/丢弃。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from linkrag_eval.golden.gen.generator import TextClient
from linkrag_eval.golden.gen.prompts import parse_llm_json
from linkrag_eval.golden.schema import GoldenSample
from linkrag_eval.golden.synth.facts import FactUnit
from linkrag_eval.golden.synth.locate import LocateResult, normalize
from linkrag_eval.models import QuestionType

_QA_SYSTEM = (
    "你是检索评测出题助手。你针对给定事实出一个自然的问题。"
    "输出合法 JSON，不要输出任何其他内容。"
)


def build_qa_prompt(fact: FactUnit) -> tuple[str, str]:
    user = (
        "针对下面的事实出一个问题，要求：\n"
        f"1. 问题的答案就是：「{fact.answer}」；\n"
        "2. 问题中**不得出现**这个锚点短语的原文或近似原文（避免泄漏）："
        f"「{fact.anchor}」；\n"
        "3. 问题要像真实用户提问，自然、具体。\n\n"
        f"事实：{fact.statement}\n\n"
        '输出 JSON：{"query": "..."}'
    )
    return _QA_SYSTEM, user


def anchor_leaked(query: str, anchor: str, *, ngram: int = 6) -> bool:
    """问题是否泄漏锚点：归一化后锚点任意 ngram 连续片段出现在问题中即视为泄漏。"""
    n_query, n_anchor = normalize(query), normalize(anchor)
    if not n_anchor:
        return False
    if n_anchor in n_query:
        return True
    if len(n_anchor) <= ngram:
        return n_anchor in n_query
    return any(
        n_anchor[i : i + ngram] in n_query for i in range(len(n_anchor) - ngram + 1)
    )


@dataclass
class QAStats:
    requested: int = 0
    produced: int = 0
    dropped_leak: int = 0
    dropped_parse: int = 0


@dataclass
class QAGenerator:
    client: TextClient
    qa_model: str
    user_id: int
    dataset_id: int
    doc_id: int
    temperature: float = 0.7
    max_retries: int = 1
    stats: QAStats = field(default_factory=QAStats)

    async def generate_one(
        self, fact: FactUnit, located: LocateResult
    ) -> GoldenSample | None:
        if not located.located:
            return None
        self.stats.requested += 1
        system, user = build_qa_prompt(fact)
        for _ in range(self.max_retries + 1):
            result = await self.client.generate(
                prompt=user, system_prompt=system,
                temperature=self.temperature, max_tokens=256,
            )
            data = parse_llm_json(getattr(result, "content", "") or "")
            if not data or not (data.get("query") or "").strip():
                continue
            query = data["query"].strip()
            if anchor_leaked(query, fact.anchor):
                continue
            self.stats.produced += 1
            return GoldenSample(
                id=f"trackB-{uuid.uuid4().hex[:12]}",
                query=query,
                user_id=self.user_id,
                dataset_ids=[self.dataset_id],
                expected_chunk_ids=list(located.chunk_ids),
                expected_doc_ids=[self.doc_id],
                golden_answer=fact.answer,
                type=QuestionType.LONGTAIL if located.tier != "exact" else QuestionType.KEYWORD,
                note=f"trackB; fact_id={fact.fact_id}; locate_tier={located.tier}; "
                f"qa_model={self.qa_model}",
            )
        # 重试用尽：区分泄漏与解析失败仅作粗统计
        if data and (data.get("query") or "").strip():
            self.stats.dropped_leak += 1
        else:
            self.stats.dropped_parse += 1
        return None
