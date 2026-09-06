"""Pure text normalization and numeric similarity primitives.

These helpers preserve their original text and floating-point conventions; they
do not select an encoder, calibrate similarity bands, or decide relevance.
"""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from collections.abc import Sequence

import numpy as np

_BREAK_RE = re.compile(r"(?i)<br\s*/?>")
_IMG_RE = re.compile(r"(?is)<img\b[^>]*>")
_HTML_TAG_RE = re.compile(r"(?is)</?[a-z][^>]*>")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_similarity_text(value: str) -> str:
    """Canonical passage input: HTML-to-text, NFKC, whitespace collapse, no prefix."""

    text = html.unescape(value)
    text = _BREAK_RE.sub(" ", text)
    text = _IMG_RE.sub(" ", text)
    text = _HTML_TAG_RE.sub(" ", text)
    text = unicodedata.normalize("NFKC", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _float32_vector(value: Sequence[float], *, expected_dim: int | None = None) -> np.ndarray:
    vector = np.asarray(value, dtype="<f4")
    if vector.ndim != 1:
        raise ValueError(f"similarity vector must be one-dimensional, got {vector.shape}")
    if expected_dim is not None and vector.size != expected_dim:
        raise ValueError(f"similarity vector dim mismatch: {vector.size} != {expected_dim}")
    if not np.isfinite(vector).all():
        raise ValueError("similarity vector contains NaN or Inf")
    if not np.any(vector):
        raise ValueError("similarity vector has zero norm")
    return vector


def vector_float32_sha256(
    value: Sequence[float], *, expected_dim: int | None = None
) -> str:
    """Hash canonical little-endian float32 bytes, independent of JSON formatting."""

    vector = _float32_vector(value, expected_dim=expected_dim)
    return hashlib.sha256(vector.tobytes(order="C")).hexdigest()


def cosine_float64(left: Sequence[float], right: Sequence[float]) -> float:
    """Cosine with float32 inputs and float64 accumulation; reject invalid vectors."""

    left_vector = _float32_vector(left).astype(np.float64)
    right_vector = _float32_vector(right).astype(np.float64)
    if left_vector.shape != right_vector.shape:
        raise ValueError(f"similarity vector shape mismatch: {left_vector.shape} != {right_vector.shape}")
    denominator = float(np.linalg.norm(left_vector) * np.linalg.norm(right_vector))
    if denominator == 0.0:
        raise ValueError("similarity vector has zero norm")
    value = float(np.dot(left_vector, right_vector) / denominator)
    return min(1.0, max(-1.0, value))
