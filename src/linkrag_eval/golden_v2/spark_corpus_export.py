"""将 Spark 标准化 chunk_records 导出现有 ingest 输入格式。

导出器只写 ``collection.tsv`` 与 ``manifest.jsonl``。真正入库仍走 ``linkrag-eval ingest``,
从而复用 eval MySQL/Qdrant 护栏和索引流程。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from linkrag_eval.store.ids import content_hash, eval_chunk_id


@dataclass(frozen=True)
class SparkCorpusExportReport:
    chunks: int
    dataset_ids: list[int]
    doc_id_min: int | None
    doc_id_max: int | None
    collection_path: str
    manifest_path: str
    report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        datasets = ",".join(str(x) for x in self.dataset_ids) or "(空)"
        return (
            f"Spark corpus 导出完成: chunks={self.chunks} datasets={datasets} "
            f"doc_id={self.doc_id_min}-{self.doc_id_max}"
        )


def export_spark_corpus(
    chunks_path: str | Path,
    *,
    collection_out: str | Path,
    manifest_out: str | Path,
    report_out: str | Path | None = None,
    dataset_id: int | None = None,
) -> SparkCorpusExportReport:
    """把 ``chunk_records.jsonl`` 转成 ``collection.tsv`` 与 ``manifest.jsonl``。"""

    rows = _read_chunk_records(Path(chunks_path), dataset_id=dataset_id)
    collection_path = Path(collection_out)
    manifest_path = Path(manifest_out)
    collection_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    with collection_path.open("w", encoding="utf-8") as collection_fh, manifest_path.open(
        "w", encoding="utf-8"
    ) as manifest_fh:
        for row in rows:
            source_id = _source_id(row)
            text = str(row["content"]).replace("\t", " ").replace("\n", " ").strip()
            collection_fh.write(f"{source_id}\t{text}\n")
            manifest_fh.write(
                json.dumps(
                    {
                        "source_id": source_id,
                        "doc_id": int(row["doc_id"]),
                        "status": "success",
                        "ordinal": int(row["ordinal"]),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    doc_ids = [int(row["doc_id"]) for row in rows]
    report = SparkCorpusExportReport(
        chunks=len(rows),
        dataset_ids=sorted({int(row["dataset_id"]) for row in rows}),
        doc_id_min=min(doc_ids) if doc_ids else None,
        doc_id_max=max(doc_ids) if doc_ids else None,
        collection_path=str(collection_path),
        manifest_path=str(manifest_path),
        report_path=str(report_out) if report_out else None,
    )
    if report_out:
        path = Path(report_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def _read_chunk_records(path: Path, *, dataset_id: int | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_source_ids: set[str] = set()
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno} chunk_records JSONL 非法:{exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{lineno} chunk_records 行必须是 object")
            normalized = _normalize_chunk_row(row, label=f"{path}:{lineno}")
            if dataset_id is not None and normalized["dataset_id"] != dataset_id:
                raise ValueError(
                    f"{path}:{lineno} dataset_id={normalized['dataset_id']} 与参数 {dataset_id} 不一致"
                )
            source_id = _source_id(normalized)
            if source_id in seen_source_ids:
                raise ValueError(f"{path}:{lineno} source_id 重复:{source_id}")
            seen_source_ids.add(source_id)
            rows.append(normalized)
    if not rows:
        raise ValueError(f"{path} chunk_records 为空")
    return rows


def _normalize_chunk_row(row: dict[str, Any], *, label: str) -> dict[str, Any]:
    missing = [field for field in ("dataset_id", "doc_id", "ordinal", "content") if row.get(field) in (None, "")]
    if missing:
        raise ValueError(f"{label} 缺必填字段:{missing}")
    dataset_id = int(row["dataset_id"])
    doc_id = int(row["doc_id"])
    ordinal = int(row["ordinal"])
    content = str(row["content"]).strip()
    if not content:
        raise ValueError(f"{label} content 为空")

    expected_chunk_id = eval_chunk_id(dataset_id, doc_id, ordinal)
    if row.get("chunk_id") and str(row["chunk_id"]) != expected_chunk_id:
        raise ValueError(f"{label} chunk_id 与 uuid5 规则不一致")
    if row.get("content_hash") and _strip_sha_prefix(str(row["content_hash"])) != content_hash(content):
        raise ValueError(f"{label} content_hash 不一致")

    out = dict(row)
    out.update(
        {
            "dataset_id": dataset_id,
            "doc_id": doc_id,
            "ordinal": ordinal,
            "content": content,
            "chunk_id": expected_chunk_id,
            "content_hash": content_hash(content),
        }
    )
    return out


def _source_id(row: dict[str, Any]) -> str:
    raw = row.get("source_passage_id")
    if raw:
        return str(raw)
    return f"spark-{int(row['dataset_id'])}-{int(row['doc_id'])}-{int(row['ordinal'])}"


def _strip_sha_prefix(value: str) -> str:
    value = value.strip()
    return value.split(":", 1)[1] if value.startswith("sha256:") else value
