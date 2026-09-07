"""完整原始 T2 的有界分批入库；完成状态来自实际语料行，不读取 qrels。"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from contextlib import closing
from itertools import islice
from pathlib import Path

from linkrag_eval.llm.sparse_client import SAFE_SPARSE_FAILURE_REASONS, SparseEncodeError
from linkrag_eval.store.corpus_repo import CorpusChunkRow, EvalCorpusRepo
from linkrag_eval.store.ids import eval_chunk_id
from linkrag_eval.store.indexer import EvalPassage, EvalVectorIndexer
from linkrag_eval.store.sqlite_bm25 import SQLiteBm25Store
from linkrag_eval.store.vector_store import EvalVectorStore


class T2IngestError(RuntimeError):
    """保存已确认完成量及失败批范围；不把远端异常正文写入运行记录。"""

    def __init__(
        self,
        *,
        phase: str,
        progress: dict[str, int],
        first_position: int,
        batch_count: int,
        error_type: str,
        cause_chain: list[dict[str, str | int]] | None = None,
    ) -> None:
        self.phase = phase
        self.progress = dict(progress)
        self.failed_batch = {
            "first_position": first_position,
            "passage_count": batch_count,
        }
        self.error_type = error_type
        self.cause_chain = list(cause_chain or [])
        super().__init__(
            f"T2 入库在 {phase} 阶段失败（{error_type}），"
            f"位置 {first_position}，本批 {batch_count} 段；已完成批次保留。"
        )


def _safe_cause_chain(error: BaseException) -> list[dict[str, str | int]]:
    """仅保留异常类型、HTTP 状态和 Sparse 固定原因；SDK 传输异常可沿 source。"""
    chain: list[dict[str, str | int]] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen and len(chain) < 6:
        seen.add(id(current))
        row: dict[str, str | int] = {"error_type": type(current).__name__}
        status = getattr(current, "status_code", None)
        if type(status) is not int:
            status = getattr(getattr(current, "response", None), "status_code", None)
        if type(status) is int:
            row["http_status"] = status
        if isinstance(current, SparseEncodeError):
            reason = getattr(current, "reason", None)
            if type(reason) is str and reason in SAFE_SPARSE_FAILURE_REASONS:
                row["reason"] = reason
        chain.append(row)
        following = current.__cause__ or getattr(current, "source", None) or current.__context__
        current = following if isinstance(following, BaseException) else None
    return chain


def _passage_batches(
    passages: Iterable[tuple[str, str]], *, doc_id_base: int, batch_size: int
) -> Iterator[list[EvalPassage]]:
    indexed = enumerate(passages)
    while batch := list(islice(indexed, batch_size)):
        yield [
            EvalPassage(source_passage_id=pid, content=text, doc_id=doc_id_base + position)
            for position, (pid, text) in batch
        ]


def _completed_ids(
    *, dataset_id: int, passages: list[EvalPassage], rows: list[CorpusChunkRow]
) -> set[str]:
    expected = {eval_chunk_id(dataset_id, p.doc_id, 0): p for p in passages}
    seen: set[str] = set()
    completed: set[str] = set()
    for row in rows:
        passage = expected.get(row.chunk_id)
        if passage is None or row.chunk_id in seen:
            raise ValueError("续接查询返回非请求或重复 chunk ID")
        seen.add(row.chunk_id)
        if (
            row.dataset_id != dataset_id
            or row.doc_id != passage.doc_id
            or row.ordinal != 0
            or row.source_passage_id != passage.source_passage_id
            or row.content != passage.content
        ):
            raise ValueError("已有 chunk 身份或原始正文与本次输入不一致")
        raw_chars = len(passage.content)
        min_input_chars = 1 if raw_chars else 0
        receipt_valid = (
            type(row.char_len) is int
            and row.char_len == raw_chars
            and all(
                type(input_chars) is int and min_input_chars <= input_chars <= raw_chars
                for input_chars in (row.dense_input_chars, row.sparse_input_chars)
            )
        )
        # 未知或不符的编码凭据需重编码，不冒充全文编码，也不改写原始身份。
        if receipt_valid and row.dense_indexed and row.sparse_indexed and row.bm25_indexed:
            completed.add(row.chunk_id)
    return completed


async def _verify_indexes(
    *,
    dataset_id: int,
    user_id: int,
    passages: list[EvalPassage],
    candidates: set[str],
    vector_store: EvalVectorStore,
    bm25_store: SQLiteBm25Store,
) -> set[str]:
    if not candidates:
        return set()
    doc_ids = {eval_chunk_id(dataset_id, p.doc_id, 0): p.doc_id for p in passages}
    ids = sorted(candidates)
    vectors = await vector_store.fetch_indexed_rows(
        dataset_id=dataset_id, chunk_ids=ids,
        expected_doc_ids={cid: doc_ids[cid] for cid in ids},
    )
    bm25 = await bm25_store.fetch_indexed_rows(
        dataset_id=dataset_id, chunk_ids=ids, user_id=user_id
    )
    for rows in (vectors, bm25):
        for chunk_id, doc_id in rows.items():
            if chunk_id not in candidates or doc_id != doc_ids[chunk_id]:
                raise ValueError("实际索引的 chunk/doc 身份与本批输入不一致")
    return candidates & vectors.keys() & bm25.keys()


async def ingest_t2_passages(
    *,
    passages: Iterable[tuple[str, str]],
    dataset_id: int,
    doc_id_base: int,
    batch_size: int,
    corpus_repo: EvalCorpusRepo,
    indexer: EvalVectorIndexer,
    vector_store: EvalVectorStore,
    bm25_store: SQLiteBm25Store,
    user_id: int,
    expected_passage_count: int,
    on_progress: Callable[[dict[str, int]], None] | None = None,
) -> dict[str, int]:
    """按原始顺序写入一段一 chunk，三路完成且编码长度凭据有效才可跳过。

    调用方须固定本次输入与存储/编码配置。逐批核对实际行与向量；源文件
    耗尽后，三处独立存储的精确总数和范围也须匹配。不信任外部进度游标，
    不加载全量完成位置；失败上抛且不自动重试。
    """
    if dataset_id <= 0 or doc_id_base <= 0 or batch_size <= 0 or expected_passage_count <= 0:
        raise ValueError("dataset_id、doc_id_base、batch_size 和 expected_passage_count 须为正整数")
    if doc_id_base + expected_passage_count - 1 > 2**63 - 1:
        raise ValueError("doc_id 范围超出 SQLite 有符号整数范围")
    progress = {
        "processed_passages": 0,
        "indexed_passages": 0,
        "skipped_passages": 0,
        "completed_batches": 0,
    }
    batches = _passage_batches(passages, doc_id_base=doc_id_base, batch_size=batch_size)
    while True:
        phase = "read"
        batch: list[EvalPassage] = []
        first_position = progress["processed_passages"]
        try:
            batch = next(batches, [])
            if not batch:
                if first_position != expected_passage_count:
                    raise ValueError("原始 collection 段落数少于声明的完整语料数量")
                phase = "final_scope_check"
                await vector_store.verify_collection_count(
                    dataset_id=dataset_id, expected_count=expected_passage_count
                )
                await corpus_repo.verify_dataset_count(
                    dataset_id=dataset_id, expected_count=expected_passage_count
                )
                await bm25_store.verify_dataset_count(
                    dataset_id=dataset_id, user_id=user_id, expected_count=expected_passage_count
                )
                return progress
            if first_position + len(batch) > expected_passage_count:
                raise ValueError("原始 collection 段落数多于声明的完整语料数量")
            chunk_ids = [eval_chunk_id(dataset_id, p.doc_id, 0) for p in batch]
            phase = "resume_check"
            rows = await corpus_repo.fetch_ingest_rows(dataset_id, chunk_ids)
            completed = _completed_ids(dataset_id=dataset_id, passages=batch, rows=rows)
            actual_complete = await _verify_indexes(
                dataset_id=dataset_id, user_id=user_id, passages=batch, candidates=set(chunk_ids),
                vector_store=vector_store, bm25_store=bm25_store,
            )
            completed &= actual_complete
            pending = [p for p, cid in zip(batch, chunk_ids, strict=True) if cid not in completed]
            if pending:
                phase = "index"
                written = await indexer.index_passages(dataset_id, pending)
                if written != len(pending):
                    raise ValueError("索引器报告的写入数量与本批待写数量不一致")
                phase = "completion_check"
                actual = await corpus_repo.fetch_ingest_rows(dataset_id, chunk_ids)
                verified = _completed_ids(dataset_id=dataset_id, passages=batch, rows=actual)
                verified = await _verify_indexes(
                    dataset_id=dataset_id, user_id=user_id, passages=batch, candidates=verified,
                    vector_store=vector_store, bm25_store=bm25_store,
                )
                if len(verified) != len(batch):
                    raise ValueError("本批尚未全部留下三路写入成功的语料记录")
            progress["processed_passages"] += len(batch)
            progress["indexed_passages"] += len(pending)
            progress["skipped_passages"] += len(completed)
            progress["completed_batches"] += 1
            phase = "progress"
            if on_progress is not None:
                on_progress(dict(progress))
        except Exception as exc:  # noqa: BLE001 — 保存故障批范围后立即上抛，不重试或跳过
            raise T2IngestError(
                phase=phase,
                progress=progress,
                first_position=first_position,
                batch_count=len(batch),
                error_type=type(exc).__name__,
                cause_chain=_safe_cause_chain(exc),
            ) from None


async def ingest_t2_collection(
    *,
    collection_path: Path,
    dataset_id: int,
    doc_id_base: int,
    batch_size: int,
    corpus_repo: EvalCorpusRepo,
    indexer: EvalVectorIndexer,
    vector_store: EvalVectorStore,
    bm25_store: SQLiteBm25Store,
    user_id: int,
    expected_passage_count: int,
    on_progress: Callable[[dict[str, int]], None] | None = None,
) -> dict[str, int]:
    """流式读取官方 collection；生成器在成功、中断和异常时都关闭。"""
    from linkrag_eval.golden.opensource.datasets import iter_t2_collection

    with closing(iter_t2_collection(collection_path)) as passages:
        return await ingest_t2_passages(
            passages=passages,
            dataset_id=dataset_id,
            doc_id_base=doc_id_base,
            batch_size=batch_size,
            corpus_repo=corpus_repo,
            indexer=indexer,
            vector_store=vector_store,
            bm25_store=bm25_store,
            user_id=user_id,
            expected_passage_count=expected_passage_count,
            on_progress=on_progress,
        )
