from __future__ import annotations

import pytest

from linkrag_eval.golden.provenance import QueryProvenance
from linkrag_eval.golden.schema import GoldenSample


def test_opensource_provenance_round_trip() -> None:
    provenance = QueryProvenance(
        source_kind="opensource",
        source_name="T2Retrieval",
        source_record_id="q1",
        domain="general",
        scenario="retrieval",
        canonical_query="如何取件",
        dataset_version="main@sha",
        license="Apache-2.0",
    )
    sample = GoldenSample(
        id="q1", query="如何取件", user_id=1, dataset_ids=[1], expected_chunk_ids=["c1"],
        provenance=provenance,
    )

    restored = GoldenSample.from_dict(sample.to_dict())

    assert restored.provenance == provenance
    assert restored.provenance.is_real_query


def test_synthetic_provenance_requires_generator() -> None:
    value = QueryProvenance(
        source_kind="synthetic", source_name="x", source_record_id="1", domain="d",
        scenario="s", canonical_query="q",
    )
    with pytest.raises(ValueError, match="generator_model"):
        value.validate()
