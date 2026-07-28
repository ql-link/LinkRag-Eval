"""Blind v4 冻结与一次性运行门禁。"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def freeze_blind_v4(
    samples_path: str | Path,
    *,
    tune_paths: Iterable[str | Path],
    frozen_config_paths: Iterable[str | Path],
    out_dir: str | Path,
    min_samples: int = 500,
) -> dict[str, Any]:
    samples = _read_jsonl(Path(samples_path))
    if len(samples) < min_samples:
        raise ValueError(f"Blind v4 至少需要 {min_samples} 条，当前 {len(samples)}")
    ids = [str(row["id"]) for row in samples]
    if len(ids) != len(set(ids)):
        raise ValueError("Blind v4 sample id 重复")
    tune_rows = [row for path in tune_paths for row in _read_jsonl(Path(path))]
    tune_ids = {str(row.get("id") or row.get("sample_id")) for row in tune_rows}
    overlap_ids = sorted(set(ids).intersection(tune_ids))
    if overlap_ids:
        raise ValueError(f"Blind/Tune sample id 泄漏:{overlap_ids[:3]}")
    tune_queries = {_query_hash(str(row["query"])) for row in tune_rows if row.get("query")}
    overlap_queries = [row["id"] for row in samples if _query_hash(str(row["query"])) in tune_queries]
    if overlap_queries:
        raise ValueError(f"Blind/Tune query 文本泄漏:{overlap_queries[:3]}")
    missing_provenance = [row["id"] for row in samples if not row.get("provenance")]
    if missing_provenance:
        raise ValueError(f"Blind v4 缺来源元数据:{missing_provenance[:3]}")
    config_files = [Path(path) for path in frozen_config_paths]
    config_hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in config_files}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    frozen_path = out / "blind_v4.jsonl"
    _write_jsonl(frozen_path, samples)
    manifest = {
        "version": "blind_v4",
        "sample_count": len(samples),
        "golden_sha256": hashlib.sha256(frozen_path.read_bytes()).hexdigest(),
        "config_sha256": config_hashes,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "run_count": 0,
        "run_id": None,
        "result_sha256": None,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def claim_blind_v4_run(out_dir: str | Path, *, run_id: str) -> dict[str, Any]:
    """在真正召回前原子占用唯一运行机会，失败也不得调参后重跑。"""
    out = Path(out_dir)
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if int(manifest.get("run_count", 0)) != 0:
        raise RuntimeError(f"Blind v4 已运行，禁止第二次揭盲:{manifest.get('run_id')}")
    current_sha = hashlib.sha256((out / "blind_v4.jsonl").read_bytes()).hexdigest()
    if current_sha != manifest["golden_sha256"]:
        raise RuntimeError("Blind v4 golden 冻结后被修改")
    manifest["run_count"] = 1
    manifest["run_id"] = run_id
    manifest["claimed_at"] = datetime.now(timezone.utc).isoformat()
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, manifest_path)
    return manifest


def seal_blind_v4_result(out_dir: str | Path, *, result_path: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if int(manifest.get("run_count", 0)) != 1 or not manifest.get("run_id"):
        raise RuntimeError("Blind v4 尚未 claim")
    result = Path(result_path)
    manifest["result_sha256"] = hashlib.sha256(result.read_bytes()).hexdigest()
    manifest["sealed_at"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def _query_hash(query: str) -> str:
    return hashlib.sha256(" ".join(query.casefold().split()).encode("utf-8")).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
