"""语料/编目落库(``EvalCorpusRepo``,Postgres)。

搬迁自源仓库 ``EvalIngestor`` 的落库部分,去掉生产 ORM 依赖:只写 eval 自持的
``eval_dataset`` / ``eval_corpus_chunk``。索引动作不在此(由 EvalVectorIndexer 编排),
本类只负责"把已索引的 chunk 元数据 + 编目落进 Postgres"。

幂等 ``merge``(按主键覆盖),便于重灌刷新。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from linkrag_eval.store.engine import get_eval_sessionmaker, init_eval_schema
from linkrag_eval.store.models import EvalCorpusChunkDB, EvalDatasetDB


@dataclass(frozen=True)
class CorpusChunkRow:
    """一条待落库的语料 chunk 元数据(索引状态由 indexer 据实际写入结果填)。"""

    chunk_id: str
    dataset_id: int
    doc_id: int
    content: str
    content_hash: str
    source_passage_id: str | None = None
    ordinal: int = 0
    char_len: int | None = None
    token_len: int | None = None
    dense_indexed: bool = False
    sparse_indexed: bool = False
    bm25_indexed: bool = False
    ingest_run_id: str | None = None


class EvalCorpusRepo:
    """eval 语料 + 编目的 Postgres 仓储。"""

    def __init__(self, *, url: str | None = None, sessionmaker: Any | None = None) -> None:
        self._url = url
        self._sm = sessionmaker or get_eval_sessionmaker(url)

    async def init_schema(self) -> None:
        """建表(仅本地/测试;生产用 alembic)。"""
        await init_eval_schema(self._url)

    async def register_dataset(
        self,
        dataset_id: int,
        *,
        name: str,
        source_type: str,
        domain: str | None = None,
        genre: str | None = None,
        relevance_type: str = "binary",
        batch: int | None = None,
        ingestion_ref: str | None = None,
        note: str | None = None,
    ) -> None:
        """写/更新 ``eval_dataset`` 编目行(幂等 merge)。"""
        async with self._sm() as s:
            await s.merge(
                EvalDatasetDB(
                    dataset_id=dataset_id,
                    name=name,
                    source_type=source_type,
                    domain=domain,
                    genre=genre,
                    relevance_type=relevance_type,
                    batch=batch,
                    ingestion_ref=ingestion_ref,
                    note=note,
                )
            )
            await s.commit()

    async def upsert_chunks(self, rows: Sequence[CorpusChunkRow]) -> int:
        """批量落 ``eval_corpus_chunk``(幂等 merge),返回写入行数。"""
        rows = list(rows)
        if not rows:
            return 0
        async with self._sm() as s:
            for r in rows:
                await s.merge(
                    EvalCorpusChunkDB(
                        chunk_id=r.chunk_id,
                        dataset_id=r.dataset_id,
                        doc_id=r.doc_id,
                        source_passage_id=r.source_passage_id,
                        ordinal=r.ordinal,
                        content=r.content,
                        content_hash=r.content_hash,
                        char_len=r.char_len,
                        token_len=r.token_len,
                        dense_indexed=r.dense_indexed,
                        sparse_indexed=r.sparse_indexed,
                        bm25_indexed=r.bm25_indexed,
                        ingest_run_id=r.ingest_run_id,
                    )
                )
            await s.commit()
        return len(rows)
