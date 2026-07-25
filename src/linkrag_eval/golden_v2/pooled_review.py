"""Top-K pooled 候选的盲化独立复核与多正例 qrels 汇总。"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class PooledReviewReport:
    queries: int
    candidates: int
    reviewers: list[str]
    agreements: int
    disagreements: int
    unresolved: int
    positive_qrels: int
    multi_positive_queries: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def prepare_blinded_pool(
    candidate_pool_path: str | Path,
    *,
    out: str | Path,
    top_n: int = 50,
    salt: str,
) -> int:
    """去除 route/rank/score，输出供独立 reviewer 使用的固定 Top-K pool。"""
    if top_n != 50:
        raise ValueError("最终 pooled review 必须固定 top_n=50")
    if not salt.strip():
        raise ValueError("salt 不能为空")
    pools = _read_jsonl(Path(candidate_pool_path))
    rows: list[dict[str, Any]] = []
    for pool in pools:
        for candidate in list(pool.get("candidates") or [])[:top_n]:
            chunk_id = str(candidate["chunk_id"])
            review_id = hashlib.sha256(
                f"{salt}\n{pool['query_id']}\n{chunk_id}".encode("utf-8")
            ).hexdigest()[:24]
            rows.append(
                {
                    "review_id": review_id,
                    "query_id": str(pool["query_id"]),
                    "query": str(pool["query"]),
                    "chunk_id": chunk_id,
                    "doc_id": int(candidate["doc_id"]),
                    "dataset_id": int(candidate["dataset_id"]),
                    "content": str(candidate.get("content") or ""),
                    "provenance": pool.get("provenance"),
                }
            )
    _write_jsonl(Path(out), rows)
    return len(rows)


def merge_independent_reviews(
    blinded_pool_path: str | Path,
    review_paths: Iterable[str | Path],
    *,
    out: str | Path,
    qrels_out: str | Path,
    report_out: str | Path | None = None,
    arbitration_path: str | Path | None = None,
    base_qrels_paths: Iterable[str | Path] = (),
) -> PooledReviewReport:
    """要求两个不同 reviewer 独立作答；分歧必须由第三方仲裁，否则不入 qrels。"""
    pool = _read_jsonl(Path(blinded_pool_path))
    by_review_id = {str(row["review_id"]): row for row in pool}
    decisions: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    reviewer_ids: set[str] = set()
    for path in review_paths:
        for row in _read_jsonl(Path(path)):
            review_id = str(row.get("review_id") or "")
            reviewer_id = str(row.get("reviewer_id") or "").strip()
            if review_id not in by_review_id:
                raise ValueError(f"review_id 不在冻结 pool:{review_id}")
            if not reviewer_id:
                raise ValueError("reviewer_id 不能为空")
            if reviewer_id in decisions[review_id]:
                raise ValueError(f"同一 reviewer 重复判定:{review_id}/{reviewer_id}")
            decisions[review_id][reviewer_id] = row
            reviewer_ids.add(reviewer_id)
    if len(reviewer_ids) < 2:
        raise ValueError("独立复核至少需要两个不同 reviewer_id")

    arbitrations = {}
    if arbitration_path:
        arbitrations = {
            str(row["review_id"]): row for row in _read_jsonl(Path(arbitration_path))
        }
    merged: list[dict[str, Any]] = []
    positives: dict[str, list[dict[str, Any]]] = defaultdict(list)
    agreements = disagreements = unresolved = 0
    for review_id, candidate in by_review_id.items():
        per_reviewer = decisions.get(review_id, {})
        if len(per_reviewer) < 2:
            unresolved += 1
            continue
        first_two = sorted(per_reviewer.items())[:2]
        if any(bool(value.get("abstained")) for _, value in first_two):
            disagreements += 1
            arbitration = arbitrations.get(review_id)
            if arbitration is None:
                unresolved += 1
                continue
            arbitrator_id = str(arbitration.get("reviewer_id") or "").strip()
            if not arbitrator_id or arbitrator_id in {item[0] for item in first_two}:
                raise ValueError(f"仲裁 reviewer 必须独立于首轮 reviewer:{review_id}")
            relevant = bool(arbitration.get("relevant"))
            grade = int(arbitration.get("grade", int(relevant)))
            resolution = "arbitrated_abstention"
        elif (labels := [bool(value.get("relevant")) for _, value in first_two])[0] == labels[1]:
            relevant = labels[0]
            grade = min(int(value.get("grade", int(relevant))) for _, value in first_two)
            resolution = "agreement"
            agreements += 1
        else:
            disagreements += 1
            arbitration = arbitrations.get(review_id)
            if arbitration is None:
                unresolved += 1
                continue
            arbitrator_id = str(arbitration.get("reviewer_id") or "").strip()
            if not arbitrator_id or arbitrator_id in {item[0] for item in first_two}:
                raise ValueError(f"仲裁 reviewer 必须独立于首轮 reviewer:{review_id}")
            relevant = bool(arbitration.get("relevant"))
            grade = int(arbitration.get("grade", int(relevant)))
            resolution = "arbitrated"
        grade = max(1, grade) if relevant else 0
        row = {
            **{key: candidate[key] for key in ("review_id", "query_id", "chunk_id", "doc_id", "dataset_id")},
            "relevant": relevant,
            "grade": grade,
            "resolution": resolution,
            "reviewer_ids": [item[0] for item in first_two],
        }
        merged.append(row)
        if relevant:
            positives[str(candidate["query_id"])].append(row)

    base_qrels: dict[str, dict[str, Any]] = {}
    for path in base_qrels_paths:
        for row in _read_jsonl(Path(path)):
            query_id = str(row.get("id") or row.get("query_id") or "")
            if query_id:
                base_qrels[query_id] = row
    qrels = []
    query_by_id = {str(row["query_id"]): str(row["query"]) for row in pool}
    provenance_by_id = {str(row["query_id"]): row.get("provenance") for row in pool}
    for query_id in sorted(set(query_by_id) & (set(positives) | set(base_qrels))):
        rows = positives.get(query_id, [])
        base = base_qrels.get(query_id) or {}
        chunk_grades = {
            str(chunk_id): int((base.get("relevance_grades") or {}).get(chunk_id, 1))
            for chunk_id in base.get("expected_chunk_ids") or []
        }
        chunk_grades.update({str(row["chunk_id"]): int(row["grade"]) for row in rows})
        qrels.append(
            {
                "id": query_id,
                "query_id": query_id,
                "query": query_by_id[query_id],
                "user_id": 990001,
                "expected_chunk_ids": sorted(chunk_grades),
                "expected_doc_ids": sorted(
                    {int(value) for value in base.get("expected_doc_ids") or []}
                    | {int(row["doc_id"]) for row in rows}
                ),
                "dataset_ids": sorted(
                    {int(value) for value in base.get("dataset_ids") or []}
                    | {int(row["dataset_id"]) for row in rows}
                ),
                "relevance_grades": chunk_grades,
                "type": "keyword",
                "note": "pooled_top50_independent_review_v1;type_hint=real_search_query",
                "provenance": provenance_by_id[query_id],
            }
        )
    _write_jsonl(Path(out), merged)
    _write_jsonl(Path(qrels_out), qrels)
    report = PooledReviewReport(
        queries=len({str(row["query_id"]) for row in pool}),
        candidates=len(pool),
        reviewers=sorted(reviewer_ids),
        agreements=agreements,
        disagreements=disagreements,
        unresolved=unresolved,
        positive_qrels=sum(len(row["expected_chunk_ids"]) for row in qrels),
        multi_positive_queries=sum(len(row["expected_chunk_ids"]) > 1 for row in qrels),
    )
    if report_out:
        path = Path(report_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
