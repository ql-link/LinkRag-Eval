"""黄金集生成 prompt(中文自研,taxonomy 参考 RAGAS/DeepEval 但 prompt 自写)。

每个 prompt 强约束 JSON 输出,并要求模型自报 answerable(false 直接丢弃,从源头压低噪声)。
另含真实 query 日志种子路径的补标 prompt(冷启动)。

``parse_llm_json`` 是评测内的纯解析工具,已下沉到 :mod:`linkrag_eval.judge.json_parse`;
此处 re-export 以保持 generator/gate 的旧 import 面不变。
"""

from __future__ import annotations

from linkrag_eval.judge.json_parse import parse_llm_json
from linkrag_eval.models import QuestionType

__all__ = [
    "SYSTEM_PROMPT",
    "build_generation_prompt",
    "build_seed_annotation_prompt",
    "parse_llm_json",
]

SYSTEM_PROMPT = (
    "你是检索评测数据构造助手。你只依据给定的文本片段出题,"
    "绝不引入片段之外的知识。输出必须是一个合法 JSON 对象,不要输出任何其他内容。"
)

_OUTPUT_SCHEMA = """输出 JSON 字段:
- "answerable": bool,给定片段是否真的能完整回答你出的问题;没把握就填 false
- "query": string,问题
- "golden_answer": string,仅依据片段写出的标准答案
- "used_chunk_ids": string 数组,回答实际用到的片段 id
- "reason": string,一句话说明出题依据
若片段信息量不足以出题,输出 {"answerable": false}。"""

_TYPE_INSTRUCTIONS: dict[QuestionType, str] = {
    QuestionType.KEYWORD: (
        "出一个关键词直问式问题:用词贴近片段原文中的具体事实(实体/名称/术语),"
        "答案能在片段中直接找到。"
    ),
    QuestionType.PARAPHRASE: (
        "出一个改写式问题:针对片段中的某一事实,但问法措辞要与原文明显拉开"
        "(换说法、换句式,不复用原文关键词),语义保持等价。"
    ),
    QuestionType.LONGTAIL: (
        "出一个长尾细节问题:针对片段中具体的数字、条件、边界、例外等细节发问,"
        "问题要具体到只有读过该片段才能答上。"
    ),
    QuestionType.CROSS_DOC: (
        "出一个跨片段综合问题:必须同时利用给定的多个片段才能完整回答,"
        "禁止任何单一片段可独立回答。若给定片段间没有可综合的关联,"
        '不要强造,输出 {"answerable": false}。'
    ),
}


def build_generation_prompt(
    type_: QuestionType, chunks: list[tuple[str, str]]
) -> tuple[str, str]:
    """构造 (system, user)。chunks 为 (chunk_id, content) 列表。"""
    blocks = "\n\n".join(
        f"[片段 {cid}]\n{content}" for cid, content in chunks
    )
    user = (
        f"{_TYPE_INSTRUCTIONS[type_]}\n\n{_OUTPUT_SCHEMA}\n\n给定文本片段:\n\n{blocks}"
    )
    return SYSTEM_PROMPT, user


def build_seed_annotation_prompt(
    seed_query: str, chunks: list[tuple[str, str]]
) -> tuple[str, str]:
    """真实 query 日志种子的补标路径:判断哪些片段能答、补 golden_answer。"""
    blocks = "\n\n".join(f"[片段 {cid}]\n{content}" for cid, content in chunks)
    user = (
        "下面是一个真实用户问题与若干候选文本片段。判断这些片段能否回答该问题:\n"
        '- 能:输出 {"answerable": true, "query": 原问题, "golden_answer": 仅依据片段的答案, '
        '"used_chunk_ids": 实际支撑回答的片段 id 数组, "reason": 一句话依据}\n'
        '- 不能:输出 {"answerable": false}\n'
        "输出必须是合法 JSON,不要输出其他内容。\n\n"
        f"用户问题:{seed_query}\n\n候选片段:\n\n{blocks}"
    )
    return SYSTEM_PROMPT, user
