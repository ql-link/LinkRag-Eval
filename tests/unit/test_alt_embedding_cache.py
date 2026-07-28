"""Alt embedding SQLite sidecar 单测。"""

from __future__ import annotations

from types import SimpleNamespace

from linkrag_eval.store.alt_embedding_cache import (
    AltEmbeddingCache,
    AltEmbeddingPoint,
    alt_embedding_model_key,
)


async def test_alt_embedding_cache_upsert_fetch_and_count(tmp_path) -> None:
    cache = AltEmbeddingCache(tmp_path / "alt.sqlite3")
    model_key = alt_embedding_model_key(base_url="https://alt/v1", model="alt", dim=2)
    await cache.ensure_schema()

    await cache.upsert_vectors(
        [
            AltEmbeddingPoint(
                chunk_id="c1",
                dataset_id=1,
                doc_id=11,
                content_hash="h1",
                vector=[1.0, 0.0],
            )
        ],
        model_key=model_key,
    )

    got = await cache.fetch_vectors(
        [SimpleNamespace(chunk_id="c1", content_hash="h1")], model_key=model_key
    )
    assert got["c1"] == [1.0, 0.0]
    assert await cache.count(model_key=model_key, dataset_ids=[1]) == 1


async def test_alt_embedding_cache_ignores_stale_content_hash(tmp_path) -> None:
    cache = AltEmbeddingCache(tmp_path / "alt.sqlite3")
    model_key = "model"
    await cache.upsert_vectors(
        [
            AltEmbeddingPoint(
                chunk_id="c1",
                dataset_id=1,
                doc_id=11,
                content_hash="old",
                vector=[1.0],
            )
        ],
        model_key=model_key,
    )

    got = await cache.fetch_vectors(
        [SimpleNamespace(chunk_id="c1", content_hash="new")], model_key=model_key
    )

    assert got == {}
