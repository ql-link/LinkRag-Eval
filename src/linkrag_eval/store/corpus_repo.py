"""语料/编目落库(``EvalCorpusRepo``,MySQL 独立库)。

搬迁自源仓库 ``EvalIngestor`` 的落库部分,去掉生产 ORM 依赖:只写 eval 自持的
``eval_dataset`` / ``eval_corpus_chunk``(在 ``tolink_rag_eval_db``,绝不碰生产表)。索引动作
不在此(由 EvalVectorIndexer 编排),本类只负责"把已索引的 chunk 元数据 + 编目落库"。

幂等 ``merge``(按主键覆盖),便于重灌刷新。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from sqlalchemy import select, update

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
    """eval 语料 + 编目的 MySQL 仓储(独立库)。"""

    def __init__(self, *, url: str | None = None, sessionmaker: Any | None = None) -> None:
        self._url = url
        self._sm = sessionmaker or get_eval_sessionmaker(url)

    async def init_schema(self) -> None:
        """建表(仅本地/测试;生产用 alembic)。"""
        await init_eval_schema(self._url)

    async def fetch_status(self, chunk_ids: list[str]) -> dict[str, str]:
        """precheck 用:给一批 chunk_id,返回 ``{存在的 chunk_id: "ACTIVE"}``。

        eval 语料无生命周期态,存在即视为 ACTIVE(满足 ``golden.precheck`` 的注入式 fetch_status)。
        """
        if not chunk_ids:
            return {}
        async with self._sm() as s:
            rows = (
                await s.execute(
                    select(EvalCorpusChunkDB.chunk_id).where(
                        EvalCorpusChunkDB.chunk_id.in_(chunk_ids)
                    )
                )
            ).scalars().all()
        return {cid: "ACTIVE" for cid in rows}

    async def fetch_chunks_for_datasets(
        self, dataset_ids: Sequence[int], *, min_content_chars: int = 0
    ) -> list[CorpusChunkRow]:
        """取若干 dataset 下的全部语料 chunk(按 chunk_id 定序),供采样器分层抽样。

        eval 语料无生命周期态,落库即活;``min_content_chars`` 过滤过短 chunk(降"答不出"噪声)。
        """
        ids = list(dataset_ids)
        if not ids:
            return []
        async with self._sm() as s:
            rows = (
                await s.execute(
                    select(EvalCorpusChunkDB)
                    .where(EvalCorpusChunkDB.dataset_id.in_(ids))
                    .order_by(EvalCorpusChunkDB.chunk_id)
                )
            ).scalars().all()
        out: list[CorpusChunkRow] = []
        for r in rows:
            if len((r.content or "").strip()) < min_content_chars:
                continue
            out.append(
                CorpusChunkRow(
                    chunk_id=r.chunk_id,
                    dataset_id=r.dataset_id,
                    doc_id=r.doc_id,
                    content=r.content,
                    content_hash=r.content_hash,
                    source_passage_id=r.source_passage_id,
                    ordinal=r.ordinal,
                    char_len=r.char_len,
                    token_len=r.token_len,
                    dense_indexed=r.dense_indexed,
                    sparse_indexed=r.sparse_indexed,
                    bm25_indexed=r.bm25_indexed,
                    ingest_run_id=r.ingest_run_id,
                )
            )
        return out

    async def fetch_contents_by_ids(self, chunk_ids: Sequence[str]) -> dict[str, str]:
        """按输入 chunk_id 批量回填正文，仅查询 eval 自持语料表。

        rerank 只需要正文而不需要生产 ``kb_document_chunk``；缺失或空正文的候选由调用方
        保留在融合排序中、但不送模型，以避免因元数据不全破坏候选截断口径。
        """
        ids = list(dict.fromkeys(str(chunk_id) for chunk_id in chunk_ids))
        if not ids:
            return {}
        async with self._sm() as s:
            rows = (
                await s.execute(
                    select(EvalCorpusChunkDB.chunk_id, EvalCorpusChunkDB.content).where(
                        EvalCorpusChunkDB.chunk_id.in_(ids)
                    )
                )
            ).all()
        return {
            str(chunk_id): str(content)
            for chunk_id, content in rows
            if isinstance(content, str) and content.strip()
        }

    async def fetch_chunk_ids_for_docs(self, doc_ids: Sequence[int]) -> dict[int, list[str]]:
        """按 doc_id 取 eval 语料中的 chunk_id,供 doc 粒度标注收缩为 chunk 粒度。"""
        ids = list(dict.fromkeys(int(d) for d in doc_ids))
        if not ids:
            return {}
        async with self._sm() as s:
            rows = (
                await s.execute(
                    select(EvalCorpusChunkDB.doc_id, EvalCorpusChunkDB.chunk_id)
                    .where(EvalCorpusChunkDB.doc_id.in_(ids))
                    .order_by(EvalCorpusChunkDB.doc_id, EvalCorpusChunkDB.ordinal)
                )
            ).all()
        out: dict[int, list[str]] = {doc_id: [] for doc_id in ids}
        for doc_id, chunk_id in rows:
            out.setdefault(int(doc_id), []).append(str(chunk_id))
        return out

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

    async def mark_bm25_indexed(self, chunk_ids: Sequence[str], *, indexed: bool = True) -> int:
        """批量更新 BM25 索引状态。"""
        ids = list(dict.fromkeys(str(c) for c in chunk_ids))
        if not ids:
            return 0
        async with self._sm() as s:
            await s.execute(
                update(EvalCorpusChunkDB)
                .where(EvalCorpusChunkDB.chunk_id.in_(ids))
                .values(bm25_indexed=indexed)
            )
            await s.commit()
        return len(ids)
