"""Golden V2 真实 query seed 导入。

用于把日志、客服问题、业务问题或开源 query 清洗成候选池可消费的
``query_seeds.jsonl``。本模块只做本地文件转换和脱敏检查,不连接生产库。
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


_SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_-]{12,}|api[_-]?key\s*[:=])", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class SeedImportReport:
    input_path: str
    output_path: str
    report_path: str | None
    source: str
    input_rows: int
    written: int
    skipped_short: int
    skipped_duplicate: int
    skipped_pii: int
    skipped_secret: int
    source_counts: dict[str, int]
    type_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        return (
            f"Golden V2 seed import: input={self.input_rows} written={self.written} "
            f"duplicate={self.skipped_duplicate} short={self.skipped_short} pii={self.skipped_pii}"
        )


def import_query_seeds(
    input_path: str | Path,
    *,
    out: str | Path,
    source: str,
    input_format: str = "auto",
    query_field: str = "query",
    id_field: str | None = None,
    domain_field: str | None = "domain",
    type_field: str | None = "type_hint",
    dataset_ids_field: str | None = "dataset_ids",
    min_chars: int = 2,
    max_chars: int = 300,
    reject_pii: bool = True,
    report_out: str | Path | None = None,
) -> SeedImportReport:
    if not source.strip():
        raise ValueError("source 不能为空")
    if min_chars <= 0 or max_chars < min_chars:
        raise ValueError("min_chars/max_chars 非法")
    path = Path(input_path)
    rows = _read_rows(path, input_format=input_format)
    seen_query: set[str] = set()
    seen_id: set[str] = set()
    out_rows: list[dict[str, Any]] = []
    skipped_short = 0
    skipped_duplicate = 0
    skipped_pii = 0
    skipped_secret = 0

    for index, row in enumerate(rows, start=1):
        query = _normalize_query(str(row.get(query_field) or ""))
        if _contains_secret(query):
            skipped_secret += 1
            continue
        if reject_pii and _contains_pii(query):
            skipped_pii += 1
            continue
        if len(query) < min_chars or len(query) > max_chars:
            skipped_short += 1
            continue
        query_key = query.casefold()
        if query_key in seen_query:
            skipped_duplicate += 1
            continue
        seed_id = _seed_id(source=source, row=row, id_field=id_field, query=query, index=index)
        if seed_id in seen_id:
            skipped_duplicate += 1
            continue
        seen_query.add(query_key)
        seen_id.add(seed_id)
        metadata = _metadata(row, passthrough_fields=("source_channel", "difficulty", "notes"))
        metadata["import_source"] = source
        metadata["input_row"] = index
        out_rows.append(
            {
                "seed_id": seed_id,
                "query": query,
                "source": source,
                "domain": _optional_string(row, domain_field),
                "type_hint": _optional_string(row, type_field),
                "dataset_ids": _dataset_ids(row, dataset_ids_field),
                "metadata": metadata,
            }
        )

    out_path = Path(out)
    _write_jsonl(out_path, out_rows)
    source_counts = Counter(str(row["source"]) for row in out_rows)
    type_counts = Counter(str(row.get("type_hint") or "unknown") for row in out_rows)
    report = SeedImportReport(
        input_path=str(path),
        output_path=str(out_path),
        report_path=str(report_out) if report_out else None,
        source=source,
        input_rows=len(rows),
        written=len(out_rows),
        skipped_short=skipped_short,
        skipped_duplicate=skipped_duplicate,
        skipped_pii=skipped_pii,
        skipped_secret=skipped_secret,
        source_counts=dict(sorted(source_counts.items())),
        type_counts=dict(sorted(type_counts.items())),
    )
    if report_out:
        report_path = Path(report_out)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return report


def _read_rows(path: Path, *, input_format: str) -> list[dict[str, Any]]:
    fmt = input_format.lower().strip()
    if fmt == "auto":
        suffix = path.suffix.lower()
        if suffix == ".jsonl":
            fmt = "jsonl"
        elif suffix in {".tsv", ".txt"}:
            fmt = "tsv"
        elif suffix == ".csv":
            fmt = "csv"
        else:
            fmt = "jsonl"
    if fmt == "jsonl":
        return _read_jsonl(path)
    if fmt in {"tsv", "csv"}:
        delimiter = "\t" if fmt == "tsv" else ","
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh, delimiter=delimiter)
            return [dict(row) for row in reader]
    raise ValueError(f"不支持的 input_format:{input_format}")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno} JSONL 非法:{exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{lineno} 行必须是 object")
            rows.append(row)
    return rows


def _normalize_query(query: str) -> str:
    return _WHITESPACE_RE.sub(" ", query).strip()


def _contains_secret(value: str) -> bool:
    return bool(_SECRET_RE.search(value))


def _contains_pii(value: str) -> bool:
    return bool(_PHONE_RE.search(value) or _EMAIL_RE.search(value) or _ID_CARD_RE.search(value))


def _seed_id(
    *,
    source: str,
    row: dict[str, Any],
    id_field: str | None,
    query: str,
    index: int,
) -> str:
    if id_field and row.get(id_field) not in (None, ""):
        raw = _slug(str(row[id_field]).strip())
        source_slug = _slug(source)
        if raw == source_slug or raw.startswith(f"{source_slug}-"):
            return raw
        return f"{source_slug}-{raw}"
    digest = hashlib.sha256(f"{source}\n{query}".encode("utf-8")).hexdigest()[:16]
    return f"{_slug(source)}-{index:06d}-{digest}"


def _optional_string(row: dict[str, Any], field: str | None) -> str | None:
    if not field:
        return None
    value = row.get(field)
    if value in (None, ""):
        return None
    return str(value).strip()


def _dataset_ids(row: dict[str, Any], field: str | None) -> list[int]:
    if not field:
        return []
    value = row.get(field)
    if value in (None, ""):
        return []
    if isinstance(value, list):
        values = value
    else:
        values = re.split(r"[,;\s]+", str(value))
    return sorted({int(v) for v in values if str(v).strip()})


def _metadata(row: dict[str, Any], *, passthrough_fields: Sequence[str] = ()) -> dict[str, Any]:
    raw = row.get("metadata")
    if isinstance(raw, dict):
        out = dict(raw)
    else:
        out = {}
    for field in passthrough_fields:
        value = row.get(field)
        if value not in (None, ""):
            out[field] = value
    return out


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _slug(value: str) -> str:
    text = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-") or "seed"
