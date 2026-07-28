"""锚点回定位：按 distinctive 短语在 chunk 正文中匹配，确定 expected_chunk_ids。

归一化匹配而非裸 exact-match（B3）：Track B 的存在理由就是测 PDF/mineru 等
会改写/丢字/重排版的解析路径。三档：
- exact：原文逐字命中；
- normalized：去空白/标点/全半角归一后命中；
- fuzzy：归一化后高阈值相似度（滑窗 SequenceMatcher）；
- miss：真·覆盖缺口，丢弃并按"格式×PDF后端"分桶计数。
注意：丢弃率混合了 compose 失败与解析丢字两类原因，是覆盖缺口指标，
不是可归因的解析保真度指标。多 chunk 命中（事实切到边界）取全部。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from linkrag_eval.golden.synth.facts import FactUnit

_PUNCT_RE = re.compile(r"[\s　，。、；：！？·…—\-–—_,.;:!?'\"“”‘’()（）\[\]【】<>《》|/\\*#`~]+")
_FUZZY_THRESHOLD = 0.85

TIER_EXACT = "exact"
TIER_NORMALIZED = "normalized"
TIER_FUZZY = "fuzzy"
TIER_MISS = "miss"


def normalize(text: str) -> str:
    """NFKC（全半角归一）→ 去空白与标点 → 小写。"""
    text = unicodedata.normalize("NFKC", text)
    text = _PUNCT_RE.sub("", text)
    return text.lower()


def _fuzzy_contains(needle: str, haystack: str, threshold: float) -> bool:
    """归一化后的滑窗相似度：haystack 中是否存在与 needle 相似度 ≥ 阈值的窗口。"""
    n, m = len(needle), len(haystack)
    if n == 0 or m < n // 2:
        return False
    window = n
    step = max(1, n // 4)
    best = 0.0
    for start in range(0, max(1, m - window + 1), step):
        ratio = SequenceMatcher(
            None, needle, haystack[start : start + window + step]
        ).ratio()
        best = max(best, ratio)
        if best >= threshold:
            return True
    return False


def match_anchor(
    anchor: str, content: str, *, fuzzy_threshold: float = _FUZZY_THRESHOLD
) -> str:
    """单 chunk 三档匹配，返回命中档位（TIER_*）或 TIER_MISS。"""
    if anchor in content:
        return TIER_EXACT
    n_anchor, n_content = normalize(anchor), normalize(content)
    if n_anchor and n_anchor in n_content:
        return TIER_NORMALIZED
    if n_anchor and _fuzzy_contains(n_anchor, n_content, fuzzy_threshold):
        return TIER_FUZZY
    return TIER_MISS


@dataclass
class LocateResult:
    fact_id: str
    chunk_ids: list[str] = field(default_factory=list)
    tier: str = TIER_MISS            # 多 chunk 命中时取最好档

    @property
    def located(self) -> bool:
        return bool(self.chunk_ids)


@dataclass
class LocateReport:
    results: list[LocateResult] = field(default_factory=list)
    # 覆盖缺口分桶：(fmt, pdf_backend) → miss 数（诚实声明覆盖不足的路径）
    miss_by_bucket: dict[str, int] = field(default_factory=dict)
    total_by_bucket: dict[str, int] = field(default_factory=dict)

    @property
    def located(self) -> list[LocateResult]:
        return [r for r in self.results if r.located]

    @property
    def miss_rate(self) -> float:
        return (
            sum(1 for r in self.results if not r.located) / len(self.results)
            if self.results
            else 0.0
        )

    def summary(self) -> str:
        buckets = ", ".join(
            f"{b}: {self.miss_by_bucket.get(b, 0)}/{n} miss"
            for b, n in sorted(self.total_by_bucket.items())
        )
        return f"locate: {len(self.located)}/{len(self.results)} 定位成功；分桶 [{buckets}]"


_TIER_ORDER = {TIER_EXACT: 0, TIER_NORMALIZED: 1, TIER_FUZZY: 2, TIER_MISS: 3}


def locate_facts(
    facts: list[FactUnit],
    chunks: dict[str, str],
    *,
    bucket: str = "default",
    report: LocateReport | None = None,
    fuzzy_threshold: float = _FUZZY_THRESHOLD,
) -> LocateReport:
    """对一篇已入库文档的 chunks（chunk_id→content）回定位全部 facts。

    bucket 形如 "pdf×mineru"，用于覆盖缺口分桶；传入 report 可跨文档累计。
    """
    report = report or LocateReport()
    for fact in facts:
        matches: list[tuple[str, str]] = []
        for chunk_id, content in chunks.items():
            tier = match_anchor(fact.anchor, content, fuzzy_threshold=fuzzy_threshold)
            if tier != TIER_MISS:
                matches.append((chunk_id, tier))
        best_tier = (
            min((t for _, t in matches), key=lambda t: _TIER_ORDER[t])
            if matches
            else TIER_MISS
        )
        report.results.append(
            LocateResult(
                fact_id=fact.fact_id,
                chunk_ids=sorted(cid for cid, _ in matches),
                tier=best_tier,
            )
        )
        report.total_by_bucket[bucket] = report.total_by_bucket.get(bucket, 0) + 1
        if not matches:
            report.miss_by_bucket[bucket] = report.miss_by_bucket.get(bucket, 0) + 1
    return report
