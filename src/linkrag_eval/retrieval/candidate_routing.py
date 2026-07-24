"""Deterministic query routing for retrieval candidate depth selection."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping


ROUTES = ("dense", "sparse", "bm25")
BASELINE_THRESHOLDS = {"dense": 0.30, "sparse": 0.20, "bm25": 0.0}


@dataclass(frozen=True)
class CandidateDepths:
    dense: int
    sparse: int
    bm25: int

    @property
    def budget(self) -> int:
        return self.dense + self.sparse + self.bm25

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


BASELINE_DEPTHS = CandidateDepths(dense=150, sparse=50, bm25=100)
GLOBAL_FALLBACK_DEPTHS = CandidateDepths(dense=200, sparse=50, bm25=200)

# Selected on the 2,000-query Tune set. The exact-identifier bucket keeps the
# baseline because the current Tune data has no representative valid sample for
# that bucket; exact lexical coverage remains an LTR feature instead of a manual boost.
FROZEN_ROUTING_DEPTHS = {
    "short_keyword": CandidateDepths(dense=300, sparse=100, bm25=225),
    "exact_identifier": BASELINE_DEPTHS,
    "number_time": CandidateDepths(dense=275, sparse=50, bm25=200),
    "long_multi": CandidateDepths(dense=125, sparse=50, bm25=75),
    "natural_default": CandidateDepths(dense=150, sparse=50, bm25=225),
}

_EXACT_IDENTIFIER_RE = re.compile(
    r"(?:v(?:ersion)?\s*\d+(?:\.\d+)*|"
    r"\d{4}[-/.年]\d{1,2}(?:[-/.月]\d{1,2})?|"
    r"[A-Za-z]{2,}[-_]?[0-9]{2,}|(?<!\d)\d{5,}(?!\d))",
    re.IGNORECASE,
)
_NUMBER_TIME_RE = re.compile(
    r"(?:\d+(?:\.\d+)?|[一二三四五六七八九十百]+)\s*"
    r"(?:分钟|小时|天|日|个月|年|次|%|％)",
    re.IGNORECASE,
)
_QUERY_CLEAN_RE = re.compile(r"[\s，。？！、；：,.?!;:]+")
_CONDITION_MARKERS = ("同时", "并且", "以及", "还是", "是否", "分别", "之后", "之前", "如果", "且")


def classify_candidate_query(query: str) -> str:
    """Classify a query using only runtime-visible text features."""
    if _EXACT_IDENTIFIER_RE.search(query):
        return "exact_identifier"
    if _NUMBER_TIME_RE.search(query):
        return "number_time"

    compact = _QUERY_CLEAN_RE.sub("", query)
    if len(compact) <= 15:
        return "short_keyword"
    marker_count = sum(marker in query for marker in _CONDITION_MARKERS)
    if len(compact) > 35 or marker_count >= 3:
        return "long_multi"
    return "natural_default"


def has_exact_identifier(query: str) -> bool:
    """Return whether query contains an explicit ID, date, or version token."""
    return _EXACT_IDENTIFIER_RE.search(query) is not None


def depths_for_query(query: str) -> CandidateDepths:
    return FROZEN_ROUTING_DEPTHS[classify_candidate_query(query)]


def first_expected_hit(
    row: Mapping[str, Any],
    route: str,
) -> tuple[int | None, float | None]:
    expected = {str(value) for value in row.get("expected_chunk_ids", [])}
    for index, hit in enumerate(row.get("routes", {}).get(route, []), start=1):
        if str(hit.get("chunk_id")) in expected:
            return index, float(hit.get("score", 0.0))
    return None, None


def candidate_union_hit(
    row: Mapping[str, Any],
    depths: CandidateDepths,
    *,
    thresholds: Mapping[str, float] = BASELINE_THRESHOLDS,
) -> bool:
    for route in ROUTES:
        rank, score = first_expected_hit(row, route)
        if rank is None or score is None:
            continue
        if rank <= getattr(depths, route) and score >= float(thresholds[route]):
            return True
    return False
