"""Shared full-pool LTR feature computation; no labels, training or experiment I/O."""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any

import numpy as np

from linkrag_eval.retrieval.learning_to_rank import english_rules
from linkrag_eval.retrieval.tuning import RouteHit, weighted_score_fuse

ROUTES = ("dense", "sparse", "bm25")

BASELINE_WEIGHTS = {"dense": 0.70, "sparse": 0.15, "bm25": 0.15}

BASELINE_THRESHOLDS = {"dense": 0.30, "sparse": 0.20, "bm25": 0.0}

FEATURE_VERSION = "candidate_difference_v3"

ENGLISH_FEATURE_VERSION = "candidate_difference_v3_en_v1"
FEATURE_VERSIONS = (FEATURE_VERSION, ENGLISH_FEATURE_VERSION)


class FeatureContractError(ValueError):
    """An explicit feature version/schema cannot be used with this model/input."""


def rules_version(feature_version: str) -> str:
    if feature_version == FEATURE_VERSION:
        return "legacy_v3"
    if feature_version == ENGLISH_FEATURE_VERSION:
        return english_rules.RULES_VERSION
    raise FeatureContractError(f"unknown LTR feature version: {feature_version}")

FEATURE_NAMES = [
    "dense_score",
    "sparse_log_score",
    "bm25_log_score",
    "dense_norm",
    "sparse_norm",
    "bm25_norm",
    "dense_rr",
    "sparse_rr",
    "bm25_rr",
    "dense_missing",
    "sparse_missing",
    "bm25_missing",
    "route_count",
    "all_routes",
    "dense_sparse_overlap",
    "dense_bm25_overlap",
    "sparse_bm25_overlap",
    "dense_sparse_rr_gap",
    "dense_bm25_rr_gap",
    "sparse_bm25_rr_gap",
    "dense_top12_margin",
    "sparse_top12_margin",
    "bm25_top12_margin",
    "baseline_score",
    "baseline_rr",
    "query_length",
    "query_has_digit",
    "identifier_exact_coverage",
    "number_exact_coverage",
    "negation_overlap_coverage",
    "negation_mismatch",
    "query_bigram_coverage",
    "query_trigram_coverage",
    "condition_coverage",
    "distinctive_query_bigram_coverage",
    "same_doc_candidate_count",
    "same_doc_max_bigram_similarity",
    "content_length_log",
]

_IDENTIFIER_RE = re.compile(
    r"(?i)(?:v(?:ersion)?\s*)?\d+(?:\.\d+){1,3}|"
    r"\d{4}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?|"
    r"[a-z]{1,12}[-_]?[a-z0-9]*\d[a-z0-9._-]*|\d{4,}"
)

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

_NEGATIONS = ("尚未", "不得", "禁止", "不能", "不会", "无需", "未", "不", "无", "否", "非")

_CLAUSE_SPLIT_RE = re.compile(r"[，,。；;？?！!]|并且|同时|以及|如果|但是|但|仍然|仍|而且")

_TEXT_CLEAN_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+", re.IGNORECASE)

def _route_hits(row: dict[str, Any], source: str) -> list[RouteHit]:
    return [
        RouteHit(
            chunk_id=str(hit["chunk_id"]),
            doc_id=int(hit["doc_id"]),
            dataset_id=int(hit["dataset_id"]),
            score=float(hit["score"]),
            source=source,
        )
        for hit in row["routes"].get(source, [])
    ]

def _normalized(hits: list[RouteHit], source: str) -> dict[str, float]:
    if not hits:
        return {}
    transformed = [
        hit.score if source == "dense" else math.log1p(max(0.0, hit.score)) for hit in hits
    ]
    low, high = min(transformed), max(transformed)
    if high == low:
        return {hit.chunk_id: 1.0 for hit in hits}
    return {hit.chunk_id: (score - low) / (high - low) for hit, score in zip(hits, transformed)}

def _baseline_hits(route_hits: dict[str, list[RouteHit]]) -> dict[str, list[RouteHit]]:
    return {
        source: [hit for hit in hits if hit.score >= BASELINE_THRESHOLDS[source]]
        for source, hits in route_hits.items()
    }

def _normalized_text(value: str) -> str:
    return _TEXT_CLEAN_RE.sub("", value).lower()

def _ngrams(value: str, size: int) -> set[str]:
    text = _normalized_text(value)
    return {text[index : index + size] for index in range(max(0, len(text) - size + 1))}

def _coverage(needles: set[str], content: str) -> float:
    if not needles:
        return 0.0
    lowered = content.lower()
    return sum(needle.lower() in lowered for needle in needles) / len(needles)

def _condition_coverage(query: str, content: str, *, feature_version: str = FEATURE_VERSION) -> float:
    rules_version(feature_version)
    clauses = (english_rules.clauses(query, _CLAUSE_SPLIT_RE) if feature_version == ENGLISH_FEATURE_VERSION
               else [part.strip() for part in _CLAUSE_SPLIT_RE.split(query) if len(part.strip()) >= 2])
    if len(clauses) <= 1:
        return 0.0
    content_bigrams = _ngrams(content, 2)
    matched = 0
    for clause in clauses:
        grams = _ngrams(clause, 2)
        if grams and len(grams.intersection(content_bigrams)) / len(grams) >= 0.5:
            matched += 1
    return matched / len(clauses)

def _top12_margin(hits: list[RouteHit], source: str) -> float:
    if len(hits) < 2:
        return 0.0
    values = [
        hit.score if source == "dense" else math.log1p(max(0.0, hit.score)) for hit in hits[:2]
    ]
    return max(0.0, values[0] - values[1]) / max(abs(values[0]), 1e-9)

def build_online_features(
    *,
    query: str,
    routes: dict[str, list[dict[str, Any]]],
    candidate_contents: dict[str, str] | None = None,
    feature_version: str = FEATURE_VERSION,
) -> tuple[list[str], np.ndarray]:
    """Build production-safe features without Golden/qrels/evaluation metadata."""
    rules_version(feature_version)
    english = feature_version == ENGLISH_FEATURE_VERSION
    online_row = {"routes": routes}
    route_hits = {source: _route_hits(online_row, source) for source in ROUTES}
    by_source = {source: {hit.chunk_id: hit for hit in hits} for source, hits in route_hits.items()}
    rank_by_source = {
        source: {hit.chunk_id: rank for rank, hit in enumerate(hits, 1)}
        for source, hits in route_hits.items()
    }
    norms = {source: _normalized(hits, source) for source, hits in route_hits.items()}
    baseline = weighted_score_fuse(
        _baseline_hits(route_hits),
        final_top_k=sum(len(hits) for hits in route_hits.values()),
        weights=BASELINE_WEIGHTS,
    )
    baseline_by_id = {hit.chunk_id: hit for hit in baseline}
    chunk_ids = sorted(
        {hit.chunk_id for hits in route_hits.values() for hit in hits},
        key=lambda chunk_id: (
            baseline_by_id.get(chunk_id).rank if chunk_id in baseline_by_id else 10**9,
            chunk_id,
        ),
    )
    if candidate_contents is None:
        raise ValueError(f"{feature_version} requires candidate contents")
    missing_contents = [chunk_id for chunk_id in chunk_ids if chunk_id not in candidate_contents]
    if missing_contents:
        raise ValueError(
            f"missing candidate contents: {missing_contents[:3]} "
            f"({len(missing_contents)} total)"
        )

    query_identifiers = (english_rules.identifiers(query, _IDENTIFIER_RE) if english else
                         {match.group(0).lower() for match in _IDENTIFIER_RE.finditer(query)})
    query_numbers = (english_rules.numbers(query) if english else
                     {match.group(0).lower() for match in _NUMBER_RE.finditer(query)})
    query_negations = (english_rules.negations(query) if english else {token for token in _NEGATIONS if token in query})
    query_bigrams = _ngrams(query, 2)
    query_trigrams = _ngrams(query, 3)
    candidate_bigrams = {
        chunk_id: _ngrams(candidate_contents[chunk_id], 2) for chunk_id in chunk_ids
    }
    bigram_frequency = Counter(gram for grams in candidate_bigrams.values() for gram in grams)
    distinctive_limit = max(1, math.ceil(len(chunk_ids) * 0.10))
    doc_by_chunk: dict[str, int] = {}
    for source in ROUTES:
        for hit in route_hits[source]:
            doc_by_chunk.setdefault(hit.chunk_id, hit.doc_id)
    chunks_by_doc: dict[int, list[str]] = defaultdict(list)
    for chunk_id in chunk_ids:
        chunks_by_doc[doc_by_chunk[chunk_id]].append(chunk_id)
    top12_margins = {source: _top12_margin(route_hits[source], source) for source in ROUTES}
    features: list[list[float]] = []
    for chunk_id in chunk_ids:
        hits = {source: by_source[source].get(chunk_id) for source in ROUTES}
        ranks = {source: rank_by_source[source].get(chunk_id, 0) for source in ROUTES}
        reciprocal_ranks = {
            source: 1.0 / ranks[source] if ranks[source] else 0.0 for source in ROUTES
        }
        baseline_hit = baseline_by_id.get(chunk_id)
        content = candidate_contents[chunk_id]
        content_negations = (english_rules.negations(content) if english else
                             {token for token in _NEGATIONS if token in content})
        same_doc_chunks = chunks_by_doc[doc_by_chunk[chunk_id]]
        same_doc_similarities = []
        for peer_id in same_doc_chunks:
            if peer_id == chunk_id:
                continue
            union = candidate_bigrams[chunk_id].union(candidate_bigrams[peer_id])
            same_doc_similarities.append(
                len(candidate_bigrams[chunk_id].intersection(candidate_bigrams[peer_id]))
                / len(union)
                if union
                else 0.0
            )
        distinctive_query_grams = {
            gram
            for gram in query_bigrams.intersection(candidate_bigrams[chunk_id])
            if bigram_frequency[gram] <= distinctive_limit
        }
        values = [
            hits["dense"].score if hits["dense"] else 0.0,
            math.log1p(max(0.0, hits["sparse"].score)) if hits["sparse"] else 0.0,
            math.log1p(max(0.0, hits["bm25"].score)) if hits["bm25"] else 0.0,
            norms["dense"].get(chunk_id, 0.0),
            norms["sparse"].get(chunk_id, 0.0),
            norms["bm25"].get(chunk_id, 0.0),
            reciprocal_ranks["dense"],
            reciprocal_ranks["sparse"],
            reciprocal_ranks["bm25"],
            0.0 if hits["dense"] else 1.0,
            0.0 if hits["sparse"] else 1.0,
            0.0 if hits["bm25"] else 1.0,
            float(sum(hit is not None for hit in hits.values())),
            float(all(hit is not None for hit in hits.values())),
            float(hits["dense"] is not None and hits["sparse"] is not None),
            float(hits["dense"] is not None and hits["bm25"] is not None),
            float(hits["sparse"] is not None and hits["bm25"] is not None),
            abs(reciprocal_ranks["dense"] - reciprocal_ranks["sparse"]),
            abs(reciprocal_ranks["dense"] - reciprocal_ranks["bm25"]),
            abs(reciprocal_ranks["sparse"] - reciprocal_ranks["bm25"]),
            top12_margins["dense"],
            top12_margins["sparse"],
            top12_margins["bm25"],
            baseline_hit.score if baseline_hit else 0.0,
            1.0 / (baseline_hit.rank + 1) if baseline_hit else 0.0,
            float(len(query)),
            float(any(char.isdigit() for char in query)),
            (len(query_identifiers & english_rules.identifiers(content, _IDENTIFIER_RE)) / len(query_identifiers)
             if query_identifiers else 0.0) if english else _coverage(query_identifiers, content),
            (len(query_numbers & english_rules.numbers(content)) / len(query_numbers)
             if query_numbers else 0.0) if english else _coverage(query_numbers, content),
            (
                len(query_negations.intersection(content_negations)) / len(query_negations)
                if query_negations
                else 0.0
            ),
            float(
                bool(query_negations) != bool(content_negations)
                or (bool(query_negations) and not query_negations.intersection(content_negations))
            ),
            (
                len(query_bigrams.intersection(candidate_bigrams[chunk_id])) / len(query_bigrams)
                if query_bigrams
                else 0.0
            ),
            (
                len(query_trigrams.intersection(_ngrams(content, 3))) / len(query_trigrams)
                if query_trigrams
                else 0.0
            ),
            _condition_coverage(query, content, feature_version=feature_version),
            len(distinctive_query_grams) / len(query_bigrams) if query_bigrams else 0.0,
            float(len(same_doc_chunks) - 1),
            max(same_doc_similarities, default=0.0),
            math.log1p(len(content)),
        ]
        features.append(values)
    matrix = np.asarray(features, dtype=np.float32)
    if not features:
        matrix = np.empty((0, len(FEATURE_NAMES)), dtype=np.float32)
    return chunk_ids, matrix
