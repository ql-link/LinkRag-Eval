"""原始 T2 入库编排：独立存储、明确配置、可核对的逐批续接。"""

from __future__ import annotations

import asyncio
import fcntl
import json
from contextlib import AsyncExitStack, contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from linkrag_eval.runners.t2_ingest import T2IngestError, ingest_t2_collection


def _endpoint(value: str) -> str:
    """配置记录剥离 URL 凭证、查询参数和片段。"""
    parsed = urlsplit(value if "://" in value else "http://" + value)
    if not parsed.hostname:
        raise ValueError("服务 URL 缺少有效主机")
    hostname = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    netloc = hostname if parsed.port is None else f"{hostname}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path.rstrip("/"), "", ""))


def encoder_semantics(settings: Any) -> dict[str, Any]:
    """只记录影响当前编码结果的配置，不记录密钥或吞吐参数。"""
    from linkrag_eval.llm.sparse_client import ArkSparseEncoder

    dense_endpoint = settings.embed_base_url.rstrip("/")
    if not dense_endpoint:
        raise ValueError("EVAL_EMBED_BASE_URL 未配置")
    if not dense_endpoint.endswith("/embeddings"):
        dense_endpoint += "/embeddings"
    return {
        "dense": {
            "endpoint": _endpoint(dense_endpoint),
            "model": settings.embed_model,
            "dim": settings.embed_dim,
            "input_length_policy": settings.embed_input_length_policy,
        },
        "sparse": {
            "endpoint": _endpoint(settings.sparse_base_url or ArkSparseEncoder.DEFAULT_ENDPOINT),
            "provider": settings.sparse_provider,
            "model": settings.sparse_model,
            "top_k": settings.sparse_top_k,
            "min_weight": settings.sparse_min_weight,
            "input_length_policy": settings.sparse_input_length_policy,
        },
        "bm25": {
            "mode": settings.bm25_mode,
            "schema": 2,
            "coarse_weight": settings.bm25_sqlite_coarse_weight,
            "fine_weight": settings.bm25_sqlite_fine_weight,
            "input_text": "full_original_passage",
        },
        "input_length_contract": {
            "version": 1,
            "unit": "unicode_code_points_sent",
            "prefix_on_length_error": "halve_current_prefix_only_after_explicit_length_rejection",
            "stored_text": "full_original_passage",
        },
    }


def _bound_settings(settings: Any, out_dir: Path, qdrant_prefix: str) -> Any:
    if "eval" not in qdrant_prefix:
        raise ValueError("独立 Qdrant 前缀必须包含 eval")
    if settings.bm25_mode != "sqlite_fts5":
        raise ValueError("完整三路入库要求 EVAL_BM25_MODE=sqlite_fts5")
    return settings.model_copy(update={
        "db_url": f"sqlite+aiosqlite:///{out_dir / 'corpus.sqlite3'}",
        "bm25_sqlite_path": str(out_dir / "bm25.sqlite3"),
        "qdrant_prefix": qdrant_prefix,
    })


def _identity(
    *, collection_path: Path, dataset_id: int, doc_id_base: int,
    expected_passages: int, settings: Any,
) -> dict[str, Any]:
    from linkrag_eval.store.vector_store import resolve_eval_qdrant_collection

    if min(dataset_id, doc_id_base, expected_passages) <= 0:
        raise ValueError("dataset_id、doc_id_base、expected_passages 须为正整数")
    if doc_id_base + expected_passages - 1 > 2**63 - 1:
        raise ValueError("doc_id 范围超出 SQLite 有符号整数范围")
    if not collection_path.is_file():
        raise ValueError("原始 collection 文件不存在")
    return {
        "format": "t2-corpus-run-v1",
        "source": {
            "collection_path": str(collection_path),
            "dataset_id": dataset_id,
            "doc_id_base": doc_id_base,
            "expected_passages": expected_passages,
        },
        "encoders": encoder_semantics(settings),
        "storage": {
            "database_url": settings.database_url(),
            "bm25_sqlite_path": settings.bm25_sqlite_path,
            "qdrant_endpoint": _endpoint(settings.qdrant_host),
            "qdrant_prefix": settings.qdrant_prefix,
            "qdrant_bucket_count": settings.qdrant_bucket_count,
            "qdrant_collection": resolve_eval_qdrant_collection(
                prefix=settings.qdrant_prefix, bucket_count=settings.qdrant_bucket_count,
                user_id=settings.user_id,
            ),
            "sparse_vector_name": settings.sparse_vector_name,
            "user_id": settings.user_id,
            "on_disk": True,
        },
    }


def _write_json_atomic(path: Path, value: Any) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    temporary.replace(path)


@contextmanager
def _run_lock(out_dir: Path):
    with (out_dir / ".ingest.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("该语料目录已有入库操作运行") from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def migrate_corpus_database(database_url: str) -> None:
    """通过唯一 Alembic 迁移链建库；显式 URL 不受全局环境覆盖。"""
    from alembic.config import Config

    from alembic import command

    repository = Path(__file__).resolve().parents[3]
    config = Config()
    config.set_main_option("script_location", str(repository / "alembic"))
    config.attributes["database_url"] = database_url
    command.upgrade(config, "head")


async def _run_ingestion(
    *, settings: Any, collection_path: Path, dataset_id: int, doc_id_base: int,
    batch_size: int, expected_passages: int, on_progress: Any,
) -> dict[str, Any]:
    from linkrag_eval.compute.rag_adapter import RagProductComputer
    from linkrag_eval.llm.dense_client import build_dense_embedder
    from linkrag_eval.llm.sparse_client import build_sparse_encoder
    from linkrag_eval.store.corpus_repo import EvalCorpusRepo
    from linkrag_eval.store.indexer import EvalVectorIndexer
    from linkrag_eval.store.sqlite_bm25 import SQLiteBm25Store
    from linkrag_eval.store.vector_store import EvalVectorStore

    async with AsyncExitStack() as resources:
        dense = build_dense_embedder(settings)
        resources.push_async_callback(dense.aclose)
        sparse = build_sparse_encoder(settings)
        resources.push_async_callback(sparse.aclose)
        computer = RagProductComputer(dense_encoder=dense, sparse_encoder=sparse)
        migrate_corpus_database(settings.database_url())
        repo = EvalCorpusRepo(url=settings.database_url())
        bm25 = SQLiteBm25Store(
            settings.bm25_sqlite_path,
            coarse_weight=settings.bm25_sqlite_coarse_weight,
            fine_weight=settings.bm25_sqlite_fine_weight,
        )
        vectors = EvalVectorStore(
            prefix=settings.qdrant_prefix, bucket_count=settings.qdrant_bucket_count,
            user_id=settings.user_id, qdrant_host=settings.qdrant_host,
            sparse_vector_name=settings.sparse_vector_name,
            bm25_store=bm25, bm25_mode=settings.bm25_mode,
        )
        resources.push_async_callback(vectors.aclose)
        await vectors.prepare_collection(
            vector_size=computer.dense_dim, dataset_id=dataset_id, on_disk=True,
        )
        await bm25.ensure_collection()
        await repo.register_dataset(
            dataset_id, name="T2Ranking original collection", source_type="opensource",
            relevance_type="graded", ingestion_ref=str(collection_path),
            note="原始 passage 一段一 chunk；未读取 qrels。",
        )
        indexer = EvalVectorIndexer(
            computer=computer, vector_store=vectors, corpus_repo=repo,
            with_sparse=True, bm25_mode=settings.bm25_mode,
        )
        try:
            result = await ingest_t2_collection(
                collection_path=collection_path, dataset_id=dataset_id, doc_id_base=doc_id_base,
                batch_size=batch_size, corpus_repo=repo, indexer=indexer,
                vector_store=vectors, bm25_store=bm25, user_id=settings.user_id,
                expected_passage_count=expected_passages, on_progress=on_progress,
            )
        except BaseException:
            # 只在收尾聚合当前存储行，避免逐批扫全库或累计重复续接条次。
            try:
                summary = await repo.summarize_encoding_inputs(dataset_id=dataset_id)
            except Exception as exc:  # noqa: BLE001 — 保留主失败，汇总不可用不能假装为零。
                summary = {"status": "unavailable", "error_type": type(exc).__name__}
            on_progress({"encoding_inputs": summary})
            raise
        try:
            summary = await repo.summarize_encoding_inputs(dataset_id=dataset_id)
        except Exception as exc:  # 聚合失败保留未知状态与原异常，不再扫描。
            on_progress({"encoding_inputs": {
                "status": "unavailable", "error_type": type(exc).__name__,
            }})
            raise
        # 先保存已观察的汇总，后续资源关闭或完成判定失败也不能丢失它。
        on_progress({"encoding_inputs": summary})
        return {**result, "encoding_inputs": summary}


def _validate_complete(progress: dict[str, Any], expected_passages: int) -> None:
    fields = ("processed_passages", "indexed_passages", "skipped_passages", "completed_batches")
    if any(type(progress.get(key)) is not int or progress[key] < 0 for key in fields):
        raise ValueError("入库完成记录缺少有效计数")
    if (
        progress["processed_passages"] != expected_passages
        or progress["indexed_passages"] + progress["skipped_passages"] != expected_passages
        or progress["completed_batches"] == 0
    ):
        raise ValueError("入库尚未核对全部声明的原始语料")
    summary = progress.get("encoding_inputs", {})
    if (
        summary.get("total_rows") != expected_passages
        or summary.get("completed_rows") != expected_passages
        or summary.get("incomplete_rows") != 0
        or summary.get("affected_status_unknown") != 0
        or any(summary.get(route, {}).get("unknown") != 0 for route in ("dense", "sparse"))
    ):
        raise ValueError("入库尚未记录完整语料两路实际编码输入长度")


async def ingest_t2_corpus(
    *, collection_path: Path, dataset_id: int, doc_id_base: int,
    expected_passages: int, qdrant_prefix: str, out_dir: Path,
    settings: Any, batch_size: int = 25,
) -> dict[str, Any]:
    """完整读流及实际索引核对后才记录 completed；续接不使用进度跳行。"""
    if batch_size <= 0:
        raise ValueError("batch_size 须为正整数")
    out_dir = Path(out_dir).resolve()
    collection_path = Path(collection_path).resolve()
    settings = _bound_settings(settings, out_dir, qdrant_prefix)
    identity = _identity(
        collection_path=collection_path, dataset_id=dataset_id, doc_id_base=doc_id_base,
        expected_passages=expected_passages, settings=settings,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    with _run_lock(out_dir):
        metadata_path = out_dir / "ingest.json"
        if metadata_path.exists():
            existing = json.loads(metadata_path.read_text(encoding="utf-8"))
            if {key: existing.get(key) for key in identity} != identity:
                raise ValueError("已有语料运行的来源、编码器或存储配置不匹配，拒绝续接")
        else:
            if any(path.name != ".ingest.lock" for path in out_dir.iterdir()):
                raise ValueError("已有目录缺少 ingest.json，拒绝接管其中的数据")
            _write_json_atomic(metadata_path, identity)
        from linkrag_eval.app import _git_state

        revision, dirty = _git_state()
        execution = {
            "code_revision": revision, "worktree_dirty": dirty, "batch_size": batch_size,
        }
        progress_path = out_dir / "progress.json"
        latest = {
            "processed_passages": 0, "indexed_passages": 0,
            "skipped_passages": 0, "completed_batches": 0,
        }

        def save_progress(progress: dict[str, Any]) -> None:
            latest.update(progress)
            _write_json_atomic(progress_path, {**execution, "status": "running", **latest})

        save_progress(latest)
        try:
            result = await _run_ingestion(
                settings=settings, collection_path=collection_path, dataset_id=dataset_id,
                doc_id_base=doc_id_base, batch_size=batch_size,
                expected_passages=expected_passages, on_progress=save_progress,
            )
            _validate_complete(result, expected_passages)
            output = {"status": "completed", **result}
        except (asyncio.CancelledError, KeyboardInterrupt) as exc:
            _write_json_atomic(progress_path, {
                **execution, "status": "interrupted", **latest,
                "error_type": type(exc).__name__,
            })
            raise
        except T2IngestError as exc:
            output = {
                "status": "failed", "phase": exc.phase, **latest, **exc.progress,
                "failed_batch": exc.failed_batch, "error_type": exc.error_type,
                "cause_chain": exc.cause_chain,
            }
        except Exception as exc:  # noqa: BLE001 — 只记录安全类型，不泄露服务错误正文
            output = {
                "status": "failed", "phase": "setup_or_completion", **latest,
                "error_type": type(exc).__name__,
            }
        output = {**execution, **output}
        _write_json_atomic(progress_path, output)
        return output


def bind_completed_t2_corpus(corpus_run: Path, settings: Any) -> tuple[Any, Path, int]:
    """把采集器绑定到成功完整入库的当前格式；不替换当前模型配置。"""
    directory = Path(corpus_run).resolve()
    metadata = json.loads((directory / "ingest.json").read_text(encoding="utf-8"))
    progress = json.loads((directory / "progress.json").read_text(encoding="utf-8"))
    if metadata.get("format") != "t2-corpus-run-v1":
        raise ValueError("不支持的语料运行格式")
    source = metadata["source"]
    _validate_complete(progress, source["expected_passages"])
    if progress.get("status") != "completed":
        raise ValueError("语料尚未完成完整入库")
    settings = _bound_settings(settings, directory, metadata["storage"]["qdrant_prefix"])
    collection_path = Path(source["collection_path"])
    expected = _identity(
        collection_path=collection_path, dataset_id=source["dataset_id"],
        doc_id_base=source["doc_id_base"], expected_passages=source["expected_passages"],
        settings=settings,
    )
    if {key: metadata.get(key) for key in expected} != expected:
        raise ValueError("当前编码器或存储配置与已入库语料不匹配")
    if not all((directory / name).is_file() for name in ("corpus.sqlite3", "bm25.sqlite3")):
        raise ValueError("已入库语料的本地存储文件缺失")
    return settings, collection_path, source["dataset_id"]
