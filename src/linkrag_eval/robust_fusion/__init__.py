"""Gate A/B research instrumentation kept separate from production adapters."""

from linkrag_eval.robust_fusion.similarity import (
    cosine_float64,
    normalize_similarity_text,
    vector_float32_sha256,
)

__all__ = [
    "cosine_float64",
    "normalize_similarity_text",
    "vector_float32_sha256",
]
