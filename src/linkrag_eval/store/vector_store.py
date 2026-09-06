"""eval 前缀 Qdrant 的写入器(``EvalVectorStore``)。

复用生产 ``QdrantIndexStore`` + point 模型(白名单 Qdrant 原语),
用 **eval 独立前缀** 实例化,绕开所有写 pipeline,自己构 ``IndexedPoint`` / ``SparseIndexedPoint``
直接 upsert。写读口径与生产一致——因为召回侧(recall_factory)复用同一 ``QdrantIndexStore``。

不经 ``ChunkRecordDB``:payload 只需 ``chunk_id/user_id/set_id/doc_id``,直接构点(见 point_factory._payload)。
dense 是 named ``dense`` 向量、sparse 是 named(名取自 ``EVAL_SPARSE_VECTOR_NAME``,默认
``sparse_text``)。BM25 使用 eval 自持 SQLite FTS5 sidecar。

护栏:前缀必须含 ``eval``,否则构造期拒跑——防写串生产 collection。
本文件是允许 import toLink-Rag 的四个 adapter 之一(Qdrant 原语)。rag import 全部惰性,
使包在无 rag 环境仍可导入;注入 ``index_store`` fake 即可单测编排,不连真 Qdrant。
"""

from __future__ import annotations

import asyncio
import logging
import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from linkrag_eval.compute.protocol import Bm25Tokens, SparseVec

_DENSE_VECTOR_NAME = "dense"
_PAYLOAD_INDEX_FIELDS = ("user_id", "set_id", "doc_id")
_LOOKUP_BATCH_SIZE = 256
_QDRANT_TIMEOUT_SECONDS = 60
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvalPoint:
    """一个待写入的 eval 点:确定性 chunk_id + dense(+ 可选 sparse)+ 归属 doc。"""

    chunk_id: str
    doc_id: int
    dense: list[float]
    sparse: SparseVec | None = None
    bm25_tokens: Bm25Tokens | None = None
    chunk_type: str = "text"


class EvalVectorStore:
    """把 eval 点写进 eval collection 的 named dense／sparse，BM25 写本地 FTS5。"""

    def __init__(
        self,
        *,
        prefix: str,
        bucket_count: int,
        user_id: int,
        qdrant_host: str | None = None,
        api_key: str | None = None,
        index_store: Any | None = None,
        sparse_vector_name: str | None = None,
        bm25_store: Any | None = None,
        bm25_mode: str = "stub",
        bm25_sqlite_path: str | None = None,
        bm25_sqlite_coarse_weight: float = 2.0,
        bm25_sqlite_fine_weight: float = 1.0,
    ) -> None:
        if "eval" not in prefix:
            raise RuntimeError(
                f"EvalVectorStore 前缀 {prefix!r} 不含 'eval';为防写串生产,拒绝构造。"
            )
        if bm25_mode not in {"stub", "sqlite_fts5"}:
            raise ValueError(f"不支持的 BM25 模式: {bm25_mode!r}")
        self._prefix = prefix
        self._user_id = user_id
        self._bucket_id = _route_bucket(bucket_count, user_id)
        self._collection_name = _collection_name(prefix, self._bucket_id)
        self._store = index_store or _build_index_store(self._collection_name, qdrant_host, api_key)
        self._sparse_name = sparse_vector_name or "sparse_text"
        self._bm25_store = bm25_store
        self._bm25_mode = bm25_mode
        self._bm25_sqlite_path = bm25_sqlite_path
        self._bm25_sqlite_coarse_weight = bm25_sqlite_coarse_weight
        self._bm25_sqlite_fine_weight = bm25_sqlite_fine_weight
        self._collection_ready = False
        self._sparse_ready = False
        self._bm25_ready = False
        self._prepared_vector_size: int | None = None
        self._prepared_dataset_id: int | None = None
        self._closed = False

    @property
    def bucket_id(self) -> int:
        return self._bucket_id

    @property
    def collection_name(self) -> str:
        return self._collection_name

    async def _collection_client(self):
        """复用 Qdrant 原语的 client，先核对实际写入目标与 named dense 契约。"""
        if self._closed:
            raise RuntimeError("EvalVectorStore 已关闭。")
        if self._store.collection_name != self._collection_name:
            raise RuntimeError("QdrantIndexStore collection 与 eval 目标不一致。")
        if self._store._dense_vector_name != _DENSE_VECTOR_NAME:
            raise RuntimeError("QdrantIndexStore dense 名与 eval 的 'dense' 契约不一致。")
        return await self._store._get_client()

    async def aclose(self) -> None:
        """幂等关闭实际持有的 Qdrant client；未创建 client 时不触发连接。"""
        if self._closed:
            return
        client = getattr(self._store, "_client", None)
        if client is not None:
            await client.close()
        self._closed = True

    async def prepare_collection(self, *, vector_size: int, dataset_id: int, on_disk: bool) -> None:
        """编码前显式创建或校验独立 hybrid collection，只补齐缺失的必要索引。

        新建时 dense/sparse/HNSW、payload 及三个整数索引均显式配置磁盘策略。
        先校验向量配置、已存在索引及 user/set 归属，再补索引，以便中断后续跑；
        不覆盖不匹配的已有 schema，也不改含其他归属点的 collection。
        默认小数据调用仍可直接 upsert，沿用原有惰性 ensure 路径。
        """
        if type(vector_size) is not int or vector_size <= 0:
            raise ValueError("vector_size 必须是正整数。")
        if type(on_disk) is not bool:
            raise ValueError("on_disk 必须是 bool。")
        if type(dataset_id) is not int:
            raise ValueError("dataset_id 必须是整数。")
        if self._sparse_name == _DENSE_VECTOR_NAME:
            raise ValueError("sparse vector 名不能与 dense 相同。")
        from qdrant_client import models

        client = await self._collection_client()
        if not await client.collection_exists(collection_name=self._collection_name):
            await client.create_collection(
                collection_name=self._collection_name,
                vectors_config={
                    _DENSE_VECTOR_NAME: models.VectorParams(
                        size=vector_size, distance=models.Distance.COSINE, on_disk=on_disk
                    )
                },
                sparse_vectors_config={
                    self._sparse_name: models.SparseVectorParams(
                        index=models.SparseIndexParams(on_disk=on_disk)
                    )
                },
                hnsw_config=models.HnswConfigDiff(on_disk=on_disk),
                on_disk_payload=on_disk,
            )
        info = await client.get_collection(collection_name=self._collection_name)
        missing_indexes = _validate_collection_schema(
            info,
            collection_name=self._collection_name,
            vector_size=vector_size,
            sparse_vector_name=self._sparse_name,
            on_disk=on_disk,
            allow_missing_indexes=True,
        )
        outside = await client.count(
            collection_name=self._collection_name,
            count_filter=models.Filter(
                must_not=[
                    models.Filter(
                        must=[
                            models.FieldCondition(
                                key="user_id", match=models.MatchValue(value=self._user_id)
                            ),
                            models.FieldCondition(
                                key="set_id", match=models.MatchValue(value=dataset_id)
                            ),
                        ]
                    )
                ]
            ),
            exact=True,
        )
        if outside.count != 0:
            raise RuntimeError(
                f"Qdrant collection {self._collection_name} 含不属于指定 user_id/dataset_id 的点。"
            )
        for field_name in missing_indexes:
            await client.create_payload_index(
                collection_name=self._collection_name,
                field_name=field_name,
                field_schema=models.IntegerIndexParams(type="integer", on_disk=on_disk),
                wait=True,
            )
        if missing_indexes:
            info = await client.get_collection(collection_name=self._collection_name)
            _validate_collection_schema(
                info,
                collection_name=self._collection_name,
                vector_size=vector_size,
                sparse_vector_name=self._sparse_name,
                on_disk=on_disk,
            )
        self._prepared_vector_size = vector_size
        self._prepared_dataset_id = dataset_id
        self._collection_ready = True
        self._sparse_ready = True

    async def verify_collection_count(self, *, dataset_id: int, expected_count: int) -> None:
        """验收已准备的专用 collection：总点数及同 user/set 点数均须精确相等。

        仅使用 exact count，不取点、向量或正文；两项任一不符都不能宣告入库完成。
        """
        if type(dataset_id) is not int:
            raise ValueError("dataset_id 必须是整数。")
        if type(expected_count) is not int or expected_count < 0:
            raise ValueError("expected_count 必须是非负整数。")
        if self._prepared_dataset_id != dataset_id or self._prepared_vector_size is None:
            raise RuntimeError("计数验收前必须为同一 dataset_id 成功 prepare_collection。")
        from qdrant_client import models

        client = await self._collection_client()
        total = await client.count(collection_name=self._collection_name, exact=True)
        scoped = await client.count(
            collection_name=self._collection_name,
            count_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="user_id", match=models.MatchValue(value=self._user_id)
                    ),
                    models.FieldCondition(key="set_id", match=models.MatchValue(value=dataset_id)),
                ]
            ),
            exact=True,
        )
        if total.count != expected_count or scoped.count != expected_count:
            raise RuntimeError(
                f"Qdrant collection {self._collection_name} 点数验收失败: "
                f"expected={expected_count}, total={total.count}, scoped={scoped.count}"
            )

    async def fetch_indexed_rows(
        self, *, dataset_id: int, chunk_ids: Sequence[str], expected_doc_ids: Mapping[str, int]
    ) -> dict[str, int]:
        """仅查询指定 IDs 中同时存在两路向量且归属一致的点，不返回向量数据。

        先按 ID retrieve 核对全部已有点的身份，包括尚缺一路向量的点；身份冲突
        在补写前报错。expected_doc_ids 必须与去重后的 chunk_ids 等集。
        has_vector 在服务端检查向量存在性；不支持该条件或读取失败时直接报错，
        不能把远端未核实当作可跳过。每次 retrieve/scroll 均限定最多 256 个 IDs。
        """
        ids = list(dict.fromkeys(chunk_ids))
        if type(dataset_id) is not int or any(not isinstance(cid, str) or not cid for cid in ids):
            raise ValueError("dataset_id 必须是整数，chunk_ids 必须是非空字符串。")
        if set(expected_doc_ids) != set(ids) or any(
            type(doc_id) is not int for doc_id in expected_doc_ids.values()
        ):
            raise ValueError("expected_doc_ids 必须与 chunk_ids 等集且值为整数。")
        if not ids:
            return {}
        from qdrant_client import models

        client = await self._collection_client()
        found: dict[str, int] = {}

        def checked_identity(record: Any, requested: set[str]) -> str:
            cid = str(record.id)
            payload = record.payload
            if (
                cid not in requested
                or not isinstance(payload, Mapping)
                or payload.get("chunk_id") != cid
                or type(payload.get("user_id")) is not int
                or payload["user_id"] != self._user_id
                or type(payload.get("set_id")) is not int
                or payload["set_id"] != dataset_id
                or type(payload.get("doc_id")) is not int
                or payload["doc_id"] != expected_doc_ids[cid]
            ):
                raise ValueError(f"Qdrant point {cid} 的 user/set/chunk/doc 身份与预期不一致。")
            return cid

        for start in range(0, len(ids), _LOOKUP_BATCH_SIZE):
            batch = ids[start : start + _LOOKUP_BATCH_SIZE]
            requested = set(batch)
            records = await client.retrieve(
                collection_name=self._collection_name,
                ids=batch,
                with_payload=["chunk_id", "user_id", "set_id", "doc_id"],
                with_vectors=False,
            )
            existing = {checked_identity(record, requested) for record in records}
            batch = [cid for cid in batch if cid in existing]
            if not batch:
                continue
            scroll_filter = models.Filter(
                must=[
                    models.HasIdCondition(has_id=batch),
                    models.HasVectorCondition(has_vector=_DENSE_VECTOR_NAME),
                    models.HasVectorCondition(has_vector=self._sparse_name),
                    models.FieldCondition(
                        key="user_id", match=models.MatchValue(value=self._user_id)
                    ),
                    models.FieldCondition(key="set_id", match=models.MatchValue(value=dataset_id)),
                ]
            )
            offset = None
            seen_offsets = set()
            for _ in range(len(batch) + 1):
                records, next_offset = await client.scroll(
                    collection_name=self._collection_name,
                    scroll_filter=scroll_filter,
                    limit=len(batch),
                    offset=offset,
                    with_payload=["chunk_id", "user_id", "set_id", "doc_id"],
                    with_vectors=False,
                )
                for record in records:
                    cid = checked_identity(record, existing)
                    found[cid] = expected_doc_ids[cid]
                if next_offset is None:
                    break
                if next_offset in seen_offsets:
                    raise RuntimeError("Qdrant 候选核对分页没有推进。")
                seen_offsets.add(next_offset)
                offset = next_offset
            else:
                raise RuntimeError("Qdrant 候选核对超出指定 IDs 的有界分页范围。")
        return found

    async def upsert(self, *, dataset_id: int, points: Sequence[EvalPoint]) -> None:
        """写一批点:ensure collection → upsert dense → (有 sparse 则)ensure schema + upsert sparse。

        幂等:point id = 确定性 chunk_id,重灌覆盖。dense/sparse 共用同一 point(sparse 走
        ``update_vectors`` 追加,不覆盖 dense)。
        """
        pts = list(points)
        if not pts:
            return
        if self._closed:
            raise RuntimeError("EvalVectorStore 已关闭。")
        if self._prepared_dataset_id is not None and dataset_id != self._prepared_dataset_id:
            raise ValueError("dataset_id 与显式准备的独立 collection 不一致。")
        if self._prepared_vector_size is not None and any(
            len(point.dense) != self._prepared_vector_size for point in pts
        ):
            raise ValueError("dense 向量维度与显式准备的 collection 不一致。")
        bm25_points = self._bm25_points(dataset_id, pts)
        vector_size = len(pts[0].dense)
        if vector_size <= 0:
            raise ValueError("dense 向量维度为 0,无法建 collection。")

        if not self._collection_ready:
            await self._store.ensure_collection(vector_size=vector_size)
            self._collection_ready = True
        await self._upsert_vectors([self._dense_point(p, dataset_id) for p in pts])

        sparse_pts = [p for p in pts if p.sparse is not None]
        if sparse_pts:
            if not self._sparse_ready:
                await self._store.ensure_sparse_vector_schema(vector_name=self._sparse_name)
                self._sparse_ready = True
            await self._upsert_vectors(
                [self._sparse_point(p, dataset_id) for p in sparse_pts], sparse=True,
            )

        if bm25_points:
            bm25_store = self._ensure_bm25_store()
            if not self._bm25_ready:
                await bm25_store.ensure_collection()
                self._bm25_ready = True
            await bm25_store.upsert_chunks(bm25_points)

    async def _upsert_vectors(self, points: list[Any], *, sparse: bool = False) -> None:
        """仅补原语漏识别的 SDK 网络包装异常；复用本路已构造向量，最多三次。"""
        write = self._store.upsert_sparse_vectors if sparse else self._store.upsert_points
        for attempt in range(3):
            try:
                await write(points=points)
                return
            except Exception as exc:
                source_type = self._unhandled_transport_error(exc)
                if attempt == 2 or source_type is None:
                    raise
                _LOGGER.warning(
                    "Qdrant %s write retry %s/3 (%s)",
                    "sparse" if sparse else "dense", attempt + 2, source_type,
                )
                await asyncio.sleep(2 ** attempt)

    def _unhandled_transport_error(self, error: Exception) -> str | None:
        """不重复叠加原语已有重试，也不按错误正文猜测类型。"""
        import httpx
        from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

        current: BaseException | None = error
        seen: set[int] = set()
        for _ in range(6):
            if current is None or id(current) in seen:
                break
            seen.add(id(current))
            if isinstance(current, (UnexpectedResponse, httpx.HTTPStatusError)):
                return None
            if isinstance(current, ResponseHandlingException):
                # 原语已识别的异常已用完其有限重试，不再从外层重新计次。
                recognized = getattr(self._store, "_is_transient_error", None)
                if recognized is not None and recognized(current):
                    return None
                if isinstance(
                    current.source,
                    (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError),
                ):
                    return type(current.source).__name__
                return None
            current = current.__cause__
        return None

    async def delete(self, *, chunk_ids: Sequence[str]) -> None:
        """按 chunk_id 删点(定向清理;幂等重灌通常无需调用)。"""
        ids = list(chunk_ids)
        if ids:
            if self._closed:
                raise RuntimeError("EvalVectorStore 已关闭。")
            await self._store.delete_points(chunk_ids=ids)

    # —— 构点(惰性 import rag 原语)——
    def _payload(self, p: EvalPoint, dataset_id: int) -> dict[str, int | str]:
        return {
            "chunk_id": p.chunk_id,
            "user_id": self._user_id,
            "set_id": dataset_id,
            "doc_id": p.doc_id,
        }

    def _dense_point(self, p: EvalPoint, dataset_id: int):
        from src.core.storage.qdrant.models import IndexedPoint

        return IndexedPoint(
            chunk_id=p.chunk_id,
            vector=[float(x) for x in p.dense],
            payload=self._payload(p, dataset_id),
        )

    def _sparse_point(self, p: EvalPoint, dataset_id: int):
        from src.core.encoding.sparse.models import SparseVector
        from src.core.storage.qdrant.models import SparseIndexedPoint

        assert p.sparse is not None
        return SparseIndexedPoint(
            chunk_id=p.chunk_id,
            vector_name=self._sparse_name,
            sparse_vector=SparseVector(
                indices=list(p.sparse.indices), values=list(p.sparse.values)
            ),
            payload=self._payload(p, dataset_id),
        )

    def _bm25_points(self, dataset_id: int, points: Sequence[EvalPoint]) -> list[Any]:
        bm25_items = [p for p in points if p.bm25_tokens is not None]
        if not bm25_items:
            return []
        if self._bm25_mode == "sqlite_fts5":
            from linkrag_eval.store.sqlite_bm25 import SQLiteBm25Point

            return [
                SQLiteBm25Point(
                    chunk_id=p.chunk_id,
                    doc_id=p.doc_id,
                    user_id=self._user_id,
                    dataset_id=dataset_id,
                    chunk_type=p.chunk_type,
                    tokens=p.bm25_tokens,
                )
                for p in bm25_items
                if p.bm25_tokens is not None
            ]
        raise ValueError("写入 BM25 tokens 需要启用 sqlite_fts5。")

    def _ensure_bm25_store(self):
        if self._bm25_mode == "sqlite_fts5":
            if self._bm25_sqlite_path is None and self._bm25_store is None:
                raise RuntimeError("启用 sqlite_fts5 写入需配置 EVAL_BM25_SQLITE_PATH。")
            if self._bm25_store is None:
                self._bm25_store = _build_sqlite_bm25_store(
                    path=self._bm25_sqlite_path,
                    coarse_weight=self._bm25_sqlite_coarse_weight,
                    fine_weight=self._bm25_sqlite_fine_weight,
                )
            return self._bm25_store
        raise ValueError("BM25 存储仅在 sqlite_fts5 模式下启用。")


def _matches_disk(config: Any, on_disk: bool, *, field: str = "on_disk") -> bool:
    """当前 SDK 的 memory 字段优先于 on_disk；不能忽略会覆盖磁盘策略的配置。"""
    memory = getattr(config, "memory", None)
    if memory is not None:
        return memory == "cold" if on_disk else memory in {"cached", "pinned"}
    return getattr(config, field, None) is on_disk


def _validate_collection_schema(
    info: Any,
    *,
    collection_name: str,
    vector_size: int,
    sparse_vector_name: str,
    on_disk: bool,
    allow_missing_indexes: bool = False,
) -> list[str]:
    from qdrant_client import models

    mismatches = []
    missing_indexes = []
    try:
        config = info.config
        params = config.params
        vectors = params.vectors
        sparse_vectors = params.sparse_vectors
        if not isinstance(vectors, Mapping) or set(vectors) != {_DENSE_VECTOR_NAME}:
            mismatches.append("named dense vectors")
        else:
            dense = vectors[_DENSE_VECTOR_NAME]
            if dense.size != vector_size:
                mismatches.append("dense.size")
            if dense.distance != models.Distance.COSINE:
                mismatches.append("dense.distance")
            if not _matches_disk(dense, on_disk):
                mismatches.append("dense.on_disk")
            hnsw = getattr(dense, "hnsw_config", None)
            if hnsw is None or (
                getattr(hnsw, "on_disk", None) is None and getattr(hnsw, "memory", None) is None
            ):
                hnsw = config.hnsw_config
            if not _matches_disk(hnsw, on_disk):
                mismatches.append("hnsw.on_disk")
            if getattr(dense, "multivector_config", None) is not None:
                mismatches.append("dense.multivector_config")
            if getattr(dense, "quantization_config", None) is not None:
                mismatches.append("dense.quantization_config")
            if getattr(dense, "datatype", None) not in {None, "float32"}:
                mismatches.append("dense.datatype")
        if not isinstance(sparse_vectors, Mapping) or set(sparse_vectors) != {sparse_vector_name}:
            mismatches.append("named sparse vectors")
        else:
            sparse = sparse_vectors[sparse_vector_name]
            if not _matches_disk(sparse.index, on_disk):
                mismatches.append("sparse.index.on_disk")
            if sparse.modifier is not None:
                mismatches.append("sparse.modifier")
            if getattr(sparse.index, "datatype", None) not in {None, "float32"}:
                mismatches.append("sparse.index.datatype")
        payload = getattr(params, "payload", None)
        if payload is not None and getattr(payload, "memory", None) is not None:
            payload_matches = _matches_disk(payload, on_disk)
        else:
            payload_matches = _matches_disk(params, on_disk, field="on_disk_payload")
        if not payload_matches:
            mismatches.append("on_disk_payload")
        if getattr(config, "quantization_config", None) is not None:
            mismatches.append("quantization_config")
        for field_name in _PAYLOAD_INDEX_FIELDS:
            index = info.payload_schema.get(field_name)
            if index is None and allow_missing_indexes:
                missing_indexes.append(field_name)
            elif index is None or index.data_type != models.PayloadSchemaType.INTEGER:
                mismatches.append(f"payload_schema.{field_name}.integer")
            elif not _matches_disk(index.params, on_disk):
                mismatches.append(f"payload_schema.{field_name}.on_disk")
            elif getattr(index.params, "lookup", None) is False:
                mismatches.append(f"payload_schema.{field_name}.lookup")
    except (AttributeError, TypeError, KeyError) as exc:
        raise RuntimeError(f"Qdrant collection {collection_name} schema 响应不完整。") from exc
    if mismatches:
        raise RuntimeError(
            f"Qdrant collection {collection_name} 与显式 schema 不一致: {', '.join(mismatches)}"
        )
    return missing_indexes


# —— 默认装配:此处(允许的 adapter 文件)惰性触碰 rag / qdrant-client ——
def _route_bucket(bucket_count: int, user_id: int) -> int:
    """按 eval 的固定 routing 常量计算 bucket，供当前写入与召回共用。

    两端必须使用相同规则，才能访问同一 collection。这里只计算存储位置，
    不依赖生产 BucketRouter，也不读取用户配置。
    """

    if bucket_count <= 0:
        raise ValueError("bucket_count 必须为正整数。")
    return zlib.crc32(str(user_id).encode("utf-8")) % bucket_count


def _collection_name(prefix: str, bucket_id: int) -> str:
    return f"{prefix}_{bucket_id}"


def resolve_eval_qdrant_collection(*, prefix: str, bucket_count: int, user_id: int) -> str:
    """返回当前 eval 路由常量对应的显式 Qdrant collection 名。"""

    if "eval" not in prefix:
        raise RuntimeError(f"Qdrant eval 前缀 {prefix!r} 不含 'eval';拒绝解析。")
    return _collection_name(prefix, _route_bucket(bucket_count, user_id))


def _build_index_store(collection_name: str, qdrant_host: str | None, api_key: str | None):
    from qdrant_client import AsyncQdrantClient
    from src.core.storage.qdrant import QdrantIndexStore

    # 注入 client 时生产原语的 timeout 不会传入 SDK；两者须显式保持一致。
    client = AsyncQdrantClient(
        url=qdrant_host,
        api_key=(api_key or None),
        trust_env=False,
        timeout=_QDRANT_TIMEOUT_SECONDS,
    )
    return QdrantIndexStore(
        client=client,
        collection_name=collection_name,
        timeout=_QDRANT_TIMEOUT_SECONDS,
    )


def _build_sqlite_bm25_store(*, path: str | None, coarse_weight: float, fine_weight: float):
    from linkrag_eval.store.sqlite_bm25 import SQLiteBm25Store

    if not path:
        raise RuntimeError("EVAL_BM25_SQLITE_PATH 未配置。")
    return SQLiteBm25Store(
        path,
        coarse_weight=coarse_weight,
        fine_weight=fine_weight,
    )


def build_eval_vector_store(settings=None) -> EvalVectorStore:
    """按 EVAL_* 配置装配 EvalVectorStore。"""
    if settings is None:
        from linkrag_eval.config import get_settings

        settings = get_settings()
    return EvalVectorStore(
        prefix=settings.qdrant_prefix,
        bucket_count=settings.qdrant_bucket_count,
        user_id=settings.user_id,
        qdrant_host=settings.qdrant_host,
        sparse_vector_name=settings.sparse_vector_name,
        bm25_mode=settings.bm25_mode,
        bm25_sqlite_path=settings.bm25_sqlite_path,
        bm25_sqlite_coarse_weight=settings.bm25_sqlite_coarse_weight,
        bm25_sqlite_fine_weight=settings.bm25_sqlite_fine_weight,
    )
