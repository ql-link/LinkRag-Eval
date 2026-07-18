"""SQLite FTS5 BM25 后端。

用途:替代 Qdrant sparse-vector 形式的 BM25。FTS5 是进程内嵌入式全文索引,
适合 eval 的本地/单机检索场景。SQLite 模式使用 eval 本地轻量分词,避免额外依赖
生产 RagFlowTokenizer。
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

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
            if con.execute("SELECT COUNT(*) FROM bm25_meta").fetchone()[0] == 0:
                con.execute("INSERT INTO bm25_meta(version) VALUES (1)")

    def _upsert_sync(self, points: list[SQLiteBm25Point]) -> None:
        self._ensure_schema_sync()
        with self._connect() as con:
            for p in points:
                con.execute("DELETE FROM bm25_fts WHERE chunk_id = ?", (p.chunk_id,))
                con.execute(
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
    """FTS5 本地 tokenizer adapter,兼容 RagFlowTokenizer 的 ``tokenize`` 调用面。"""

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
