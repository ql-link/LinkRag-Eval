"""仅在 Tune 上选择短关键词低置信度回退 Hybrid 的冻结规则。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class ShortQueryFallbackConfig:
    version: str
    max_query_chars: int
    confidence_threshold: float
    confidence_feature: str = "ltr_top12_margin"
    fallback: str = "hybrid"


def ltr_top12_margin(scores: Iterable[float]) -> float:
    ordered = sorted((float(value) for value in scores), reverse=True)
    if len(ordered) < 2:
        return 1.0
    scale = max(abs(ordered[0]), abs(ordered[1]), 1e-9)
    return max(0.0, ordered[0] - ordered[1]) / scale


def apply_short_query_fallback(
    *,
    query: str,
    ltr_ranked: list[str],
    ltr_scores: list[float],
    hybrid_ranked: list[str],
    config: ShortQueryFallbackConfig,
) -> tuple[list[str], bool, float]:
    confidence = ltr_top12_margin(ltr_scores)
    compact_length = len("".join(query.split()))
    fallback = compact_length <= config.max_query_chars and confidence < config.confidence_threshold
    return (hybrid_ranked if fallback else ltr_ranked), fallback, confidence


def tune_short_query_fallback(
    predictions: list[dict[str, Any]],
    *,
    thresholds: tuple[float, ...] = (0.01, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30),
    max_query_chars_values: tuple[int, ...] = (6, 10, 15),
) -> dict[str, Any]:
    """输入必须是未用于 Blind 的 OOF Tune predictions。"""
    if not predictions or any("query" not in row for row in predictions):
        raise ValueError("Tune predictions 必须包含 query")
    results: list[dict[str, Any]] = []
    for max_chars in max_query_chars_values:
        for threshold in thresholds:
            hit_sum = mrr_sum = fallback_count = lost = gained = 0
            for row in predictions:
                chunk_ids = list(row["candidate_chunk_ids"])
                scores = [float(value) for value in row["candidate_ltr_scores"]]
                ltr_ranked = [
                    item[0]
                    for item in sorted(zip(chunk_ids, scores), key=lambda item: (-item[1], item[0]))
                ]
                hybrid_ranked = [
                    item[0]
                    for item in sorted(
                        zip(chunk_ids, row["candidate_baseline_rr"]),
                        key=lambda item: (-float(item[1]), item[0]),
                    )
                ]
                config = ShortQueryFallbackConfig(
                    version="short_query_fallback_v1",
                    max_query_chars=max_chars,
                    confidence_threshold=threshold,
                )
                ranked, fallback, _ = apply_short_query_fallback(
                    query=str(row["query"]),
                    ltr_ranked=ltr_ranked,
                    ltr_scores=scores,
                    hybrid_ranked=hybrid_ranked,
                    config=config,
                )
                expected = set(str(value) for value in row["expected_chunk_ids"])
                rank = next((i for i, chunk_id in enumerate(ranked[:10], 1) if chunk_id in expected), None)
                ltr_hit = any(chunk_id in expected for chunk_id in ltr_ranked[:10])
                current_hit = rank is not None
                gained += int(current_hit and not ltr_hit)
                lost += int(ltr_hit and not current_hit)
                hit_sum += int(current_hit)
                mrr_sum += 1.0 / rank if rank else 0.0
                fallback_count += int(fallback)
            n = len(predictions)
            results.append(
                {
                    "max_query_chars": max_chars,
                    "confidence_threshold": threshold,
                    "hit_at_10": hit_sum / n,
                    "mrr": mrr_sum / n,
                    "fallback_count": fallback_count,
                    "gained": gained,
                    "lost": lost,
                }
            )
    results.sort(key=lambda row: (-row["hit_at_10"], -row["mrr"], row["lost"], row["fallback_count"]))
    best = results[0]
    config = ShortQueryFallbackConfig(
        version="short_query_fallback_v1",
        max_query_chars=int(best["max_query_chars"]),
        confidence_threshold=float(best["confidence_threshold"]),
    )
    return {"config": asdict(config), "best": best, "results": results}
