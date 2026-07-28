"""参考真值预处理（phase0_5 §4.6）：把真实 GitHub md 归一成"干净标准 md"。

真实 md（首选 `rojasdiego/chinese-markdown`）常混 YAML frontmatter、badges、内嵌
HTML、相对图片链接。一道**一次性轻量过滤**得到可作参考真值的标准 md：去
frontmatter / badge、规整图片引用、丢弃过短或非文档型 md。这是数据准备阶段、
非被测清洗——产出冻结后进 registry（source='chinese-markdown'）。
"""

from __future__ import annotations

import re

_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_BADGE_RE = re.compile(r"^\s*\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)\s*$", re.MULTILINE)  # [![alt](img)](link)
_SHIELD_RE = re.compile(r"!\[[^\]]*\]\(https?://img\.shields\.io/[^)]*\)")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_MULTI_BLANK_RE = re.compile(r"\n{3,}")

MIN_CHARS = 200          # 过短的非文档型 md 丢弃
MIN_HEADINGS = 1         # 至少一个标题，确保是"文档"


def normalize_reference_md(raw: str) -> str | None:
    """归一化原始 md；返回干净标准 md，不合格（过短/非文档型）返回 None。"""
    text = _FRONTMATTER_RE.sub("", raw, count=1)
    text = _BADGE_RE.sub("", text)      # 先去整条 [![alt](img)](link) badge
    text = _SHIELD_RE.sub("", text)     # 再去残留的独立 shields.io 图片
    text = _HTML_COMMENT_RE.sub("", text)
    text = _MULTI_BLANK_RE.sub("\n\n", text).strip()

    if len(text) < MIN_CHARS:
        return None
    if sum(1 for ln in text.splitlines() if re.match(r"^#{1,6}\s+\S", ln)) < MIN_HEADINGS:
        return None
    return text + "\n"
