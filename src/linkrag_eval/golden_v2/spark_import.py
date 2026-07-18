"""Spark 离线预生成 bundle 导入器。

本模块只做文件级验证和标准化输出,不连接数据库、不调用模型 API。它的核心作用是把
Codex sub-agent ``gpt-5.3-codex-spark`` 生成的大批量原料变成后续候选池可消费的
jsonl,并在入口处拦住模型混用、hash 不一致、泄漏答案词和 chunk_id 漂移。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from linkrag_eval.store.ids import content_hash, eval_chunk_id

SPARK_MODEL = "gpt-5.3-codex-spark"
SCHEMA_VERSION = "eval-offline-batch-v1"

_SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_-]{12,}|api[_-]?key\s*[:=])", re.IGNORECASE)


@dataclass(frozen=True)
class SparkImportReport:
    """一次 Spark bundle 接入校验的结果摘要。"""

    batch_id: str
    generator_model: str
    corpus_blueprints: int
    chunk_records: int
    query_seeds: int
    hard_case_seeds: int
    rewrite_seeds: int
    output_paths: dict[str, str]

    @property
    def total_seed_rows(self) -> int:
        return self.query_seeds + self.hard_case_seeds + self.rewrite_seeds

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["total_seed_rows"] = self.total_seed_rows
        return data

    def summary(self) -> str:
        return (
            "Spark bundle 导入完成:"
            f" batch={self.batch_id} model={self.generator_model} "
            f"corpus={self.corpus_blueprints} chunks={self.chunk_records} "
            f"query={self.query_seeds} hard={self.hard_case_seeds} rewrite={self.rewrite_seeds}"
        )


def import_spark_bundle(
    manifest_path: str | Path,
    *,
    out: str | Path,
    hard_out: str | Path | None = None,
    rewrite_out: str | Path | None = None,
    corpus_out: str | Path | None = None,
    chunks_out: str | Path | None = None,
    report_out: str | Path | None = None,
    expected_model: str = SPARK_MODEL,
    dry_run: bool = False,
) -> SparkImportReport:
    """校验并导入 Spark 离线 bundle。

    ``out`` 是标准化后的 query seeds 输出。其他输出未显式传入时,会落在 ``out`` 同目录。
    dry_run=True 时只校验并返回报告,不写任何输出文件。
    """

    manifest_path = Path(manifest_path)
    manifest = _load_json(manifest_path)
    _validate_manifest(manifest, expected_model=expected_model)
    _scan_for_secret(manifest, str(manifest_path))

    base_dir = manifest_path.parent
    artifacts = _artifact_map(manifest)
    for kind, artifact in artifacts.items():
        _verify_artifact_hash(base_dir / str(artifact["path"]), str(artifact["sha256"]))
        _scan_file_for_secret(base_dir / str(artifact["path"]))

    batch_id = str(manifest["batch_id"])
    generator_model = str(manifest["generator"]["model"])

    corpus_rows = _read_artifact_rows(base_dir, artifacts, "corpus_blueprints")
    chunk_rows = _read_artifact_rows(base_dir, artifacts, "chunk_records")
    query_rows = _read_artifact_rows(base_dir, artifacts, "query_seeds")
    hard_rows = _read_artifact_rows(base_dir, artifacts, "hard_case_seeds")
    rewrite_rows = _read_artifact_rows(base_dir, artifacts, "rewrite_seeds")

    normalized_corpus = _validate_corpus_blueprints(corpus_rows, batch_id=batch_id)
    normalized_chunks = _validate_chunk_records(chunk_rows, batch_id=batch_id)
    normalized_queries = _validate_query_seeds(
        query_rows, batch_id=batch_id, generator_model=generator_model
    )
    normalized_hard = _validate_hard_case_seeds(
        hard_rows, batch_id=batch_id, generator_model=generator_model
    )
    normalized_rewrites = _validate_query_seeds(
        rewrite_rows, batch_id=batch_id, generator_model=generator_model,
        id_field="seed_id",
    )

    out_path = Path(out)
    output_paths = {
        "query_seeds": str(out_path),
        "hard_case_seeds": str(Path(hard_out) if hard_out else out_path.with_name("hard_case_seeds.jsonl")),
        "rewrite_seeds": str(Path(rewrite_out) if rewrite_out else out_path.with_name("rewrite_seeds.jsonl")),
        "corpus_blueprints": str(
            Path(corpus_out) if corpus_out else out_path.with_name("corpus_blueprints.jsonl")
        ),
        "chunk_records": str(Path(chunks_out) if chunks_out else out_path.with_name("chunk_records.jsonl")),
    }
    if report_out is not None:
        output_paths["report"] = str(Path(report_out))
    else:
        output_paths["report"] = str(out_path.with_name("spark_import_report.json"))

    report = SparkImportReport(
        batch_id=batch_id,
        generator_model=generator_model,
        corpus_blueprints=len(normalized_corpus),
        chunk_records=len(normalized_chunks),
        query_seeds=len(normalized_queries),
        hard_case_seeds=len(normalized_hard),
        rewrite_seeds=len(normalized_rewrites),
        output_paths=output_paths,
    )
    if dry_run:
        return report

    _write_jsonl(Path(output_paths["query_seeds"]), normalized_queries)
    _write_jsonl(Path(output_paths["hard_case_seeds"]), normalized_hard)
    _write_jsonl(Path(output_paths["rewrite_seeds"]), normalized_rewrites)
    _write_jsonl(Path(output_paths["corpus_blueprints"]), normalized_corpus)
    _write_jsonl(Path(output_paths["chunk_records"]), normalized_chunks)
    _write_json(Path(output_paths["report"]), report.to_dict())
    return report


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"bundle manifest 不存在:{path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} manifest JSON 非法:{exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} manifest 必须是 JSON object")
    return data


def _validate_manifest(manifest: dict[str, Any], *, expected_model: str) -> None:
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"bundle schema_version 必须是 {SCHEMA_VERSION},实际 {manifest.get('schema_version')}"
        )
    if not manifest.get("batch_id"):
        raise ValueError("bundle manifest 缺 batch_id")
    generator = manifest.get("generator")
    if not isinstance(generator, dict):
        raise ValueError("bundle manifest 缺 generator")
    model = generator.get("model")
    if model != expected_model:
        raise ValueError(f"生成模型必须是 {expected_model},实际 {model}")
    if not isinstance(manifest.get("artifacts"), list):
        raise ValueError("bundle manifest 缺 artifacts 列表")


def _artifact_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for i, artifact in enumerate(manifest["artifacts"], start=1):
        if not isinstance(artifact, dict):
            raise ValueError(f"artifact[{i}] 必须是 object")
        kind = str(artifact.get("kind") or "")
        path = artifact.get("path")
        sha = artifact.get("sha256")
        if not kind or not path or not sha:
            raise ValueError(f"artifact[{i}] 缺 kind/path/sha256")
        if kind in out:
            raise ValueError(f"artifact kind 重复:{kind}")
        out[kind] = artifact
    return out


def _verify_artifact_hash(path: Path, expected: str) -> None:
    if not path.exists():
        raise ValueError(f"artifact 不存在:{path}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != _normalize_sha256(expected):
        raise ValueError(f"artifact hash 不一致:{path} expected={expected} actual=sha256:{actual}")


def _normalize_sha256(raw: str) -> str:
    value = raw.strip()
    if value.startswith("sha256:"):
        value = value.split(":", 1)[1]
    if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise ValueError(f"sha256 格式非法:{raw}")
    return value.lower()


def _read_artifact_rows(
    base_dir: Path, artifacts: dict[str, dict[str, Any]], kind: str
) -> list[dict[str, Any]]:
    artifact = artifacts.get(kind)
    if artifact is None:
        return []
    return _read_jsonl(base_dir / str(artifact["path"]), kind=kind)


def _read_jsonl(path: Path, *, kind: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno} {kind} JSONL 非法:{exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{lineno} {kind} 行必须是 object")
            rows.append(row)
    return rows


def _validate_corpus_blueprints(rows: list[dict[str, Any]], *, batch_id: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        _require_fields(row, ["blueprint_id", "body"], "corpus_blueprints")
        blueprint_id = str(row["blueprint_id"])
        _reject_duplicate(seen, blueprint_id, "blueprint_id")
        body = str(row["body"]).strip()
        if not body:
            raise ValueError(f"corpus blueprint {blueprint_id} body 为空")
        normalized = dict(row)
        normalized["blueprint_id"] = blueprint_id
        normalized["body"] = body
        normalized.setdefault("metadata", {})
        normalized["metadata"] = _metadata_with_batch(normalized["metadata"], batch_id)
        out.append(normalized)
    return out


def _validate_chunk_records(rows: list[dict[str, Any]], *, batch_id: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        _require_fields(row, ["dataset_id", "doc_id", "ordinal", "content"], "chunk_records")
        dataset_id = int(row["dataset_id"])
        doc_id = int(row["doc_id"])
        ordinal = int(row["ordinal"])
        text = str(row["content"]).strip()
        if not text:
            raise ValueError(f"chunk record dataset={dataset_id} doc={doc_id} ordinal={ordinal} content 为空")
        expected_chunk_id = eval_chunk_id(dataset_id, doc_id, ordinal)
        provided_chunk_id = row.get("chunk_id")
        if provided_chunk_id and str(provided_chunk_id) != expected_chunk_id:
            raise ValueError(
                "chunk_id 与 uuid5 规则不一致:"
                f" dataset={dataset_id} doc={doc_id} ordinal={ordinal}"
            )
        expected_hash = content_hash(text)
        provided_hash = row.get("content_hash")
        if provided_hash and _normalize_optional_sha256(str(provided_hash)) != expected_hash:
            raise ValueError(f"chunk content_hash 不一致: chunk_id={expected_chunk_id}")
        _reject_duplicate(seen, expected_chunk_id, "chunk_id")
        normalized = dict(row)
        normalized.update(
            {
                "dataset_id": dataset_id,
                "doc_id": doc_id,
                "ordinal": ordinal,
                "content": text,
                "content_hash": expected_hash,
                "chunk_id": expected_chunk_id,
            }
        )
        normalized.setdefault("metadata", {})
        normalized["metadata"] = _metadata_with_batch(normalized["metadata"], batch_id)
        out.append(normalized)
    return out


def _validate_query_seeds(
    rows: list[dict[str, Any]],
    *,
    batch_id: str,
    generator_model: str,
    id_field: str = "seed_id",
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        _require_fields(row, [id_field, "query", "source"], "query_seeds")
        seed_id = str(row[id_field])
        _reject_duplicate(seen, seed_id, id_field)
        query = str(row["query"]).strip()
        if len(query) < 2:
            raise ValueError(f"query seed {seed_id} query 过短")
        _validate_must_not_contain(seed_id, query, row.get("must_not_contain"))
        normalized = dict(row)
        normalized[id_field] = seed_id
        normalized["query"] = query
        normalized.setdefault("source", "spark_pregen")
        normalized.setdefault("metadata", {})
        normalized["metadata"] = _metadata_with_batch(
            normalized["metadata"], batch_id, generator_model=generator_model
        )
        out.append(normalized)
    return out


def _validate_hard_case_seeds(
    rows: list[dict[str, Any]], *, batch_id: str, generator_model: str
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        _require_fields(row, ["seed_id", "query", "hard_reason"], "hard_case_seeds")
        seed_id = str(row["seed_id"])
        _reject_duplicate(seen, seed_id, "seed_id")
        query = str(row["query"]).strip()
        if len(query) < 2:
            raise ValueError(f"hard case {seed_id} query 过短")
        normalized = dict(row)
        normalized["seed_id"] = seed_id
        normalized["query"] = query
        normalized.setdefault("source", "spark_pregen")
        normalized.setdefault("metadata", {})
        normalized["metadata"] = _metadata_with_batch(
            normalized["metadata"], batch_id, generator_model=generator_model
        )
        out.append(normalized)
    return out


def _require_fields(row: dict[str, Any], fields: Iterable[str], label: str) -> None:
    missing = [field for field in fields if row.get(field) in (None, "")]
    if missing:
        raise ValueError(f"{label} 缺必填字段:{missing}")


def _reject_duplicate(seen: set[str], value: str, label: str) -> None:
    if value in seen:
        raise ValueError(f"{label} 重复:{value}")
    seen.add(value)


def _validate_must_not_contain(seed_id: str, query: str, raw_terms: Any) -> None:
    if raw_terms is None:
        return
    if not isinstance(raw_terms, list):
        raise ValueError(f"query seed {seed_id} must_not_contain 必须是列表")
    lowered = query.lower()
    leaked = [str(term) for term in raw_terms if str(term).strip() and str(term).lower() in lowered]
    if leaked:
        raise ValueError(f"query seed {seed_id} 泄漏答案词:{leaked}")


def _metadata_with_batch(
    metadata: Any, batch_id: str, *, generator_model: str | None = None
) -> dict[str, Any]:
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ValueError("metadata 必须是 object")
    out = dict(metadata)
    out.setdefault("generator_batch_id", batch_id)
    if generator_model:
        out.setdefault("generator_model", generator_model)
    return out


def _normalize_optional_sha256(raw: str) -> str:
    return _normalize_sha256(raw)


def _scan_file_for_secret(path: Path) -> None:
    _scan_for_secret(path.read_text(encoding="utf-8"), str(path))


def _scan_for_secret(value: Any, label: str) -> None:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    if _SECRET_RE.search(text):
        raise ValueError(f"{label} 疑似包含 API key 或密钥字段")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
