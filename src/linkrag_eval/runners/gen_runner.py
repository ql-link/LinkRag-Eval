"""黄金集生成运行器:eval 自有语料 → 采样 → LLM 生成 → 自动门禁 → golden jsonl。

「反向合成」主链(区别于 Track B synth 走真实渲染/解析):从冻结评测语料按类型配比
分层采样 chunk,喂生成器产 (query, golden_answer, expected_chunk_ids);可选三信号自动
门禁筛掉答不出/不自洽,回环未命中的进难例桶单列。让 eval 不依赖人工标注自产数据集。

全部依赖注入、零 rag:
- ``sampler``::class:`~linkrag_eval.golden.gen.sampler.ChunkSampler`(读 eval 语料);
- ``generator``::class:`~linkrag_eval.golden.gen.generator.GoldenGenerator`(judge 客户端驱动);
- ``gate_factory``:可选,``{chunk_id: 正文} -> gate``——门禁需 expected 正文与独立检索器,
  二者都依赖采样产出的语料,故工厂在采样后才装配(cli 传真 :class:`AutoQualityGate`,
  测试注入 fake)。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Awaitable, Callable, Sequence

from linkrag_eval.golden.gen.sampler import SampleSpec, SampledChunk
from linkrag_eval.golden.opensource.convert import write_golden_jsonl
from linkrag_eval.golden.schema import GoldenSample
from linkrag_eval.models import QuestionType

# 单 chunk 类型(各取一片正文出题);CROSS_DOC 走相邻 chunk 组,单列。
_SINGLE_TYPES = (QuestionType.KEYWORD, QuestionType.PARAPHRASE, QuestionType.LONGTAIL)

GateFactory = Callable[[dict[str, str]], Any]


@dataclass
class GenRunReport:
    requested: int = 0          # 实际发起的生成请求数
    produced: int = 0           # 生成器吐出的有效样本数(门禁前)
    passed: int = 0             # 入库 golden 条数(门禁后,无门禁=produced)
    hard: int = 0               # 难例桶条数
    dropped: int = 0            # 门禁丢弃条数
    golden_path: str = ""
    hard_path: str | None = None
    gate_summary: str = ""
    gen_summary: str = ""
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"golden 生成: 请求 {self.requested} → 有效 {self.produced} "
            f"→ 入库 {self.passed}(难例 {self.hard} / 丢弃 {self.dropped})",
            f"  写出: {self.golden_path}",
        ]
        if self.hard_path and self.hard:
            lines.append(f"  难例: {self.hard_path}")
        if self.gen_summary:
            lines.append(f"  生成器: {self.gen_summary}")
        if self.gate_summary:
            lines.append(f"  {self.gate_summary}")
        return "\n".join(lines)


def _alloc_singles(
    chunks: Sequence[SampledChunk], quota: dict[QuestionType, int]
) -> list[tuple[SampledChunk, QuestionType]]:
    """把采样到的单 chunk 按各单跳类型的配额顺次切片分配(语料不足则尽力)。"""
    out: list[tuple[SampledChunk, QuestionType]] = []
    offset = 0
    for t in _SINGLE_TYPES:
        need = quota.get(t, 0)
        if need <= 0:
            continue
        for c in chunks[offset : offset + need]:
            out.append((c, t))
        offset += need
    return out


async def run_golden_gen(
    *,
    sampler: Any,
    generator: Any,
    spec: SampleSpec,
    out_path: str | Path,
    gate_factory: GateFactory | None = None,
    hard_path: str | Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> GenRunReport:
    """采样 → 生成 → (可选)门禁 → 写 golden jsonl。返回 :class:`GenRunReport`。

    ``spec.n`` 为目标总条数,按 ``spec.type_mix`` 折成各类型配额;单跳类型共用一次单 chunk
    采样后切片,CROSS_DOC 用相邻 chunk 组。生成器内部对答不出/解析失败静默丢弃并计数。
    """
    quota = spec.quota()
    singles_n = sum(quota.get(t, 0) for t in _SINGLE_TYPES)
    groups_n = quota.get(QuestionType.CROSS_DOC, 0)

    single_chunks: list[SampledChunk] = []
    groups: list[list[SampledChunk]] = []
    if singles_n:
        single_chunks = await sampler.sample_single(replace(spec, n=singles_n))
    if groups_n:
        groups = await sampler.sample_groups(replace(spec, n=groups_n))
    if progress:
        progress(
            f"采样: 单 chunk {len(single_chunks)}/{singles_n}、"
            f"相邻组 {len(groups)}/{groups_n}(类型配额 "
            + ", ".join(f"{t.value}={n}" for t, n in quota.items() if n)
            + ")"
        )

    # 收全本轮可见语料(单 chunk + 组内 chunk),供门禁取正文/建独立检索器。
    chunk_texts: dict[str, str] = {c.chunk_id: c.content for c in single_chunks}
    for g in groups:
        chunk_texts.update({c.chunk_id: c.content for c in g})

    produced: list[GoldenSample] = []
    for chunk, type_ in _alloc_singles(single_chunks, quota):
        sample = await generator.generate_one([chunk], type_)
        if sample is not None:
            produced.append(sample)
    for group in groups:
        sample = await generator.generate_one(list(group), QuestionType.CROSS_DOC)
        if sample is not None:
            produced.append(sample)
    if progress:
        progress(f"生成: {len(produced)} 条有效样本(门禁前)")

    passed: list[GoldenSample] = produced
    hard: list[GoldenSample] = []
    dropped = 0
    gate_summary = ""
    if gate_factory is not None and produced:
        gate = gate_factory(chunk_texts)
        gate_report = await gate.screen(produced)
        passed = gate_report.passed
        hard = gate_report.hard
        dropped = len(gate_report.dropped)
        gate_summary = gate_report.summary()
        if progress:
            progress(gate_summary)

    out_path = Path(out_path)
    write_golden_jsonl(passed, out_path)
    hard_out: str | None = None
    if hard_path is not None and hard:
        hard_out = str(hard_path)
        write_golden_jsonl(hard, hard_path)

    stats = getattr(generator, "stats", None)
    return GenRunReport(
        requested=getattr(stats, "requested", len(produced)),
        produced=len(produced),
        passed=len(passed),
        hard=len(hard),
        dropped=dropped,
        golden_path=str(out_path),
        hard_path=hard_out,
        gate_summary=gate_summary,
        gen_summary=(
            f"丢弃 答不出={getattr(stats, 'dropped_unanswerable', 0)} "
            f"解析错={getattr(stats, 'dropped_parse_error', 0)} "
            f"无效={getattr(stats, 'dropped_invalid', 0)}"
            if stats is not None
            else ""
        ),
    )
