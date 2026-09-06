"""SQLite FTS5 BM25 后端。

FTS5 是进程内嵌入式全文索引，写入与查询使用同一套 eval 本地分词。
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from linkrag_eval.compute.protocol import Bm25Tokens


@dataclass(frozen=True)
class SQLiteBm25Point:
    chunk_id: str
    doc_id: int
    user_id: int
    dataset_id: int
    chunk_type: str
    tokens: Bm25Tokens


@dataclass(frozen=True)
class SQLiteBm25Hit:
    chunk_id: str
    doc_id: int
    score: float


class SQLiteBm25Store:
    """SQLite FTS5 存储与检索。

    FTS5 的 ``bm25()`` 分数越小越好,这里统一取负数作为正向 score,与召回融合
    约定的"越大越好"一致。
    """

    def __init__(self, path: str | Path, *, coarse_weight: float = 2.0, fine_weight: float = 1.0):
        self.path = Path(path)
        self.coarse_weight = float(coarse_weight)
        self.fine_weight = float(fine_weight)

    async def ensure_collection(self) -> None:
        await asyncio.to_thread(self._ensure_schema_sync)

    async def upsert_chunks(self, points: Sequence[SQLiteBm25Point]) -> None:
        pts = list(points)
        if not pts:
            return
        await asyncio.to_thread(self._upsert_sync, pts)

    async def recall_topk_chunks(self, request) -> list[SQLiteBm25Hit]:
        tokens = list(getattr(request, "tokens", []) or [])
        dataset_id = int(request.dataset_id)
        doc_id = getattr(request, "doc_id", None)
        top_k = int(request.top_k)
        if not tokens or top_k <= 0:
            return []
        return await asyncio.to_thread(
            self._search_sync,
            tokens,
            dataset_id,
            int(doc_id) if doc_id is not None else None,
            top_k,
        )

    async def fetch_indexed_rows(
        self, *, dataset_id: int, chunk_ids: Sequence[str], user_id: int
    ) -> dict[str, int]:
        """只读核对本批已索引 ID；调用前由写入初始化负责确保 schema 2。"""
        ids = list(dict.fromkeys(chunk_ids))
        if not ids:
            return {}
        return await asyncio.to_thread(
            self._fetch_indexed_rows_sync, int(dataset_id), ids, int(user_id)
        )

    async def verify_dataset_count(
        self, *, dataset_id: int, user_id: int, expected_count: int
    ) -> None:
        """入库末尾只读核对独立库的实际范围与映射；不用于逐批续接。"""
        if type(expected_count) is not int or expected_count < 0:
            raise ValueError("expected_count 必须是非负整数")
        await asyncio.to_thread(
            self._verify_dataset_count_sync, int(dataset_id), int(user_id), expected_count
        )

    async def identity(self) -> dict[str, object]:
        """返回 sidecar 的路径、schema、数量和权重，不扫描正文计算指纹。"""
        return await asyncio.to_thread(
            inspect_sqlite_bm25_identity,
            self.path,
            coarse_weight=self.coarse_weight,
            fine_weight=self.fine_weight,
        )

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.path)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA temp_store=MEMORY")
        return con

    def _ensure_schema_sync(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS bm25_fts USING fts5(
                    chunk_id UNINDEXED,
                    doc_id UNINDEXED,
                    user_id UNINDEXED,
                    dataset_id UNINDEXED,
                    chunk_type UNINDEXED,
                    coarse,
                    fine,
                    tokenize='unicode61'
                )
                """
            )
            con.execute("CREATE TABLE IF NOT EXISTS bm25_meta(version INTEGER NOT NULL)")
            version_row = con.execute(
                "SELECT version FROM bm25_meta ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            if version_row == (2,):
                return

            # 升级只扫描一次已有 ID，不重建 FTS。锁内重查版本，避免并发重复回填。
            con.execute("BEGIN IMMEDIATE")
            version_row = con.execute(
                "SELECT version FROM bm25_meta ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            if version_row == (2,):
                return
            if version_row is not None and version_row != (1,):
                raise ValueError(f"不支持的 BM25 schema version: {version_row[0]}")
            con.execute(
                """
                CREATE TABLE bm25_chunk_rows(
                    fts_rowid INTEGER PRIMARY KEY,
                    chunk_id TEXT NOT NULL
                )
                """
            )
            con.execute("CREATE INDEX bm25_chunk_rows_chunk_id ON bm25_chunk_rows(chunk_id)")
            con.execute(
                "INSERT INTO bm25_chunk_rows(fts_rowid, chunk_id) SELECT rowid, chunk_id FROM bm25_fts"
            )
            if version_row is None:
                con.execute("INSERT INTO bm25_meta(version) VALUES (2)")
            else:
                con.execute("UPDATE bm25_meta SET version = 2")

    def _upsert_sync(self, points: list[SQLiteBm25Point]) -> None:
        self._ensure_schema_sync()
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            for p in points:
                # chunk_id 在 FTS 中是 UNINDEXED；先走普通索引定位，再按 rowid 删除。
                rowids = con.execute(
                    "SELECT fts_rowid FROM bm25_chunk_rows WHERE chunk_id = ?", (p.chunk_id,)
                ).fetchall()
                con.executemany("DELETE FROM bm25_fts WHERE rowid = ?", rowids)
                con.executemany("DELETE FROM bm25_chunk_rows WHERE fts_rowid = ?", rowids)
                cursor = con.execute(
                    """
                    INSERT INTO bm25_fts(
                        chunk_id, doc_id, user_id, dataset_id, chunk_type, coarse, fine
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        p.chunk_id,
                        int(p.doc_id),
                        int(p.user_id),
                        int(p.dataset_id),
                        p.chunk_type,
                        p.tokens.coarse,
                        p.tokens.fine,
                    ),
                )
                con.execute(
                    "INSERT INTO bm25_chunk_rows(fts_rowid, chunk_id) VALUES (?, ?)",
                    (cursor.lastrowid, p.chunk_id),
                )

    def _fetch_indexed_rows_sync(
        self, dataset_id: int, chunk_ids: list[str], user_id: int
    ) -> dict[str, int]:
        resolved = self.path.resolve()
        if not resolved.is_file():
            return {}
        con = sqlite3.connect(resolved.as_uri() + "?mode=ro", uri=True)
        try:
            tables = {
                row[0]
                for row in con.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name IN ('bm25_meta', 'bm25_chunk_rows')"
                )
            }
            if tables != {"bm25_meta", "bm25_chunk_rows"}:
                raise ValueError("BM25 sidecar 尚未初始化至 schema 2；请先调用 ensure_collection")
            version_row = con.execute(
                "SELECT version FROM bm25_meta ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            if version_row != (2,):
                raise ValueError("BM25 sidecar 需要 schema 2；请先调用 ensure_collection")
            indexed: dict[str, int] = {}
            for offset in range(0, len(chunk_ids), 256):
                batch = chunk_ids[offset : offset + 256]
                placeholders = ",".join("?" for _ in batch)
                # CROSS JOIN 保持 ID 索引在外层，FTS 每次只按已定位的 rowid 读取。
                rows = con.execute(
                    f"""
                    SELECT m.chunk_id, f.doc_id
                    FROM bm25_chunk_rows AS m
                    CROSS JOIN bm25_fts AS f
                    WHERE m.chunk_id IN ({placeholders})
                      AND f.rowid = m.fts_rowid
                      AND f.chunk_id = m.chunk_id
                      AND f.dataset_id = ?
                      AND f.user_id = ?
                    """,
                    [*batch, dataset_id, user_id],
                )
                for chunk_id, doc_id in rows:
                    doc_id = int(doc_id)
                    if chunk_id in indexed and indexed[chunk_id] != doc_id:
                        raise ValueError(f"BM25 chunk_id={chunk_id!r} 对应多个 doc_id")
                    indexed[chunk_id] = doc_id
            return indexed
        finally:
            con.close()

    def _search_sync(
        self,
        tokens: list[str],
        dataset_id: int,
        doc_id: int | None,
        top_k: int,
    ) -> list[SQLiteBm25Hit]:
        self._ensure_schema_sync()
        query = _fts_or_query(tokens)
        if not query:
            return []
        where_doc = "AND doc_id = ?" if doc_id is not None else ""
        params: list[object] = [
            query,
            self.coarse_weight,
            self.fine_weight,
            dataset_id,
        ]
        if doc_id is not None:
            params.append(doc_id)
        params.append(top_k)
        sql = f"""
            SELECT
                chunk_id,
                doc_id,
                -bm25(bm25_fts, ?, ?) AS score
            FROM bm25_fts
            WHERE bm25_fts MATCH ?
              AND dataset_id = ?
              {where_doc}
            ORDER BY bm25(bm25_fts, {self.coarse_weight:g}, {self.fine_weight:g}) ASC
            LIMIT ?
        """
        # MATCH 参数必须紧跟 FROM 表达式;为了保持 SQL 可读,这里按最终 SQL 顺序重排。
        ordered_params: list[object] = [
            self.coarse_weight,
            self.fine_weight,
            query,
            dataset_id,
        ]
        if doc_id is not None:
            ordered_params.append(doc_id)
        ordered_params.append(top_k)
        with self._connect() as con:
            rows = con.execute(sql, ordered_params).fetchall()
        return [
            SQLiteBm25Hit(chunk_id=str(chunk_id), doc_id=int(row_doc_id), score=float(score))
            for chunk_id, row_doc_id, score in rows
        ]

    def _verify_dataset_count_sync(
        self, dataset_id: int, user_id: int, expected_count: int
    ) -> None:
        resolved = self.path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        con = sqlite3.connect(resolved.as_uri() + "?mode=ro", uri=True)
        try:
            con.execute("BEGIN")  # 两项计数使用同一只读快照。
            version_row = con.execute(
                "SELECT version FROM bm25_meta ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            if version_row != (2,):
                raise ValueError("BM25 sidecar 需要 schema 2；请先调用 ensure_collection")
            total, matching, invalid_mappings = con.execute(
                """
                SELECT COUNT(*),
                       COALESCE(SUM(CASE WHEN f.dataset_id = ? AND f.user_id = ?
                                         THEN 1 ELSE 0 END), 0),
                       COALESCE(SUM(CASE WHEN m.fts_rowid IS NULL OR m.chunk_id IS NOT f.chunk_id
                                         THEN 1 ELSE 0 END), 0)
                FROM bm25_fts AS f
                LEFT JOIN bm25_chunk_rows AS m ON m.fts_rowid = f.rowid
                """,
                (dataset_id, user_id),
            ).fetchone()
            mapping_count = con.execute("SELECT COUNT(*) FROM bm25_chunk_rows").fetchone()[0]
            if (
                total != expected_count
                or matching != expected_count
                or mapping_count != expected_count
                or invalid_mappings
            ):
                raise ValueError(
                    "BM25 范围核对失败: "
                    f"expected={expected_count}, total={total}, matching={matching}, "
                    f"mapping_rows={mapping_count}, invalid_mappings={invalid_mappings}"
                )
        finally:
            con.close()


_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)
_LOCAL_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[a-z0-9_.]+", re.IGNORECASE)


@dataclass(frozen=True)
class SQLiteBm25Tokenized:
    coarse_tokens: str
    fine_tokens: str

    @property
    def tokens(self) -> list[str]:
        return [tok for tok in self.coarse_tokens.split() if tok]


class SQLiteBm25Tokenizer:
    """提供 eval BM25 检索器所需的本地分词接口。"""

    def tokenize(self, text: str) -> SQLiteBm25Tokenized:
        tokens = local_bm25_terms(text)
        joined = " ".join(tokens)
        return SQLiteBm25Tokenized(coarse_tokens=joined, fine_tokens=joined)


def local_bm25_terms(text: str) -> list[str]:
    """中文按字、英文/数字按词切分,与 SQLite FTS5 unicode61 口径配合。"""
    seen: set[str] = set()
    terms: list[str] = []
    for token in _LOCAL_TOKEN_RE.findall(text.lower()):
        if token and token not in seen:
            seen.add(token)
            terms.append(token)
    return terms


def local_bm25_tokens(text: str) -> Bm25Tokens:
    joined = " ".join(local_bm25_terms(text))
    return Bm25Tokens(coarse=joined, fine=joined)


def _fts_or_query(tokens: Sequence[str]) -> str:
    """把预分词 token 转成 FTS5 OR 查询。"""
    seen: set[str] = set()
    parts: list[str] = []
    for token in tokens:
        normalized = token.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        # FTS5 双引号 phrase 可安全承载中文/英文 token;内部双引号按 FTS5 规则转义。
        clean = " ".join(_TOKEN_RE.findall(normalized)) or normalized.replace('"', '""')
        if clean:
            parts.append(f'"{clean}"')
    return " OR ".join(parts)


def inspect_sqlite_bm25_identity(
    path: str | Path,
    *,
    coarse_weight: float = 2.0,
    fine_weight: float = 1.0,
) -> dict[str, object]:
    """只读汇总 sidecar 的路径、schema、数量和权重，不读取正文列。"""
    resolved = Path(path).expanduser().resolve()
    identity: dict[str, object] = {
        "backend": "sqlite_fts5",
        "path": str(resolved),
        "exists": resolved.is_file(),
        "schema_version": None,
        "chunk_count": 0,
        "dataset_counts": {},
        "coarse_weight": float(coarse_weight),
        "fine_weight": float(fine_weight),
    }
    if not resolved.is_file():
        return identity

    con = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)
    try:
        version_row = con.execute(
            "SELECT version FROM bm25_meta ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        identity["schema_version"] = int(version_row[0]) if version_row else None
        dataset_rows = con.execute(
            """
            SELECT dataset_id, COUNT(*)
            FROM bm25_fts
            GROUP BY dataset_id
            ORDER BY CAST(dataset_id AS INTEGER)
            """
        ).fetchall()
        identity["dataset_counts"] = {
            str(dataset_id): int(count) for dataset_id, count in dataset_rows
        }
        identity["chunk_count"] = sum(int(count) for _, count in dataset_rows)

        identity["file_size"] = resolved.stat().st_size
        return identity
    finally:
        con.close()
