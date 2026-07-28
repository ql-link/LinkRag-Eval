"""文档编织：调 LLM 把事实单元自然编织成结构化 markdown（中间结构）。

硬要求：每个 fact 的 anchor 原文必须逐字保留（compose 后逐一校验，缺失
锚点的事实记入 ComposeResult.missing_anchors——它们不会有 ground truth）。
语料编织模型与 QA 生成/门禁复核/判官错开（防双重合成偏置）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from linkrag_eval.golden.gen.generator import TextClient
from linkrag_eval.golden.synth.facts import FactUnit
from linkrag_eval.golden.synth.spec import LENGTH_PROFILE, DocSpec

_COMPOSE_SYSTEM = (
    "你是技术文档撰写助手。你把给定的事实单元自然编织进一篇结构完整的"
    " markdown 文档。只输出 markdown 正文，不要输出任何解释。"
)

_STRUCTURE_HINTS = {
    "headings": "使用至少三级的多级标题（#/##/###），层级清晰",
    "table_heavy": "包含至少两个 markdown 表格，部分事实放进表格单元格",
    "list_heavy": "大量使用有序与无序列表组织内容",
    "long_paragraph": "以长段落为主，少用列表，段落间自然衔接",
    "code_block": "包含至少两个带语言标注的代码块，并配说明文字",
}


@dataclass
class ComposeResult:
    markdown: str
    spec: DocSpec
    facts: list[FactUnit]
    missing_anchors: list[str] = field(default_factory=list)  # fact_id 列表

    @property
    def planted_facts(self) -> list[FactUnit]:
        missing = set(self.missing_anchors)
        return [f for f in self.facts if f.fact_id not in missing]


def build_compose_prompt(spec: DocSpec, topic: str, facts: list[FactUnit]) -> tuple[str, str]:
    fact_lines = "\n".join(
        f"- [{f.section_hint}] {f.statement}\n  （锚点，必须逐字保留：「{f.anchor}」）"
        for f in facts
    )
    user = (
        f"写一篇主题为「{topic}」的 markdown 文档，篇幅{LENGTH_PROFILE[spec.length]['words']}。\n"
        f"结构要求：{_STRUCTURE_HINTS[spec.structure]}。\n\n"
        "把下列事实自然编织进对应章节。每条事实的「锚点短语」必须**原样逐字**出现在"
        "正文中（可在其前后自由组织语句，但锚点内部一个字都不能改）：\n\n"
        f"{fact_lines}\n\n"
        "此外可自由补充相关内容使文档完整自然，但补充内容不得与给定事实矛盾。"
    )
    return _COMPOSE_SYSTEM, user


def check_anchors(markdown: str, facts: list[FactUnit]) -> list[str]:
    """返回锚点未逐字出现的 fact_id（compose 失败的事实）。"""
    return [f.fact_id for f in facts if f.anchor not in markdown]


class DocumentComposer:
    def __init__(
        self,
        client: TextClient,
        model_name: str,
        *,
        temperature: float = 0.7,
        max_retries: int = 1,
    ):
        self.client = client
        self.model_name = model_name
        self.temperature = temperature
        self.max_retries = max_retries

    async def compose(self, spec: DocSpec, topic: str, facts: list[FactUnit]) -> ComposeResult:
        system, user = build_compose_prompt(spec, topic, facts)
        markdown = ""
        missing = [f.fact_id for f in facts]
        for _ in range(self.max_retries + 1):
            result = await self.client.generate(
                prompt=user, system_prompt=system, temperature=self.temperature,
                max_tokens=8192,
            )
            markdown = (getattr(result, "content", "") or "").strip()
            missing = check_anchors(markdown, facts)
            if not missing:
                break
        return ComposeResult(markdown=markdown, spec=spec, facts=facts, missing_anchors=missing)
