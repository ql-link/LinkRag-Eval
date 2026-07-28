"""Golden V2 judgment QC。

对 DeepSeek 标注后的 judgments 做结构化门禁,避免 random 误标、无正例过高、
候选来源缺失等问题直接进入主黄金集。
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class JudgmentQcReport:
    status: str
    total_queries: int
    judged: int
    relevant: int
    unresolved_queries: int
    unresolved_rate: float
    random_candidates: int
    random_relevant: int
    random_relevant_rate: float
    source_counts: dict[str, int]
    relevant_source_counts: dict[str, int]
    failures: list[str]
    warnings: list[str]
    output_path: str | None = None
    markdown_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        return (
            f"Golden V2 QC: status={self.status} queries={self.total_queries} "
            f"judged={self.judged} relevant={self.relevant} "
            f"unresolved_rate={self.unresolved_rate:.3f} "
            f"random_relevant_rate={self.random_relevant_rate:.3f}"
        )


@dataclass(frozen=True)
class ReviewQueueReport:
    total_items: int
    reason_counts: dict[str, int]
    output_path: str
    report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        return f"Golden V2 复核队列: items={self.total_items} reasons={self.reason_counts}"


@dataclass(frozen=True)
class ReviewLabelReport:
    reviewed: int
    relevant: int
    missing_content: int
    reviewer_model: str
    output_path: str
    report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        return (
            f"Golden V2 二次复判: reviewed={self.reviewed} relevant={self.relevant} "
            f"missing_content={self.missing_content} reviewer={self.reviewer_model}"
        )


@dataclass(frozen=True)
class AdjudicationReport:
    input_judgments: int
    review_items: int
    unique_review_items: int
    duplicate_reviews: int
    changed: int
    kept: int
    conflicts: int
    missing_review: int
    output_path: str
    report_path: str | None = None
    conflict_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        return (
            f"Golden V2 仲裁合并: input={self.input_judgments} reviews={self.review_items} "
            f"unique_reviews={self.unique_review_items} "
            f"changed={self.changed} kept={self.kept} conflicts={self.conflicts} "
            f"missing_review={self.missing_review}"
        )


def qc_judgments(
    judgment_paths: Iterable[str | Path],
    *,
    report_out: str | Path | None = None,
    markdown_out: str | Path | None = None,
    max_random_relevant_rate: float = 0.05,
    max_unresolved_rate: float = 0.30,
    min_queries: int = 1,
) -> JudgmentQcReport:
    rows: list[dict[str, Any]] = []
    for path in judgment_paths:
        rows.extend(_read_jsonl(Path(path), label="judgments"))
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_counts: Counter[str] = Counter()
    relevant_source_counts: Counter[str] = Counter()
    random_candidates = 0
    random_relevant = 0

    for row in rows:
        query_id = str(row.get("query_id") or "")
        if not query_id:
            raise ValueError("judgment 缺 query_id")
        grouped[query_id].append(row)
        sources = [str(s) for s in row.get("candidate", {}).get("sources", [])]
        relevant = bool(row.get("relevant")) and int(row.get("grade", 1) or 0) > 0
        for source in sources:
            source_counts[source] += 1
            if relevant:
                relevant_source_counts[source] += 1
        if _is_random_only_sources(sources):
            random_candidates += 1
            if relevant:
                random_relevant += 1

    total_queries = len(grouped)
    relevant = sum(1 for row in rows if row.get("relevant") and int(row.get("grade", 1) or 0) > 0)
    unresolved = sum(
        1
        for query_rows in grouped.values()
        if not any(r.get("relevant") and int(r.get("grade", 1) or 0) > 0 for r in query_rows)
    )
    unresolved_rate = unresolved / total_queries if total_queries else 0.0
    random_rate = random_relevant / random_candidates if random_candidates else 0.0

    failures: list[str] = []
    warnings: list[str] = []
    if total_queries < min_queries:
        failures.append(f"query 数 {total_queries} < min_queries {min_queries}")
    if random_candidates and random_rate > max_random_relevant_rate:
        failures.append(
            f"random_relevant_rate {random_rate:.3f} > {max_random_relevant_rate:.3f}"
        )
    if unresolved_rate > max_unresolved_rate:
        failures.append(f"unresolved_rate {unresolved_rate:.3f} > {max_unresolved_rate:.3f}")
    if not random_candidates:
        warnings.append("没有纯 random_neighbor 候选,无法估计判官 false positive")
    if not any(source.startswith("alt_embedding") for source in source_counts):
        warnings.append("没有 alt_embedding 候选,候选池仍可能偏向当前系统")
    if not relevant:
        failures.append("全部 query 均无 relevant chunk")

    status = "fail" if failures else ("warn" if warnings else "pass")
    report = JudgmentQcReport(
        status=status,
        total_queries=total_queries,
        judged=len(rows),
        relevant=relevant,
        unresolved_queries=unresolved,
        unresolved_rate=unresolved_rate,
        random_candidates=random_candidates,
        random_relevant=random_relevant,
        random_relevant_rate=random_rate,
        source_counts=dict(sorted(source_counts.items())),
        relevant_source_counts=dict(sorted(relevant_source_counts.items())),
        failures=failures,
        warnings=warnings,
        output_path=str(report_out) if report_out else None,
        markdown_path=str(markdown_out) if markdown_out else None,
    )
    if report_out:
        out = Path(report_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if markdown_out:
        out = Path(markdown_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_to_markdown(report), encoding="utf-8")
    return report


def build_review_queue(
    judgment_paths: Iterable[str | Path],
    *,
    out: str | Path,
    report_out: str | Path | None = None,
    include_random_relevant: bool = True,
    include_unresolved: bool = True,
    include_no_alt_support: bool = True,
) -> ReviewQueueReport:
    rows: list[dict[str, Any]] = []
    for path in judgment_paths:
        rows.extend(_read_jsonl(Path(path), label="judgments"))
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("query_id") or "")].append(row)

    queue: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for query_id, query_rows in sorted(grouped.items()):
        positives = [r for r in query_rows if _is_positive(r)]
        has_alt_positive = any(_has_source(r, "alt_embedding") for r in positives)
        if include_unresolved and not positives:
            for row in query_rows:
                _append_review(queue, seen, row, reason="unresolved_query")
            continue
        for row in positives:
            if include_random_relevant and _is_random_only(row):
                _append_review(queue, seen, row, reason="random_relevant")
            if include_no_alt_support and not has_alt_positive:
                _append_review(queue, seen, row, reason="no_alt_positive_support")

    reason_counts = Counter(str(item["review_reason"]) for item in queue)
    out_path = Path(out)
    _write_jsonl(out_path, queue)
    report = ReviewQueueReport(
        total_items=len(queue),
        reason_counts=dict(sorted(reason_counts.items())),
        output_path=str(out_path),
        report_path=str(report_out) if report_out else None,
    )
    if report_out:
        path = Path(report_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


async def label_review_queue(
    review_queue_path: str | Path,
    *,
    candidate_pool_paths: Iterable[str | Path],
    out: str | Path,
    judge_client: Any,
    report_out: str | Path | None = None,
    limit: int | None = None,
) -> ReviewLabelReport:
    queue = _read_jsonl(Path(review_queue_path), label="review_queue")
    if limit is not None:
        queue = queue[:limit]
    content_by_chunk = _load_candidate_content(candidate_pool_paths)
    rows: list[dict[str, Any]] = []
    missing_content = 0
    for item in queue:
        candidate = dict(item.get("candidate") or {})
        chunk_id = str(candidate.get("chunk_id") or "")
        content = content_by_chunk.get(chunk_id, "")
        if not content:
            missing_content += 1
            result = {
                "relevant": False,
                "grade": 0,
                "evidence_span": "",
                "reason": "missing_candidate_content",
            }
        else:
            result = await _review_one(judge_client, item=item, content=content)
        relevant = bool(result.get("relevant", False))
        grade = int(result.get("grade", 1 if relevant else 0) or 0)
        if relevant and grade <= 0:
            grade = 1
        if not relevant:
            grade = 0
        rows.append(
            {
                **item,
                "review_relevant": relevant,
                "review_grade": grade,
                "review_evidence_span": str(result.get("evidence_span") or ""),
                "reviewer_reason": str(result.get("reason") or ""),
                "reviewer_model": getattr(judge_client, "model", "unknown"),
            }
        )

    out_path = Path(out)
    _write_jsonl(out_path, rows)
    report = ReviewLabelReport(
        reviewed=len(rows),
        relevant=sum(1 for row in rows if row["review_relevant"]),
        missing_content=missing_content,
        reviewer_model=getattr(judge_client, "model", "unknown"),
        output_path=str(out_path),
        report_path=str(report_out) if report_out else None,
    )
    if report_out:
        path = Path(report_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def adjudicate_judgments(
    judgment_paths: Iterable[str | Path],
    *,
    review_paths: Iterable[str | Path],
    out: str | Path,
    report_out: str | Path | None = None,
    conflict_out: str | Path | None = None,
    policy: str = "review_overrides",
) -> AdjudicationReport:
    """把第二判官结果合并回主 judgments。

    默认策略 ``review_overrides``:只要存在 review 结果,最终 relevant/grade 以 review
    为准,并保留原判定与复判审计字段。

    ``manual_on_conflict``:复判与原判冲突时不覆盖原判,标记
    ``needs_manual_review`` 并可输出冲突队列;一致时仍用复判确认后的 grade。
    """
    if policy not in {"review_overrides", "manual_on_conflict"}:
        raise ValueError("policy 目前仅支持 review_overrides/manual_on_conflict")
    rows: list[dict[str, Any]] = []
    for path in judgment_paths:
        rows.extend(_read_jsonl(Path(path), label="judgments"))
    reviews: list[dict[str, Any]] = []
    for path in review_paths:
        reviews.extend(_read_jsonl(Path(path), label="review_judgments"))
    review_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    duplicate_reviews = 0
    for review in reviews:
        key = _row_key(review)
        if key in review_by_key:
            duplicate_reviews += 1
        review_by_key[key] = review

    changed = 0
    kept = 0
    conflicts = 0
    missing_review = 0
    out_rows: list[dict[str, Any]] = []
    conflict_rows: list[dict[str, Any]] = []
    for row in rows:
        key = _row_key(row)
        review = review_by_key.get(key)
        if review is None:
            out_rows.append({**row, "adjudication_status": "not_reviewed"})
            missing_review += 1
            continue
        original_relevant = bool(row.get("relevant"))
        original_grade = int(row.get("grade", 0) or 0)
        final_relevant = bool(review.get("review_relevant"))
        final_grade = int(review.get("review_grade", 0) or 0)
        if not final_relevant:
            final_grade = 0
        changed_here = (original_relevant != final_relevant) or (original_grade != final_grade)
        if policy == "manual_on_conflict" and changed_here:
            conflicts += 1
            conflict_row = _adjudicated_row(
                row,
                review=review,
                policy=policy,
                relevant=original_relevant,
                grade=original_grade,
                status="needs_manual_review",
                original_relevant=original_relevant,
                original_grade=original_grade,
            )
            out_rows.append(conflict_row)
            conflict_rows.append(conflict_row)
            continue
        changed += 1 if changed_here else 0
        kept += 0 if changed_here else 1
        out_rows.append(
            _adjudicated_row(
                row,
                review=review,
                policy=policy,
                relevant=final_relevant,
                grade=final_grade,
                status="review_changed" if changed_here else "review_confirmed",
                original_relevant=original_relevant,
                original_grade=original_grade,
            )
        )

    out_path = Path(out)
    _write_jsonl(out_path, out_rows)
    if conflict_out:
        _write_jsonl(Path(conflict_out), conflict_rows)
    report = AdjudicationReport(
        input_judgments=len(rows),
        review_items=len(reviews),
        unique_review_items=len(review_by_key),
        duplicate_reviews=duplicate_reviews,
        changed=changed,
        kept=kept,
        conflicts=conflicts,
        missing_review=missing_review,
        output_path=str(out_path),
        report_path=str(report_out) if report_out else None,
        conflict_path=str(conflict_out) if conflict_out else None,
    )
    if report_out:
        path = Path(report_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def _adjudicated_row(
    row: dict[str, Any],
    *,
    review: dict[str, Any],
    policy: str,
    relevant: bool,
    grade: int,
    status: str,
    original_relevant: bool,
    original_grade: int,
) -> dict[str, Any]:
    return {
        **row,
        "relevant": relevant,
        "grade": grade,
        "adjudication_status": status,
        "adjudication_policy": policy,
        "adjudication_review_reason": review.get("review_reason"),
        "adjudication_original_relevant": original_relevant,
        "adjudication_original_grade": original_grade,
        "adjudication_review_relevant": bool(review.get("review_relevant")),
        "adjudication_review_grade": int(review.get("review_grade", 0) or 0),
        "adjudication_reviewer_model": review.get("reviewer_model", ""),
        "adjudication_reviewer_reason": review.get(
            "reviewer_reason", review.get("review_reason_text", "")
        ),
        "adjudication_review_evidence_span": review.get("review_evidence_span", ""),
    }


async def _review_one(judge_client: Any, *, item: dict[str, Any], content: str) -> dict[str, Any]:
    prompt = (
        "请作为第二判官复核一条检索黄金集标注。"
        "只根据用户问题和候选 chunk 判断是否能提供直接答案或关键证据。"
        "不要受原判定影响,但可参考复核原因。"
        "只输出 JSON,字段为 relevant(boolean)、grade(0-3)、evidence_span、reason。\n\n"
        f"复核原因:{item.get('review_reason')}\n"
        f"原判定: relevant={item.get('original_relevant')} grade={item.get('original_grade')} "
        f"reason={item.get('original_reason')}\n\n"
        f"用户问题:\n{item.get('query', '')}\n\n"
        f"候选 chunk:\n{content}"
    )
    parsed = await judge_client.generate_json(
        prompt=prompt,
        system_prompt="你是检索评测二次复核员。只判断给定 chunk 与 query 的证据相关性。",
        temperature=0.0,
        max_tokens=500,
    )
    if not isinstance(parsed, dict):
        return {"relevant": False, "grade": 0, "reason": "review_json_parse_failed"}
    return parsed


def _load_candidate_content(candidate_pool_paths: Iterable[str | Path]) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in candidate_pool_paths:
        for pool in _read_jsonl(Path(path), label="candidate_pool"):
            for candidate in pool.get("candidates") or []:
                chunk_id = str(candidate.get("chunk_id") or "")
                content = str(candidate.get("content") or "")
                if chunk_id and content and chunk_id not in out:
                    out[chunk_id] = content
    return out


def _row_key(row: dict[str, Any]) -> tuple[str, str]:
    return (
        str(row.get("query_id") or ""),
        str(row.get("candidate", {}).get("chunk_id") or ""),
    )


def _append_review(
    queue: list[dict[str, Any]],
    seen: set[tuple[str, str, str]],
    row: dict[str, Any],
    *,
    reason: str,
) -> None:
    candidate = row.get("candidate", {})
    key = (str(row.get("query_id")), str(candidate.get("chunk_id")), reason)
    if key in seen:
        return
    seen.add(key)
    queue.append(
        {
            "review_reason": reason,
            "query_id": row.get("query_id"),
            "query": row.get("query"),
            "role": row.get("role"),
            "source": row.get("source"),
            "type_hint": row.get("type_hint"),
            "hard_reason": row.get("hard_reason"),
            "candidate": candidate,
            "original_relevant": bool(row.get("relevant")),
            "original_grade": int(row.get("grade", 0) or 0),
            "original_evidence_span": row.get("evidence_span", ""),
            "original_reason": row.get("reason", ""),
            "original_judge_model": row.get("judge_model", ""),
        }
    )


def _is_positive(row: dict[str, Any]) -> bool:
    return bool(row.get("relevant")) and int(row.get("grade", 1) or 0) > 0


def _has_source(row: dict[str, Any], prefix: str) -> bool:
    return any(str(s).startswith(prefix) for s in row.get("candidate", {}).get("sources", []))


def _is_random_only(row: dict[str, Any]) -> bool:
    return _is_random_only_sources(
        [str(s) for s in row.get("candidate", {}).get("sources", [])]
    )


def _is_random_only_sources(sources: list[str]) -> bool:
    return set(sources) == {"random_neighbor"}


def _to_markdown(report: JudgmentQcReport) -> str:
    lines = [
        "# Golden V2 Judgment QC",
        "",
        f"- status: `{report.status}`",
        f"- queries: {report.total_queries}",
        f"- judged: {report.judged}",
        f"- relevant: {report.relevant}",
        f"- unresolved_rate: {report.unresolved_rate:.3f}",
        f"- random_relevant_rate: {report.random_relevant_rate:.3f}",
        "",
        "## Failures",
        *(f"- {item}" for item in report.failures),
        "",
        "## Warnings",
        *(f"- {item}" for item in report.warnings),
        "",
        "## Relevant Source Counts",
        *(f"- {k}: {v}" for k, v in report.relevant_source_counts.items()),
        "",
    ]
    return "\n".join(lines)


def _read_jsonl(path: Path, *, label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno} {label} JSONL 非法:{exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{lineno} {label} 行必须是 object")
            rows.append(row)
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
