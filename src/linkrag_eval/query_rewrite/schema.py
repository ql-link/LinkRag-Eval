"""Structured query rewrite plan and validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


ROUTES = ("dense", "sparse", "bm25")
QUERY_TYPES = {
    "short_keyword",
    "exact_identifier",
    "long_multi_constraint",
    "semantic_paraphrase",
    "general",
}
DEFAULT_WEIGHTS = {"dense": 0.70, "sparse": 0.15, "bm25": 0.15}
ROUTING_POLICIES = {
    "short_keyword": (
        {"dense": 0.45, "sparse": 0.40, "bm25": 0.15},
        {"dense": 0, "sparse": 3, "bm25": 0},
    ),
    "exact_identifier": (
        {"dense": 0.30, "sparse": 0.35, "bm25": 0.35},
        {"dense": 0, "sparse": 3, "bm25": 3},
    ),
    "long_multi_constraint": (
        {"dense": 0.45, "sparse": 0.40, "bm25": 0.15},
        {"dense": 0, "sparse": 3, "bm25": 0},
    ),
    "semantic_paraphrase": (
        {"dense": 0.70, "sparse": 0.20, "bm25": 0.10},
        {"dense": 4, "sparse": 0, "bm25": 0},
    ),
    "general": (
        dict(DEFAULT_WEIGHTS),
        {"dense": 0, "sparse": 0, "bm25": 0},
    ),
}

_EXACT_TOKEN_RE = re.compile(
    r"(?:[A-Za-z]+[-_/]?\d[A-Za-z0-9._/-]*|\d{4}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?|"
    r"\d+(?:\.\d+)?%|[“\"']([^”\"']+)[”\"'])"
)
_NEGATIONS = ("不", "未", "没", "不能", "禁止", "无需", "不得", "除外", "没有")


def extract_preserved_terms(query: str) -> list[str]:
    """Extract literals that a rewrite must not silently drop."""
    terms: list[str] = []
    for match in _EXACT_TOKEN_RE.finditer(query):
        value = match.group(1) or match.group(0)
        value = value.strip()
        if value and value not in terms:
            terms.append(value)
    for token in sorted(_NEGATIONS, key=len, reverse=True):
        if token in query and not any(token in existing for existing in terms):
            terms.append(token)
    return terms


def _route_map(raw: Any, *, default: Any) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    return {route: source.get(route, default) for route in ROUTES}


@dataclass(frozen=True)
class QueryRewritePlan:
    sample_id: str
    original_query: str
    query_type: str
    dense_query: str
    sparse_query: str
    bm25_query: str
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    protected_candidates: dict[str, int] = field(
        default_factory=lambda: {route: 0 for route in ROUTES}
    )
    preserved_terms: list[str] = field(default_factory=list)
    confidence: float = 0.0
    reason_code: str = ""
    model: str = ""
    prompt_version: str = "query-rewrite-v1"
    fallback: bool = False

    def route_query(self, route: str) -> str:
        if route not in ROUTES:
            raise ValueError(f"unknown rewrite route:{route}")
        return {
            "dense": self.dense_query,
            "sparse": self.sparse_query,
            "bm25": self.bm25_query,
        }[route]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "original_query": self.original_query,
            "query_type": self.query_type,
            "queries": {route: self.route_query(route) for route in ROUTES},
            "weights": dict(self.weights),
            "protected_candidates": dict(self.protected_candidates),
            "preserved_terms": list(self.preserved_terms),
            "confidence": self.confidence,
            "reason_code": self.reason_code,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "fallback": self.fallback,
        }

    @classmethod
    def fallback_plan(
        cls,
        *,
        sample_id: str,
        original_query: str,
        model: str = "",
        prompt_version: str = "query-rewrite-v1",
        reason_code: str = "planner_fallback",
    ) -> "QueryRewritePlan":
        return cls(
            sample_id=sample_id,
            original_query=original_query,
            query_type="general",
            dense_query=original_query,
            sparse_query=original_query,
            bm25_query=original_query,
            weights=dict(DEFAULT_WEIGHTS),
            protected_candidates={route: 0 for route in ROUTES},
            preserved_terms=extract_preserved_terms(original_query),
            confidence=0.0,
            reason_code=reason_code,
            model=model,
            prompt_version=prompt_version,
            fallback=True,
        )

    @classmethod
    def from_model_dict(
        cls,
        raw: dict[str, Any],
        *,
        sample_id: str,
        original_query: str,
        model: str,
        prompt_version: str,
    ) -> "QueryRewritePlan":
        forbidden = {
            "expected_chunk_ids",
            "expected_doc_ids",
            "target_chunk",
            "target_content",
            "qrels",
        }
        if forbidden & set(raw):
            raise ValueError("rewrite response contains forbidden target fields")

        queries = _route_map(raw.get("queries"), default=original_query)
        query_type = str(raw.get("query_type") or "general").strip()
        if query_type not in QUERY_TYPES:
            query_type = "general"
        policy_weights, policy_protected = ROUTING_POLICIES[query_type]
        weights = dict(policy_weights)
        protected = dict(policy_protected)

        normalized_queries = {
            route: str(queries[route] or original_query).strip()[:1000] or original_query
            for route in ROUTES
        }
        preserved = extract_preserved_terms(original_query)
        # Exact literals are most important to the lexical route. Append missing
        # values deterministically rather than accepting a destructive rewrite.
        missing_bm25 = [term for term in preserved if term not in normalized_queries["bm25"]]
        if missing_bm25:
            normalized_queries["bm25"] = (
                normalized_queries["bm25"] + " " + " ".join(missing_bm25)
            ).strip()

        return cls(
            sample_id=sample_id,
            original_query=original_query,
            query_type=query_type,
            dense_query=normalized_queries["dense"],
            sparse_query=normalized_queries["sparse"],
            bm25_query=normalized_queries["bm25"],
            weights=weights,
            protected_candidates=protected,
            preserved_terms=preserved,
            confidence=min(1.0, max(0.0, float(raw.get("confidence") or 0.0))),
            reason_code=str(raw.get("reason_code") or "").strip()[:120],
            model=model,
            prompt_version=prompt_version,
            fallback=False,
        )

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "QueryRewritePlan":
        queries = _route_map(raw.get("queries"), default=raw.get("original_query", ""))
        return cls(
            sample_id=str(raw["sample_id"]),
            original_query=str(raw["original_query"]),
            query_type=str(raw.get("query_type") or "general"),
            dense_query=str(queries["dense"]),
            sparse_query=str(queries["sparse"]),
            bm25_query=str(queries["bm25"]),
            weights={
                route: float(_route_map(raw.get("weights"), default=0.0)[route]) for route in ROUTES
            },
            protected_candidates={
                route: int(_route_map(raw.get("protected_candidates"), default=0)[route])
                for route in ROUTES
            },
            preserved_terms=[str(value) for value in raw.get("preserved_terms") or []],
            confidence=float(raw.get("confidence") or 0.0),
            reason_code=str(raw.get("reason_code") or ""),
            model=str(raw.get("model") or ""),
            prompt_version=str(raw.get("prompt_version") or "query-rewrite-v1"),
            fallback=bool(raw.get("fallback")),
        )
