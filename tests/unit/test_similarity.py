from __future__ import annotations

import hashlib

import pytest

from linkrag_eval.compute.similarity import (
    cosine_float64,
    normalize_similarity_text,
    vector_float32_sha256,
)


def test_similarity_text_normalization_is_frozen() -> None:
    assert normalize_similarity_text("  ＡＢＣ<br>\n<img src='x'>  额度　3000  ") == "ABC 额度 3000"
    assert normalize_similarity_text("值&lt;5，且<b>不</b>允许") == "值<5,且 不 允许"


def test_vector_hash_uses_little_endian_float32_bytes() -> None:
    assert vector_float32_sha256([1.0, 2.0], expected_dim=2) == hashlib.sha256(
        b"\x00\x00\x80?\x00\x00\x00@"
    ).hexdigest()


def test_cosine_float64_and_guards() -> None:
    assert cosine_float64([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_float64([1.0, 0.0], [0.0, 1.0]) == 0.0
    with pytest.raises(ValueError, match="dim mismatch"):
        vector_float32_sha256([1.0], expected_dim=2)
    with pytest.raises(ValueError, match="zero norm"):
        cosine_float64([0.0, 0.0], [1.0, 0.0])
