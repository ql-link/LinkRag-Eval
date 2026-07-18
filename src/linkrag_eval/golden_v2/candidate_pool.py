"""Golden V2 候选池构建。

提供两种模式:
- 纯文件 pilot 模式:从标准化 seeds 与 chunk_records 构造 local BM25 + random。
- 活栈模式:调用注入的 route_search 分别取 bm25/dense/sparse 分路候选,再补 random。
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Sequence


@dataclass(frozen=True)
class CandidatePoolReport:
    queries: int
    chunks: int
    candidates: int
    bm25_top_n: int
    random_n: int
    output_path: str
    report_path: str | None = None
    mode: str = "file"
    routes: list[str] | None = None
    missing_chunks: int = 0
    score_thresholds: dict[str, float | None] | None = None
    source_candidate_counts: dict[str, int] | None = None
    source_query_coverage: dict[str, int] | None = None
    candidates_per_query: dict[str, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        return (
            f"候选池构建完成: queries={self.queries} chunks={self.chunks} "
            f"candidates={self.candidates} bm25_top_n={self.bm25_top_n} "
            f"random_n={self.random_n} mode={self.mode} missing_chunks={self.missing_chunks}"
        )


RouteSearch = Callable[
    [str, list[int], str, int],
    Awaitable[Sequence[Any]],
]


def build_candidate_pool(
    seeds_path: str | Path,
    *,
    chunks_path: str | Path,
    out: str | Path,
    report_out: str | Path | None = None,
    bm25_top_n: int = 50,
    random_n: int = 20,
    seed: int = 13,
) -> CandidatePoolReport:
    seeds = _read_jsonl(Path(seeds_path), label="query_seeds")
    chunks = _read_jsonl(Path(chunks_path), label="chunk_records")
    if not seeds:
        raise ValueError(f"{seeds_path} query seeds 为空")
    if not chunks:
        raise ValueError(f"{chunks_path} chunk_records 为空")
    normalized_chunks = [_normalize_chunk(row, i + 1) for i, row in enumerate(chunks)]
    bm25 = _LocalBm25(normalized_chunks)

    rows: list[dict[str, Any]] = []
    total_candidates = 0
    source_candidate_counts: Counter[str] = Counter()
    source_query_coverage: Counter[str] = Counter()
    per_query_counts: list[int] = []
    for raw_seed in seeds:
        query_id = str(raw_seed.get("seed_id") or raw_seed.get("query_id") or "").strip()
        query = str(raw_seed.get("query") or "").strip()
        if not query_id or not query:
            raise ValueError("query seed 缺 seed_id/query")
        by_chunk: dict[str, dict[str, Any]] = {}

        for rank, (chunk, score) in enumerate(bm25.search(query, top_n=bm25_top_n), start=1):
            _add_candidate(by_chunk, chunk, source="bm25_local", rank=rank, score=score)

        rng = random.Random(_stable_seed(seed, query_id))
        sample_n = min(random_n, len(normalized_chunks))
        for rank, chunk in enumerate(rng.sample(normalized_chunks, sample_n), start=1):
            _add_candidate(by_chunk, chunk, source="random_neighbor", rank=rank, score=0.0)

        candidates = sorted(
            by_chunk.values(),
            key=lambda c: (
                -len(set(c["sources"]) - {"random_neighbor"}),
                min(c["rank_by_source"].values()),
                c["chunk_id"],
            ),
        )
        _accumulate_candidate_stats(
            candidates,
            source_candidate_counts=source_candidate_counts,
            source_query_coverage=source_query_coverage,
        )
        per_query_counts.append(len(candidates))
        total_candidates += len(candidates)
        rows.append(
            {
                "query_id": query_id,
                "query": query,
                "role": raw_seed.get("role")
                or ("hard" if raw_seed.get("hard_reason") else "realistic"),
                "source": raw_seed.get("source", "unknown"),
                "type_hint": raw_seed.get("type_hint"),
                "hard_reason": raw_seed.get("hard_reason"),
                "dataset_ids": sorted({int(c["dataset_id"]) for c in candidates}),
                "candidates": candidates,
            }
        )

    out_path = Path(out)
    _write_jsonl(out_path, rows)
    report = CandidatePoolReport(
        queries=len(rows),
        chunks=len(normalized_chunks),
        candidates=total_candidates,
        bm25_top_n=bm25_top_n,
        random_n=random_n,
        output_path=str(out_path),
        report_path=str(report_out) if report_out else None,
        source_candidate_counts=dict(sorted(source_candidate_counts.items())),
        source_query_coverage=dict(sorted(source_query_coverage.items())),
        candidates_per_query=_summarize_counts(per_query_counts),
    )
    if report_out:
        path = Path(report_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


async def build_live_candidate_pool(
    seeds_path: str | Path,
    *,
    chunks: Sequence[Any],
    route_search: RouteSearch,
    out: str | Path,
    report_out: str | Path | None = None,
    sources: Sequence[str] = ("bm25", "dense", "sparse"),
    route_top_n: int = 50,
    random_n: int = 20,
    seed: int = 13,
    source_labels: dict[str, str] | None = None,
    score_thresholds: dict[str, float | None] | None = None,
    limit_queries: int | None = None,
    use_seed_dataset_ids: bool = True,
) -> CandidatePoolReport:
    """构造活栈多源候选池。

    ``route_search`` 由 CLI/调用方注入,本模块只处理候选合并和输出 schema,
    不直接 import 生产召回对象。
    """
    seeds = _read_jsonl(Path(seeds_path), label="query_seeds")
    if limit_queries is not None:
        seeds = seeds[: max(0, limit_queries)]
    if not seeds:
        raise ValueError(f"{seeds_path} query seeds 为空")
    normalized_chunks = [_normalize_chunk_obj(row, i + 1) for i, row in enumerate(chunks)]
    if not normalized_chunks:
        raise ValueError("chunks 为空")

    chunk_by_id = {chunk["chunk_id"]: chunk for chunk in normalized_chunks}
    all_dataset_ids = sorted({int(chunk["dataset_id"]) for chunk in normalized_chunks})
    labels = source_labels or {}
    route_sources = [s.strip() for s in sources if s.strip()]
    if not route_sources:
        raise ValueError("sources 不能为空")

    rows: list[dict[str, Any]] = []
    total_candidates = 0
    missing_chunks = 0
    source_candidate_counts: Counter[str] = Counter()
    source_query_coverage: Counter[str] = Counter()
    per_query_counts: list[int] = []
    for raw_seed in seeds:
        query_id = str(raw_seed.get("seed_id") or raw_seed.get("query_id") or "").strip()
        query = str(raw_seed.get("query") or "").strip()
        if not query_id or not query:
            raise ValueError("query seed 缺 seed_id/query")
        dataset_ids = (
            (_seed_dataset_ids(raw_seed) or all_dataset_ids)
            if use_seed_dataset_ids
            else all_dataset_ids
        )
        scoped_chunks = [
            chunk for chunk in normalized_chunks if int(chunk["dataset_id"]) in set(dataset_ids)
        ]
        if not scoped_chunks:
            scoped_chunks = normalized_chunks
        by_chunk: dict[str, dict[str, Any]] = {}

        for source in route_sources:
            hits = await route_search(query, dataset_ids, source, route_top_n)
            label = labels.get(source, f"{source}_live")
            for rank, hit in enumerate(hits, start=1):
                chunk_id = str(getattr(hit, "chunk_id", ""))
                chunk = chunk_by_id.get(chunk_id)
                if chunk is None:
                    missing_chunks += 1
                    continue
                _add_candidate(
                    by_chunk,
                    chunk,
                    source=label,
                    rank=rank,
                    score=float(getattr(hit, "score", 0.0) or 0.0),
                )

        rng = random.Random(_stable_seed(seed, query_id))
        sample_n = min(random_n, len(scoped_chunks))
        for rank, chunk in enumerate(rng.sample(scoped_chunks, sample_n), start=1):
            _add_candidate(by_chunk, chunk, source="random_neighbor", rank=rank, score=0.0)

        candidates = _sort_candidates(by_chunk)
        _accumulate_candidate_stats(
            candidates,
            source_candidate_counts=source_candidate_counts,
            source_query_coverage=source_query_coverage,
        )
        per_query_counts.append(len(candidates))
        total_candidates += len(candidates)
        rows.append(
            {
                "query_id": query_id,
                "query": query,
                "role": raw_seed.get("role")
                or ("hard" if raw_seed.get("hard_reason") else "realistic"),
                "source": raw_seed.get("source", "unknown"),
                "type_hint": raw_seed.get("type_hint"),
                "hard_reason": raw_seed.get("hard_reason"),
                "dataset_ids": sorted({int(c["dataset_id"]) for c in candidates}),
                "candidates": candidates,
            }
        )

    out_path = Path(out)
    _write_jsonl(out_path, rows)
    report = CandidatePoolReport(
        queries=len(rows),
        chunks=len(normalized_chunks),
        candidates=total_candidates,
        bm25_top_n=route_top_n,
        random_n=random_n,
        output_path=str(out_path),
        report_path=str(report_out) if report_out else None,
        mode="live",
        routes=list(route_sources),
        missing_chunks=missing_chunks,
        score_thresholds=score_thresholds,
        source_candidate_counts=dict(sorted(source_candidate_counts.items())),
        source_query_coverage=dict(sorted(source_query_coverage.items())),
        candidates_per_query=_summarize_counts(per_query_counts),
    )
    if report_out:
        path = Path(report_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def _add_candidate(
    by_chunk: dict[str, dict[str, Any]],
    chunk: dict[str, Any],
    *,
    source: str,
    rank: int,
    score: float,
) -> None:
    existing = by_chunk.get(chunk["chunk_id"])
    if existing is None:
        existing = {
            "chunk_id": chunk["chunk_id"],
            "doc_id": chunk["doc_id"],
            "dataset_id": chunk["dataset_id"],
            "content": chunk["content"],
            "sources": [],
            "rank_by_source": {},
            "score_by_source": {},
        }
        by_chunk[chunk["chunk_id"]] = existing
    if source not in existing["sources"]:
        existing["sources"].append(source)
    existing["sources"].sort()
    existing["rank_by_source"][source] = rank
    existing["score_by_source"][source] = score


def _sort_candidates(by_chunk: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        by_chunk.values(),
        key=lambda c: (
            -len(set(c["sources"]) - {"random_neighbor"}),
            min(c["rank_by_source"].values()),
            c["chunk_id"],
        ),
    )


def _accumulate_candidate_stats(
    candidates: Sequence[dict[str, Any]],
    *,
    source_candidate_counts: Counter[str],
    source_query_coverage: Counter[str],
) -> None:
    seen_sources: set[str] = set()
    for candidate in candidates:
        for source in candidate.get("sources", []):
            source_candidate_counts[source] += 1
            seen_sources.add(source)
    for source in seen_sources:
        source_query_coverage[source] += 1


def _summarize_counts(counts: Sequence[int]) -> dict[str, float]:
    if not counts:
        return {"min": 0, "median": 0, "max": 0}
    ordered = sorted(counts)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        median = float(ordered[mid])
    else:
        median = (ordered[mid - 1] + ordered[mid]) / 2
    return {
        "min": float(ordered[0]),
        "median": median,
        "max": float(ordered[-1]),
    }


def _normalize_chunk(row: dict[str, Any], lineno: int) -> dict[str, Any]:
    missing = [field for field in ("chunk_id", "dataset_id", "doc_id", "content") if row.get(field) in (None, "")]
    if missing:
        raise ValueError(f"chunk_records:{lineno} 缺必填字段:{missing}")
    return {
        "chunk_id": str(row["chunk_id"]),
        "dataset_id": int(row["dataset_id"]),
        "doc_id": int(row["doc_id"]),
        "content": str(row["content"]).strip(),
    }


def _normalize_chunk_obj(row: Any, lineno: int) -> dict[str, Any]:
    if isinstance(row, dict):
        return _normalize_chunk(row, lineno)
    return _normalize_chunk(
        {
            "chunk_id": getattr(row, "chunk_id", None),
            "dataset_id": getattr(row, "dataset_id", None),
            "doc_id": getattr(row, "doc_id", None),
            "content": getattr(row, "content", None),
        },
        lineno,
    )


def _seed_dataset_ids(raw_seed: dict[str, Any]) -> list[int]:
    value = raw_seed.get("dataset_ids")
    if value is None:
        value = raw_seed.get("dataset_id")
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    return sorted({int(v) for v in values if str(v).strip()})


class _LocalBm25:
    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        self._chunks = chunks
        self._tokens = [_tokenize(c["content"]) for c in chunks]
        self._tf = [Counter(tokens) for tokens in self._tokens]
        self._avg_len = sum(len(tokens) for tokens in self._tokens) / max(1, len(self._tokens))
        df: Counter[str] = Counter()
        for tokens in self._tokens:
            df.update(set(tokens))
        n = len(chunks)
        self._idf = {term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()}

    def search(self, query: str, *, top_n: int) -> list[tuple[dict[str, Any], float]]:
        terms = _tokenize(query)
        scored: list[tuple[dict[str, Any], float]] = []
        for chunk, tf, tokens in zip(self._chunks, self._tf, self._tokens):
            score = self._score(terms, tf=tf, doc_len=len(tokens))
            if score > 0:
                scored.append((chunk, score))
        scored.sort(key=lambda item: (-item[1], item[0]["chunk_id"]))
        return scored[:top_n]

    def _score(self, terms: list[str], *, tf: Counter[str], doc_len: int) -> float:
        k1 = 1.5
        b = 0.75
        score = 0.0
        for term in terms:
            freq = tf.get(term, 0)
            if not freq:
                continue
            denom = freq + k1 * (1 - b + b * doc_len / max(1.0, self._avg_len))
            score += self._idf.get(term, 0.0) * (freq * (k1 + 1)) / denom
        return score


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens = re.findall(r"[\u4e00-\u9fff]|[a-z0-9_.]+", text)
    return [t for t in tokens if t.strip()]


def _stable_seed(seed: int, query_id: str) -> int:
    digest = hashlib.sha256(f"{seed}:{query_id}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


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
