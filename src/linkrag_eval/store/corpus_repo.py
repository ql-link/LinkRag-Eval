"""语料/编目落库(``EvalCorpusRepo``,默认本地 SQLite)。

搬迁自源仓库 ``EvalIngestor`` 的落库部分,去掉生产 ORM 依赖:只写 eval 自持的
``eval_dataset`` / ``eval_corpus_chunk``(本地独立库,绝不碰生产表)。索引动作
不在此(由 EvalVectorIndexer 编排),本类只负责"把已索引的 chunk 元数据 + 编目落库"。

编目使用幂等 ``merge``；语料按主键批量 upsert，便于重灌刷新。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import and_, case, func, or_, select, tuple_, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

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
    dense_input_chars: int | None = None
    sparse_input_chars: int | None = None
    token_len: int | None = None
    dense_indexed: bool = False
    sparse_indexed: bool = False
    bm25_indexed: bool = False
    ingest_run_id: str | None = None


class EvalCorpusRepo:
    """eval 语料 + 编目的本地仓储。"""

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

    async def fetch_ingested_positions(self, dataset_id: int) -> dict[tuple[int, int], str]:
        """返回已完成 dense+sparse 写入的位置及正文 hash，供大批量幂等续灌跳过。"""
        async with self._sm() as s:
            rows = (
                await s.execute(
                    select(
                        EvalCorpusChunkDB.doc_id,
                        EvalCorpusChunkDB.ordinal,
                        EvalCorpusChunkDB.content_hash,
                    ).where(
                        EvalCorpusChunkDB.dataset_id == dataset_id,
                        EvalCorpusChunkDB.dense_indexed.is_(True),
                        EvalCorpusChunkDB.sparse_indexed.is_(True),
                    )
                )
            ).all()
        return {(int(doc_id), int(ordinal)): str(digest) for doc_id, ordinal, digest in rows}

    async def fetch_ingest_rows(
        self, dataset_id: int, chunk_ids: Sequence[str]
    ) -> list[CorpusChunkRow]:
        """仅取当前批次 ID 的续接信息，保留未完成三路写入的记录。

        ``dataset_id`` 是待灌数据集；查询不按它过滤，以免隐藏全局 chunk_id
        已属于其他数据集的冲突。调用方须核对返回行的实际身份、正文与三路标记。
        缺失 ID 不补行，不加载整个数据集的位置或正文。
        """
        ids = list(dict.fromkeys(str(chunk_id) for chunk_id in chunk_ids))
        if not ids:
            return []
        async with self._sm() as s:
            rows = (
                await s.execute(
                    select(EvalCorpusChunkDB).where(EvalCorpusChunkDB.chunk_id.in_(ids))
                )
            ).scalars().all()
        return [
            CorpusChunkRow(
                chunk_id=r.chunk_id,
                dataset_id=r.dataset_id,
                doc_id=r.doc_id,
                content=r.content,
                content_hash=r.content_hash,
                source_passage_id=r.source_passage_id,
                ordinal=r.ordinal,
                char_len=r.char_len,
                dense_input_chars=r.dense_input_chars,
                sparse_input_chars=r.sparse_input_chars,
                token_len=r.token_len,
                dense_indexed=r.dense_indexed,
                sparse_indexed=r.sparse_indexed,
                bm25_indexed=r.bm25_indexed,
                ingest_run_id=r.ingest_run_id,
            )
            for r in rows
        ]

    async def verify_dataset_count(self, *, dataset_id: int, expected_count: int) -> None:
        """核对完整 T2 独立语料库的实际行数与归属，不适用于共享语料库。

        全表总数和指定 dataset 数量都必须等于预期；只聚合计数，不读取正文、
        全量行或索引标记。逐行身份及三路完整性由入库 runner 的批次核查负责。
        """
        async with self._sm() as s:
            total_count, dataset_count = (
                await s.execute(
                    select(
                        func.count(),
                        func.count(case((EvalCorpusChunkDB.dataset_id == dataset_id, 1))),
                    ).select_from(EvalCorpusChunkDB)
                )
            ).one()
        if total_count != expected_count or dataset_count != expected_count:
            raise ValueError(
                "独立语料库数量或归属不一致："
                f"expected_count={expected_count}, total_count={total_count}, "
                f"dataset_id={dataset_id}, dataset_count={dataset_count}, "
                f"other_dataset_count={total_count - dataset_count}"
            )

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
                    dense_input_chars=r.dense_input_chars,
                    sparse_input_chars=r.sparse_input_chars,
                    token_len=r.token_len,
                    dense_indexed=r.dense_indexed,
                    sparse_indexed=r.sparse_indexed,
                    bm25_indexed=r.bm25_indexed,
                    ingest_run_id=r.ingest_run_id,
                )
            )
        return out

    async def fetch_candidate_rows(
        self, candidate_keys: Sequence[tuple[int, str]]
    ) -> list[dict[str, Any]]:
        """按候选的 dataset/chunk 复合键取已有正文及来源；保留空正文和空来源。

        缺失键不补行，调用方对照请求键保留缺口。不读父文档、不按来源 PID 扩展。
        """
        keys = list(dict.fromkeys((int(did), str(cid)) for did, cid in candidate_keys))
        if not keys:
            return []
        async with self._sm() as s:
            rows = (
                await s.execute(
                    select(
                        EvalCorpusChunkDB.dataset_id,
                        EvalCorpusChunkDB.chunk_id,
                        EvalCorpusChunkDB.doc_id,
                        EvalCorpusChunkDB.content,
                        EvalCorpusChunkDB.source_passage_id,
                        EvalCorpusChunkDB.ordinal,
                    ).where(
                        tuple_(EvalCorpusChunkDB.dataset_id, EvalCorpusChunkDB.chunk_id).in_(keys)
                    )
                )
            ).mappings().all()
        return [dict(row) for row in rows]

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
        """单批事务按主键覆盖全部输入字段，保留已有 ``created_at``。"""
        values = [asdict(row) for row in rows]
        if not values:
            return 0
        statement = sqlite_insert(EvalCorpusChunkDB.__table__)
        statement = statement.on_conflict_do_update(
            index_elements=["chunk_id"],
            set_={
                name: statement.excluded[name]
                for name in values[0]
                if name != "chunk_id"
            },
        )
        async with self._sm() as s:
            await s.execute(statement, values)
            await s.commit()
        return len(values)

    async def mark_chunks_pending(self, *, dataset_id: int, chunk_ids: Sequence[str]) -> int:
        """覆盖三路之前使旧完成标记失效；不新增行或改写原文、来源 ID。"""
        ids = list(dict.fromkeys(chunk_ids))
        if not ids:
            return 0
        async with self._sm() as s:
            result = await s.execute(
                update(EvalCorpusChunkDB)
                .where(
                    EvalCorpusChunkDB.dataset_id == dataset_id,
                    EvalCorpusChunkDB.chunk_id.in_(ids),
                )
                .values(
                    dense_indexed=False, sparse_indexed=False, bm25_indexed=False,
                    dense_input_chars=None, sparse_input_chars=None,
                )
            )
            await s.commit()
        return result.rowcount

    async def summarize_encoding_inputs(self, *, dataset_id: int) -> dict[str, Any]:
        """按唯一 chunk 行汇总成功索引的输入长度，不读取正文或正文摘要。

        只统计三路均完成的行。缺少请求长度或全文 char_len 是未知，不补为未缩短；
        两路任一已知缩短即计入一次 either_route_shortened，不因重编码累计重复。
        """
        model = EvalCorpusChunkDB
        complete = and_(model.dense_indexed.is_(True), model.sparse_indexed.is_(True),
                        model.bm25_indexed.is_(True))
        expressions = {"completed_rows": complete}
        invalid = []
        shortened = []
        unchanged = []
        for route in ("dense", "sparse"):
            length = getattr(model, f"{route}_input_chars")
            known = and_(length.is_not(None), model.char_len.is_not(None))
            is_shortened = and_(known, length < model.char_len)
            is_unchanged = and_(known, length == model.char_len)
            expressions[f"{route}_shortened"] = and_(complete, is_shortened)
            expressions[f"{route}_unchanged"] = and_(complete, is_unchanged)
            expressions[f"{route}_unknown"] = and_(complete, ~known)
            invalid.append(and_(complete, or_(
                length < 0, model.char_len < 0, and_(known, length > model.char_len),
                and_(known, length == 0, model.char_len > 0),
            )))
            shortened.append(is_shortened)
            unchanged.append(is_unchanged)
        expressions["either_route_shortened"] = and_(complete, or_(*shortened))
        expressions["both_routes_unchanged"] = and_(complete, and_(*unchanged))
        expressions["invalid_rows"] = or_(*invalid)
        statement = select(
            func.count().label("total_rows"),
            *(func.coalesce(func.sum(case((condition, 1), else_=0)), 0).label(name)
              for name, condition in expressions.items()),
        ).where(model.dataset_id == dataset_id)
        async with self._sm() as s:
            row = (await s.execute(statement)).mappings().one()
        if row["invalid_rows"]:
            raise ValueError("完成索引行的编码输入长度超出原文 char_len 范围")
        completed = int(row["completed_rows"])
        affected = int(row["either_route_shortened"])
        unchanged_count = int(row["both_routes_unchanged"])
        return {
            "dataset_id": dataset_id,
            "total_rows": int(row["total_rows"]),
            "completed_rows": completed,
            "incomplete_rows": int(row["total_rows"]) - completed,
            **{route: {state: int(row[f"{route}_{state}"])
                       for state in ("shortened", "unchanged", "unknown")}
               for route in ("dense", "sparse")},
            "either_route_shortened": affected,
            "both_routes_unchanged": unchanged_count,
            "affected_status_unknown": completed - affected - unchanged_count,
        }

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
