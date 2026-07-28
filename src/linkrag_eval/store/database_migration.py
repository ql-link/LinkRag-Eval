"""将旧 eval MySQL 六表精确复制为本地 SQLite。"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, func, insert, select, text

from linkrag_eval.store.models import EvalBase

TABLES = tuple(
    EvalBase.metadata.tables[name]
    for name in (
        "eval_dataset",
        "eval_corpus_chunk",
        "eval_query",
        "eval_qrel",
        "eval_run",
        "eval_metric_result",
    )
)


def sync_database(
    source_url: str,
    target_path: str | Path,
    *,
    replace: bool = False,
    batch_size: int = 2_000,
) -> dict[str, Any]:
    """在一致性只读快照中复制全部 eval 表，并原子安装 SQLite 文件。"""
    target = Path(target_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp-{os.getpid()}")
    backup: Path | None = None
    if target.exists() and not replace:
        raise FileExistsError(f"目标已存在，拒绝覆盖:{target}")
    if temporary.exists():
        temporary.unlink()

    source = create_engine(source_url, future=True, pool_pre_ping=True)
    sqlite = create_engine(f"sqlite:///{temporary}", future=True)
    try:
        EvalBase.metadata.create_all(sqlite)
        source_counts: dict[str, int] = {}
        source_digests: dict[str, str] = {}
        with source.connect() as source_conn, sqlite.begin() as target_conn:
            if source.dialect.name == "mysql":
                source_conn.execute(text("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
                source_conn.execute(text("START TRANSACTION READ ONLY, WITH CONSISTENT SNAPSHOT"))
            for table in TABLES:
                row_digests: list[bytes] = []
                count = 0
                primary_key = list(table.primary_key.columns)
                statement = select(table)
                if primary_key:
                    statement = statement.order_by(*primary_key)
                result = source_conn.execution_options(stream_results=True).execute(statement)
                batch: list[dict[str, Any]] = []
                for row in result.mappings():
                    record = dict(row)
                    row_digests.append(hashlib.sha256(_canonical_record(record)).digest())
                    count += 1
                    batch.append(record)
                    if len(batch) >= batch_size:
                        target_conn.execute(insert(table), batch)
                        batch.clear()
                if batch:
                    target_conn.execute(insert(table), batch)
                source_counts[table.name] = count
                source_digests[table.name] = _aggregate_digest(row_digests)
            target_conn.execute(
                text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
            )
            target_conn.execute(text("INSERT INTO alembic_version(version_num) VALUES ('0003')"))
            if source.dialect.name == "mysql":
                source_conn.rollback()

        target_counts, target_digests = _inspect_sqlite(sqlite)
        if target_counts != source_counts:
            raise RuntimeError(f"迁移计数不一致:source={source_counts}, target={target_counts}")
        if target_digests != source_digests:
            mismatches = {
                name: {"source": source_digests[name], "target": target_digests[name]}
                for name in source_digests
                if source_digests[name] != target_digests[name]
            }
            raise RuntimeError(f"迁移内容摘要不一致:{mismatches}")
        sqlite.dispose()
        source.dispose()

        if target.exists():
            stamp = datetime.now().strftime("%Y%m%d%H%M%S")
            backup = target.with_name(f"{target.name}.before-migration-{stamp}.bak")
            os.replace(target, backup)
        os.replace(temporary, target)
        return {
            "status": "ok",
            "source_dialect": source.dialect.name,
            "target": str(target),
            "backup": str(backup) if backup else None,
            "counts": target_counts,
            "table_sha256": target_digests,
            "sqlite_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "sqlite_bytes": target.stat().st_size,
        }
    except Exception:
        sqlite.dispose()
        source.dispose()
        if temporary.exists():
            temporary.unlink()
        raise


def _inspect_sqlite(engine: Engine) -> tuple[dict[str, int], dict[str, str]]:
    counts: dict[str, int] = {}
    digests: dict[str, str] = {}
    with engine.connect() as conn:
        for table in TABLES:
            counts[table.name] = int(
                conn.execute(select(func.count()).select_from(table)).scalar_one()
            )
            row_digests: list[bytes] = []
            statement = select(table)
            primary_key = list(table.primary_key.columns)
            if primary_key:
                statement = statement.order_by(*primary_key)
            for row in conn.execute(statement).mappings():
                row_digests.append(hashlib.sha256(_canonical_record(dict(row))).digest())
            digests[table.name] = _aggregate_digest(row_digests)
    return counts, digests


def _canonical_record(record: dict[str, Any]) -> bytes:
    normalized = {key: _normalize(value) for key, value in sorted(record.items())}
    return (
        json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def _aggregate_digest(row_digests: list[bytes]) -> str:
    """与数据库 collation 和返回顺序无关的表级摘要。"""
    digest = hashlib.sha256()
    for row_digest in sorted(row_digests):
        digest.update(row_digest)
    return digest.hexdigest()


def _normalize(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return (
            value.isoformat(timespec="microseconds")
            if isinstance(value, datetime)
            else value.isoformat()
        )
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    return value
