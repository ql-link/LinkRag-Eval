"""LLM 输出 JSON 容错解析(纯函数,无依赖)。

搬迁自源仓库 ``golden/gen/prompts.py:parse_llm_json``。judge 的 ``generate_json`` 复用它剥
code fence、按括号配平截取首个完整对象,故收在 judge 包内,不牵入整条 gen/ 子树。
"""

from __future__ import annotations

import json
import re
from typing import Any


def parse_llm_json(text: str) -> dict[str, Any] | None:
    """容错解析 LLM 输出:剥 code fence、截取首个 JSON 对象;失败返回 None。"""
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    if not text.startswith("{"):
        start = text.find("{")
        if start == -1:
            return None
        text = text[start:]
    # 按括号配平截取首个完整对象(防模型尾随多余文本)
    depth = 0
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(text[: i + 1])
                except json.JSONDecodeError:
                    return None
                return parsed if isinstance(parsed, dict) else None
    return None
