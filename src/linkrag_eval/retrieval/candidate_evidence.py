"""Pure projection and validation of retrieved candidate evidence.

No release, labels, model, or storage is loaded here. Callers supply the corpus
allowlist and required routes explicitly. The output records retrieval evidence;
it neither assigns relevance to unjudged candidates nor changes their ranking.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from typing import Any

# Known evaluation/construction fields from the original input-isolation checks.
# This is a field-name guard, not a detector for information encoded in free text
# or identifiers. The serializer additionally projects only explicit fields.
METHOD_VIEW_FORBIDDEN_FIELDS = frozenset(
    {
        "source_query_id",
        "source_chunk_id",
        "source_document_id",
        "source_relevance_label",
        "target_equivalence_group_id",
        "target_relation",
        "conflict_type",
        "adjudicability",
        "query_origin",
        "origin",
        "quota_cell",
        "pool_role",
        "pressure_chain",
        "construction_role",
        "query_family_id",
        "document_family_id",
        "version_family_id",
        "counterfactual_template_family_id",
        "evidence_locator_local",
        "evidence_span_local",
        "reviewer_a",
        "reviewer_b",
        "adjudicator",
        "review_status",
        "handbook_version",
        "exposure_status",
        "similarity_band",
    }
)


def ensure_method_view_safe(rows: Sequence[Mapping[str, Any]]) -> None:
    """Reject known evaluation fields, including inside nested containers.

Callers remain responsible for the provenance of text and identifiers. Passing
this check does not establish that arbitrary metadata is safe for a model.
"""

    def walk(value: Any, location: str) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if key in METHOD_VIEW_FORBIDDEN_FIELDS:
                    raise RuntimeError(f"method_view 含禁止字段：{location}.{key}")
                walk(item, f"{location}.{key}")
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                walk(item, f"{location}[{index}]")

    for index, row in enumerate(rows):
        walk(row, f"row[{index}]")


def serialize_candidate_response(
    *,
    query_uid: str,
    response: Any,
    allowed_chunk_ids: AbstractSet[str],
    required_routes: Sequence[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Project a response with ``route_hits`` and ``candidate_hits``.

    ``allowed_chunk_ids`` identifies the retrieval corpus, not expected positive
    answers or qrels. It is used only to reject out-of-corpus hits and is never
    emitted. ``required_routes`` defines the complete route set for this call.
    A missing route differs from a present route with zero hits. Route order,
    candidate order and raw scores are preserved; absent hits have null rank and
    score. Arbitrary hit/response metadata is not copied into the output.
    Summary ``route_hit_counts`` counts the current ``route_hits`` lists; it is
    not the response's potentially pre-filter ``per_source_counts`` statistic.

    The response is duck-typed so this pure helper does not import production
    classes. Constructing/executing a production request remains an adapter job.
    """

    if isinstance(required_routes, str):
        raise TypeError("required_routes must be a sequence of route names")
    routes = tuple(required_routes)
    if not routes or any(not isinstance(route, str) or not route for route in routes):
        raise ValueError("required_routes must contain non-empty route names")
    if len(routes) != len(set(routes)):
        raise ValueError("required_routes contains duplicate names")
    if response.failed_sources:
        raise RuntimeError(f"召回存在失败来源：{response.failed_sources}")
    route_hits = response.route_hits or {}
    if set(route_hits) != set(routes):
        raise RuntimeError(f"route_hits 路集合不符：{sorted(route_hits)}")

    route_maps: dict[str, dict[str, dict[str, Any]]] = {}
    for route in routes:
        route_map: dict[str, dict[str, Any]] = {}
        for rank, hit in enumerate(route_hits[route], start=1):
            chunk_id = str(hit.chunk_id)
            if chunk_id in route_map:
                raise RuntimeError(f"{query_uid}/{route} 出现重复 chunk_id")
            if chunk_id not in allowed_chunk_ids:
                raise RuntimeError(f"{query_uid}/{route} 命中允许语料外的 chunk")
            score = float(hit.score)
            if not math.isfinite(score):
                raise RuntimeError(f"{query_uid}/{route} score 非有限数")
            route_map[chunk_id] = {"retrieved": True, "rank": rank, "raw_score": score}
        route_maps[route] = route_map

    rows: list[dict[str, Any]] = []
    seen_candidates: set[str] = set()
    for rank, hit in enumerate(response.candidate_hits, start=1):
        chunk_id = str(hit.chunk_id)
        if chunk_id in seen_candidates:
            raise RuntimeError(f"{query_uid} candidate_hits 出现重复 chunk_id")
        if chunk_id not in allowed_chunk_ids:
            raise RuntimeError(f"{query_uid} candidate_hits 含允许语料外的 chunk")
        fused_score = float(hit.fused_score)
        if not math.isfinite(fused_score):
            raise RuntimeError(f"{query_uid} fused_score 非有限数")
        seen_candidates.add(chunk_id)
        rows.append(
            {
                "query_uid": query_uid,
                "candidate_rank": rank,
                "chunk_id": chunk_id,
                "doc_id": int(hit.doc_id),
                "dataset_id": int(hit.dataset_id),
                "fused_score": fused_score,
                "route_evidence": {
                    route: route_maps[route].get(
                        chunk_id, {"retrieved": False, "rank": None, "raw_score": None}
                    )
                    for route in routes
                },
            }
        )

    route_union = set().union(*(set(route_map) for route_map in route_maps.values()))
    if seen_candidates != route_union:
        raise RuntimeError("candidate_hits 与逐路命中并集不一致")
    ensure_method_view_safe(rows)
    summary = {
        "query_uid": query_uid,
        "elapsed_ms": int(response.elapsed_ms),
        "candidate_count": len(rows),
        "route_hit_counts": {route: len(route_maps[route]) for route in routes},
        "failed_sources": [],
    }
    return rows, summary
