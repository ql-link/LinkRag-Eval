"""Golden V2 alt embedding searcher。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import linkrag_eval.golden_v2.alt_embedding_search as search_module
from linkrag_eval.golden_v2 import AltEmbeddingSearcher


class _FakeEmbedder:
    async def aembed_query(self, text):
        assert text == "query"
        return [1.0, 0.0]


def _chunks():
    return [
        SimpleNamespace(chunk_id="c1", dataset_id=1, doc_id=11),
        SimpleNamespace(chunk_id="c2", dataset_id=1, doc_id=12),
        SimpleNamespace(chunk_id="c3", dataset_id=2, doc_id=21),
    ]


async def test_alt_embedding_searcher_ranks_and_filters_dataset() -> None:
    searcher = AltEmbeddingSearcher(
        embedder=_FakeEmbedder(),
        chunks=_chunks(),
        vectors=[[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]],
    )

    hits = await searcher.search("query", [1], 2)

    assert [hit.chunk_id for hit in hits] == ["c1", "c2"]
    assert hits[0].score > hits[1].score


async def test_alt_embedding_searcher_python_fallback(monkeypatch) -> None:
    monkeypatch.setattr(search_module, "_np", None)
    searcher = AltEmbeddingSearcher(
        embedder=_FakeEmbedder(),
        chunks=_chunks(),
        vectors=[[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]],
    )

    hits = await searcher.search("query", [], 2)

    assert searcher.backend == "python"
    assert [hit.chunk_id for hit in hits] == ["c1", "c3"]


def test_alt_embedding_searcher_rejects_mismatched_vectors() -> None:
    with pytest.raises(ValueError, match="数量不符"):
        AltEmbeddingSearcher(
            embedder=_FakeEmbedder(),
            chunks=_chunks(),
            vectors=[[1.0, 0.0]],
        )
