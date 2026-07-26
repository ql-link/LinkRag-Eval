"""自动质量门禁（替代人工抽检）：三信号全机器可跑，无人工环节。

- 信号一·异模型可答性：与生成器不同（最好更强）的模型只喂 expected chunk
  正文答题，答不出 → 丢弃（catches "chunk 其实答不出的问题"）。
- 信号二·第三方检索回环（B2 防循环论证）：query 走与被测系统无关的独立
  检索器（默认纯 BM25，绝不是阶段 1 的 recall_adapter），expected_chunk_ids
  不落 top-N → 进难例桶（跨配置对比时显式排除或单列，不静默混入）。
- 信号三·答案自洽：生成器答案 vs 信号一答案语义分歧大 → 丢弃（catches 幻觉）。

诚实边界（B1/B5）：门禁是降低噪声而非消除；相对比较的"噪声恒定"前提须经
噪声地板验证后才作数；同源偏置靠模型错开降低但不消除。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable

from linkrag_eval.golden.gen.generator import TextClient
from linkrag_eval.golden.gen.prompts import parse_llm_json
from linkrag_eval.golden.schema import GoldenSample

_ANSWERABILITY_SYSTEM = (
    "你是阅读理解助手。只依据给定片段回答问题，禁止使用片段之外的知识。"
    "输出合法 JSON，不要输出其他内容。"
)

_CONSISTENCY_SYSTEM = (
    "你是答案一致性审核员。判断两个答案在事实层面是否一致。"
    "输出合法 JSON，不要输出其他内容。"
)


def build_answerability_prompt(query: str, chunk_texts: list[str]) -> str:
    blocks = "\n\n".join(f"[片段{i + 1}]\n{t}" for i, t in enumerate(chunk_texts))
    return (
        "依据下列片段回答问题。能回答输出 "
        '{"answerable": true, "answer": "..."}；片段不足以回答输出 '
        '{"answerable": false}。\n\n'
        f"问题：{query}\n\n片段：\n\n{blocks}"
    )


def build_consistency_prompt(query: str, answer_a: str, answer_b: str) -> str:
    return (
        "针对同一问题有两个答案。若它们在关键事实（数值、结论、对象）上一致，"
        '输出 {"consistent": true}；存在实质分歧输出 {"consistent": false, "reason": "..."}。\n\n'
        f"问题：{query}\n答案A：{answer_a}\n答案B：{answer_b}"
    )


@dataclass
class GateDecision:
    sample_id: str
    verdict: str               # passed / dropped / hard
    failed_signal: str | None = None   # answerability / consistency / retrieval_loop
    detail: str = ""


@dataclass
class GateReport:
    total: int = 0
    passed: list[GoldenSample] = field(default_factory=list)
    hard: list[GoldenSample] = field(default_factory=list)      # 难例桶（单列，不混入）
    dropped: list[GateDecision] = field(default_factory=list)
    decisions: list[GateDecision] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return len(self.passed) / self.total if self.total else 0.0

    @property
    def drop_rate(self) -> float:
        return len(self.dropped) / self.total if self.total else 0.0

    @property
    def hard_rate(self) -> float:
        return len(self.hard) / self.total if self.total else 0.0

    def summary(self) -> str:
        return (
            f"gate: {self.total} 条 → 通过 {len(self.passed)}（{self.pass_rate:.0%}）"
            f" / 丢弃 {len(self.dropped)}（{self.drop_rate:.0%}）"
            f" / 难例 {len(self.hard)}（{self.hard_rate:.0%}）"
        )


class AutoQualityGate:
    """三信号自动门禁。

    reviewer_client：门禁复核模型（须 ≠ 生成器，最好更强）。
    retriever：独立第三方检索 query → top-N chunk_id（默认建议
    SimpleBM25Retriever().search；绝不可传被测召回）。
    chunk_texts：chunk_id → 正文（信号一只喂 expected 正文）。
    """

    def __init__(
        self,
        reviewer_client: TextClient,
        reviewer_model: str,
        retriever: Callable[[str], Awaitable[list[str]]] | Callable[[str], list[str]],
        chunk_texts: dict[str, str],
        *,
        loop_top_n: int = 10,
        max_tokens: int = 512,
    ):
        self.client = reviewer_client
        self.reviewer_model = reviewer_model
        self.retriever = retriever
        self.chunk_texts = chunk_texts
        self.loop_top_n = loop_top_n
        self.max_tokens = max_tokens

    async def _generate_json(self, system: str, prompt: str) -> dict | None:
        result = await self.client.generate(
            prompt=prompt, system_prompt=system, temperature=0.0,
            max_tokens=self.max_tokens,
        )
        return parse_llm_json(getattr(result, "content", "") or "")

    async def _retrieve(self, query: str) -> list[str]:
        out = self.retriever(query)
        if hasattr(out, "__await__"):
            out = await out
        return list(out)

    async def screen_one(self, sample: GoldenSample) -> tuple[GateDecision, GoldenSample]:
        texts = [
            self.chunk_texts[c] for c in sample.expected_chunk_ids if c in self.chunk_texts
        ]
        if not texts:
            return GateDecision(
                sample.id, "dropped", "answerability", "expected chunk 正文缺失"
            ), sample

        # 信号一：异模型可答性
        data = await self._generate_json(
            _ANSWERABILITY_SYSTEM,
            build_answerability_prompt(sample.query, texts),
        )
        if not data or not data.get("answerable") or not (data.get("answer") or "").strip():
            return GateDecision(
                sample.id, "dropped", "answerability", "异模型据 chunk 答不出"
            ), sample
        reviewer_answer = data["answer"].strip()

        # 信号三：答案自洽（与信号一共用一次回答，先算避免白跑检索）
        if sample.golden_answer:
            verdict = await self._generate_json(
                _CONSISTENCY_SYSTEM,
                build_consistency_prompt(sample.query, sample.golden_answer, reviewer_answer),
            )
            if not verdict or not verdict.get("consistent"):
                reason = (verdict or {}).get("reason", "无法判定")
                return GateDecision(
                    sample.id, "dropped", "consistency", f"答案分歧: {reason}"
                ), sample

        # 信号二：第三方检索回环 → 难例桶（不丢弃，单列）
        top = await self._retrieve(sample.query)
        if not set(sample.expected_chunk_ids) & set(top[: self.loop_top_n]):
            return GateDecision(
                sample.id, "hard", "retrieval_loop",
                f"独立检索 top-{self.loop_top_n} 未命中 expected",
            ), sample

        return GateDecision(sample.id, "passed"), sample

    async def screen(self, samples: list[GoldenSample]) -> GateReport:
        report = GateReport(total=len(samples))
        for sample in samples:
            decision, s = await self.screen_one(sample)
            report.decisions.append(decision)
            if decision.verdict == "passed":
                report.passed.append(s)
            elif decision.verdict == "hard":
                report.hard.append(s)
            else:
                report.dropped.append(decision)
        return report
