"""黄金集加载 + 前置自检(可复现的守门)。

``load_golden`` 纯文件解析,零依赖。``precheck`` 校验每条 expected_chunk_ids 对应 chunk
在 **eval 自持语料**(``eval_corpus_chunk``)中存在,否则本轮判无效并报出失效条目
(数据可复现 > 指标好看);失效时回退用 expected_doc_ids 给出降级提示。

与源仓库差异:precheck 原依赖生产 ``ChunkRepository`` + ``AsyncSession``,这里改为**注入式
``fetch_status``**(``list[chunk_id] -> dict[chunk_id, status]``),由 eval 侧用自己的 corpus
仓储实现(存在即视为 ACTIVE),保持对生产零依赖。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Iterable

from linkrag_eval.golden.schema import GoldenSample

_CHUNK_STATUS_ACTIVE = "ACTIVE"
_PRECHECK_BATCH = 500

# 注入式状态查询:给一批 chunk_id,返回 {存在的 chunk_id: status}。
FetchStatus = Callable[[list[str]], Awaitable[dict[str, str]]]


def load_golden(path: str | Path) -> list[GoldenSample]:
    """读 jsonl、逐行校验必填字段;任何一行非法即整体失败(带行号)。"""
    samples: list[GoldenSample] = []
    seen_ids: set[str] = set()
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                sample = GoldenSample.from_dict(json.loads(line))
            except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"{path}:{lineno} 黄金集条目非法: {exc}") from exc
            if sample.id in seen_ids:
                raise ValueError(f"{path}:{lineno} 黄金集 id 重复: {sample.id}")
            seen_ids.add(sample.id)
            samples.append(sample)
    if not samples:
        raise ValueError(f"{path} 黄金集为空")
    return samples


def require_chunk_references(samples: Iterable[GoldenSample]) -> None:
    """主评测可选护栏:拒绝 doc-only golden,避免 recall 指标被 doc 粒度放宽。"""
    missing = [s.id for s in samples if not s.expected_chunk_ids]
    if missing:
        preview = ", ".join(missing[:10])
        more = "" if len(missing) <= 10 else f" ... (+{len(missing) - 10})"
        raise ValueError(
            f"golden 含 {len(missing)} 条 doc-only 样本,缺 expected_chunk_ids: {preview}{more};"
            "请先生成 chunk 粒度 golden,或不要开启 strict chunk 口径。"
        )


@dataclass
class PrecheckReport:
    total: int
    checked_chunk_ids: int
    # sample_id → 在库缺失的 chunk_id 列表
    missing: dict[str, list[str]] = field(default_factory=dict)
    # sample_id → 在库但非 ACTIVE 的 chunk_id 列表
    inactive: dict[str, list[str]] = field(default_factory=dict)
    # 失效样本中带 expected_doc_ids、可作 doc 粒度降级的 sample_id
    doc_fallback_available: list[str] = field(default_factory=list)
    # 无 chunk reference(doc 粒度样本),未参与 chunk 校验
    doc_granularity_samples: int = 0

    @property
    def invalid_sample_ids(self) -> list[str]:
        return sorted(set(self.missing) | set(self.inactive))

    @property
    def ok(self) -> bool:
        return not self.missing and not self.inactive

    def summary(self) -> str:
        if self.ok:
            return (
                f"precheck OK: {self.total} 条样本、{self.checked_chunk_ids} 个 chunk 在库且 ACTIVE"
                f"(doc 粒度样本 {self.doc_granularity_samples} 条未参与 chunk 校验)"
            )
        lines = [
            f"precheck FAILED: {len(self.invalid_sample_ids)}/{self.total} 条样本 reference 失效"
        ]
        for sid in self.invalid_sample_ids:
            parts = []
            if sid in self.missing:
                parts.append(f"缺失 {self.missing[sid]}")
            if sid in self.inactive:
                parts.append(f"非ACTIVE {self.inactive[sid]}")
            fallback = "(可降级 doc 粒度)" if sid in self.doc_fallback_available else ""
            lines.append(f"  - {sid}: {'; '.join(parts)}{fallback}")
        return "\n".join(lines)


async def precheck(
    samples: Iterable[GoldenSample],
    fetch_status: FetchStatus,
) -> PrecheckReport:
    """校验 expected_chunk_ids 全部在 eval 语料中存在(且 ACTIVE);失效条目逐条报出。

    ``fetch_status`` 由调用方注入:给一批 chunk_id,返回 ``{存在的 chunk_id: status}``。
    eval 侧实现可对 ``eval_corpus_chunk`` 查存在性(存在即 ``ACTIVE``)。
    """
    samples = list(samples)
    all_chunk_ids: set[str] = set()
    doc_only = 0
    for s in samples:
        if s.expected_chunk_ids:
            all_chunk_ids.update(s.expected_chunk_ids)
        else:
            doc_only += 1

    status_by_id: dict[str, str] = {}
    ordered = sorted(all_chunk_ids)
    for i in range(0, len(ordered), _PRECHECK_BATCH):
        batch = ordered[i : i + _PRECHECK_BATCH]
        status_by_id.update(await fetch_status(batch))

    report = PrecheckReport(
        total=len(samples),
        checked_chunk_ids=len(all_chunk_ids),
        doc_granularity_samples=doc_only,
    )
    for s in samples:
        missing = [c for c in s.expected_chunk_ids if c not in status_by_id]
        inactive = [
            c
            for c in s.expected_chunk_ids
            if c in status_by_id and status_by_id[c] != _CHUNK_STATUS_ACTIVE
        ]
        if missing:
            report.missing[s.id] = missing
        if inactive:
            report.inactive[s.id] = inactive
        if (missing or inactive) and s.expected_doc_ids:
            report.doc_fallback_available.append(s.id)
    return report
