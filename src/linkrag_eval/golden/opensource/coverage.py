"""固定候选与原始四级判断的纯连接及覆盖计数，不决定训练标签或排序。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from linkrag_eval.golden.opensource.datasets import ParsedQrels

CandidateKey = tuple[int, str]
_ISSUES = ("mapping_missing", "mapping_ambiguous", "qrel_conflict")


@dataclass(frozen=True)
class JoinedQuery:
    source_query_id: str
    candidate_keys: tuple[CandidateKey, ...]
    grades: dict[CandidateKey, int]
    issues: dict[CandidateKey, str]


def _candidate_key(value: CandidateKey) -> CandidateKey:
    if (
        not isinstance(value, tuple)
        or len(value) != 2
        or type(value[0]) is not int
        or not isinstance(value[1], str)
        or not value[1]
        or any(char.isspace() for char in value[1])
    ):
        raise ValueError("candidate key 必须是 (整数 dataset_id, 非空字符串 chunk_id)")
    return value


def _unique_keys(values: Sequence[CandidateKey]) -> tuple[CandidateKey, ...]:
    keys = tuple(_candidate_key(value) for value in values)
    if len(set(keys)) != len(keys):
        raise ValueError("candidate/baseline keys 重复")
    return keys


def join_candidate_qrels(
    *,
    source_query_id: str,
    candidate_keys: Sequence[CandidateKey],
    source_rows: Iterable[tuple[int, str, str | None]],
    qrels: ParsedQrels,
) -> JoinedQuery:
    """连接一个已选来源查询，保留所有候选及独立的关联问题。

    source_query_id 应由调用方从完整 queries 清单取得。一个 qrels 对应一个来源
    文件上下文；本函数不把没有任何 qrel 的合法查询当作未知查询 ID。
    source_rows 保留原始重复关系，输入侧负责核实当前 passage 与 chunk 的粒度；
    仅凭传入的局部映射不能证明全语料的唯一性。
    """
    if (
        not isinstance(source_query_id, str)
        or not source_query_id
        or any(char.isspace() for char in source_query_id)
    ):
        raise ValueError("source_query_id 必须是非空字符串 ID")
    keys = _unique_keys(candidate_keys)
    sources: dict[CandidateKey, set[str | None]] = {}
    chunks_by_pid: dict[tuple[int, str], set[CandidateKey]] = {}
    for dataset_id, chunk_id, pid in source_rows:
        key = _candidate_key((dataset_id, chunk_id))
        if pid is not None and not isinstance(pid, str):
            raise ValueError("source_passage_id 必须是字符串或 None")
        if pid is not None and not pid.strip():
            pid = None
        if pid is not None and any(char.isspace() for char in pid):
            raise ValueError("source_passage_id 不能包含空白")
        sources.setdefault(key, set()).add(pid)
        if pid is not None:
            chunks_by_pid.setdefault((dataset_id, pid), set()).add(key)

    grades: dict[CandidateKey, int] = {}
    issues: dict[CandidateKey, str] = {}
    for key in keys:
        pids = sources.get(key, {None})
        if len(pids) != 1:
            issues[key] = "mapping_ambiguous"
            continue
        pid = next(iter(pids))
        if pid is None:
            issues[key] = "mapping_missing"
            continue
        if len(chunks_by_pid[(key[0], pid)]) != 1:
            issues[key] = "mapping_ambiguous"
            continue
        judgment_key = (source_query_id, pid)
        if judgment_key in qrels.conflicts:
            issues[key] = "qrel_conflict"
        elif judgment_key in qrels.grades:
            grade = qrels.grades[judgment_key]
            if type(grade) is not int or grade not in range(4):
                raise ValueError("qrels grade 必须是整数 0、1、2、3")
            grades[key] = grade
    return JoinedQuery(source_query_id, keys, grades, issues)


def _counts(query: JoinedQuery, keys: Sequence[CandidateKey]) -> dict[str, Any]:
    grade_counts = {str(grade): 0 for grade in range(4)}
    issue_counts = {issue: 0 for issue in _ISSUES}
    for key in keys:
        if key in query.grades:
            grade_counts[str(query.grades[key])] += 1
        elif key in query.issues:
            issue_counts[query.issues[key]] += 1
    judged = sum(grade_counts.values())
    total = len(keys)
    return {
        "total": total,
        "grade_counts": grade_counts,
        "judged": judged,
        "unjudged": total - judged - sum(issue_counts.values()),
        "issue_counts": issue_counts,
        "coverage": judged / total if total else None,
    }


def _total_counts(scopes: Sequence[dict[str, Any]]) -> dict[str, Any]:
    total = sum(scope["total"] for scope in scopes)
    judged = sum(scope["judged"] for scope in scopes)
    return {
        "total": total,
        "grade_counts": {
            str(grade): sum(scope["grade_counts"][str(grade)] for scope in scopes)
            for grade in range(4)
        },
        "judged": judged,
        "unjudged": sum(scope["unjudged"] for scope in scopes),
        "issue_counts": {
            issue: sum(scope["issue_counts"][issue] for scope in scopes) for issue in _ISSUES
        },
        "coverage": judged / total if total else None,
    }


def summarize_label_coverage(
    queries: Sequence[JoinedQuery],
    *,
    baseline_orders: Mapping[str, Sequence[CandidateKey]] | None = None,
    k: int | None = None,
) -> dict[str, Any]:
    """汇总完整池及显式基线前 k 项；比例的分母是查询—候选数。

    baseline_orders 和 k 同时提供或同时省略；缺基线的异常查询可先计完整池，
    再由调用方对已取得完整基线的查询子集单独汇总并说明范围。
    """
    if (baseline_orders is None) != (k is None):
        raise ValueError("baseline_orders 和 k 必须同时提供")
    if k is not None and (type(k) is not int or k <= 0):
        raise ValueError("k 必须是正整数")
    qids = [query.source_query_id for query in queries]
    if len(set(qids)) != len(qids):
        raise ValueError("source_query_id 重复；每次汇总只处理一个明确来源上下文")
    if baseline_orders is not None and set(baseline_orders) != set(qids):
        raise ValueError("baseline_orders 的查询集合必须与汇总查询一致")

    per_query: list[dict[str, Any]] = []
    for query in queries:
        keys = _unique_keys(query.candidate_keys)
        key_set = set(keys)
        if not set(query.grades).issubset(key_set) or not set(query.issues).issubset(key_set):
            raise ValueError("grades/issues 含完整候选池之外的键")
        if set(query.grades).intersection(query.issues):
            raise ValueError("同一候选不能同时有已知等级和未决问题")
        if any(type(grade) is not int or grade not in range(4) for grade in query.grades.values()):
            raise ValueError("grade 必须是整数 0、1、2、3")
        if any(issue not in _ISSUES for issue in query.issues.values()):
            raise ValueError("未知的标签连接问题")
        top_counts = None
        if baseline_orders is not None:
            order = _unique_keys(baseline_orders[query.source_query_id])
            if not set(order).issubset(key_set):
                raise ValueError("baseline 含完整候选池之外的键")
            assert k is not None
            if len(order) < min(k, len(keys)):
                raise ValueError("baseline 长度不足以覆盖请求的 Top-k")
            top_counts = _counts(query, order[:k])
        per_query.append(
            {
                "source_query_id": query.source_query_id,
                "pool": _counts(query, keys),
                "baseline_top_k": top_counts,
            }
        )
    return {
        "query_count": len(queries),
        "k": k,
        "per_query": per_query,
        "overall": {
            "pool": _total_counts([row["pool"] for row in per_query]),
            "baseline_top_k": (
                _total_counts([row["baseline_top_k"] for row in per_query])
                if baseline_orders is not None
                else None
            ),
        },
    }
