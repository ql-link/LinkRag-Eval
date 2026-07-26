"""事实单元（fact unit）：文档由原子事实组装，每个事实带 distinctive 锚点。

锚点是低频、可检索的短语（带具体数字/专名/编号的子句），要求编织时原样
保留，作回定位与换分块重定位的持久依据。
"""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from linkrag_eval.golden.gen.generator import TextClient
from linkrag_eval.golden.gen.prompts import parse_llm_json
from linkrag_eval.golden.synth.spec import DocSpec

_FACTS_SYSTEM = (
    "你是评测语料构造助手。你为一篇虚构但格式真实的文档设计原子事实单元。"
    "输出必须是合法 JSON，不要输出任何其他内容。"
)


@dataclass(frozen=True)
class FactUnit:
    fact_id: str            # 内部追踪用，不出现在文档可见文本
    statement: str          # 一句可问可答的事实，须包含 anchor 原文
    anchor: str             # distinctive 短语（带具体数字/专名），编织时不可改写
    section_hint: str       # 应落在文档哪一节（控制分布）
    answer: str             # 该事实对应的标准答案

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FactUnit":
        return cls(**{k: data[k] for k in ("fact_id", "statement", "anchor", "section_hint", "answer")})


def _sections_for(spec: DocSpec) -> list[str]:
    if spec.fact_distribution == "concentrated":
        return ["第二节"]
    if spec.fact_distribution == "cross_section":
        return ["第一节", "第三节", "第五节"]
    return ["第一节", "第二节", "第三节"]  # scattered


def build_facts_prompt(spec: DocSpec, topic: str) -> tuple[str, str]:
    sections = _sections_for(spec)
    user = (
        f"为一篇主题为「{topic}」的虚构文档设计 {spec.n_facts} 个原子事实单元。要求：\n"
        "1. 每个事实是一句可独立提问、可独立回答的陈述；\n"
        "2. 每个事实内嵌一个 distinctive 锚点短语：含具体数字/专名/编号的子句，"
        "全文唯一、低频、可检索（如『额定功率 3.7 千瓦的 XR-204 模块』）；\n"
        f"3. 事实分布在这些章节：{sections}；\n"
        "4. 事实之间不重复、不互相矛盾。\n\n"
        '输出 JSON：{"facts": [{"statement": "含锚点的完整陈述", "anchor": "锚点短语原文", '
        '"section_hint": "章节", "answer": "该事实的标准答案"}]}'
    )
    return _FACTS_SYSTEM, user


class FactPlanner:
    """LLM 生成事实单元；validate 保证锚点确实内嵌且互不包含。"""

    def __init__(self, client: TextClient, model_name: str, *, temperature: float = 0.8):
        self.client = client
        self.model_name = model_name
        self.temperature = temperature

    async def plan(self, spec: DocSpec, topic: str) -> list[FactUnit]:
        system, user = build_facts_prompt(spec, topic)
        result = await self.client.generate(
            prompt=user, system_prompt=system, temperature=self.temperature,
            max_tokens=2048,
        )
        data = parse_llm_json(getattr(result, "content", "") or "")
        if not data or not isinstance(data.get("facts"), list):
            return []
        facts = []
        for item in data["facts"]:
            statement = (item.get("statement") or "").strip()
            anchor = (item.get("anchor") or "").strip()
            answer = (item.get("answer") or "").strip()
            if not statement or not anchor or not answer or anchor not in statement:
                continue
            facts.append(
                FactUnit(
                    fact_id=f"fact-{uuid.uuid4().hex[:10]}",
                    statement=statement,
                    anchor=anchor,
                    section_hint=(item.get("section_hint") or "正文").strip(),
                    answer=answer,
                )
            )
        return validate_facts(facts)


def validate_facts(facts: list[FactUnit]) -> list[FactUnit]:
    """剔除锚点互相包含/重复的事实（会破坏回定位唯一性）。"""
    kept: list[FactUnit] = []
    for f in facts:
        if any(f.anchor in other.anchor or other.anchor in f.anchor for other in kept):
            continue
        kept.append(f)
    return kept


def deterministic_facts(spec: DocSpec, *, seed: int = 0) -> list[FactUnit]:
    """无 LLM 的确定性事实构造（单测与冒烟用）：锚点用合成编号短语。"""
    rng = random.Random(seed)
    sections = _sections_for(spec)
    facts = []
    for i in range(spec.n_facts):
        code = f"ZX-{rng.randint(100, 999)}{chr(65 + i)}"
        value = rng.randint(2, 98)
        anchor = f"编号 {code} 的组件额定值为 {value} 单位"
        facts.append(
            FactUnit(
                fact_id=f"fact-det-{i}",
                statement=f"在性能测试中，{anchor}，超出该值需要降载运行。",
                anchor=anchor,
                section_hint=sections[i % len(sections)],
                answer=f"{value} 单位",
            )
        )
    return facts


def save_facts(facts: list[FactUnit], path: str | Path) -> Path:
    """锚点持久化（B11）：换分块策略后凭此重定位，不必重新生成。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for f in facts:
            fh.write(json.dumps(f.to_dict(), ensure_ascii=False) + "\n")
    return path


def load_facts(path: str | Path) -> list[FactUnit]:
    facts = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                facts.append(FactUnit.from_dict(json.loads(line)))
    return facts
