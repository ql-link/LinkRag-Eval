"""Internal Stress v6 Dev 三路检索证据的准备、执行与封存。

本模块只处理已双审裁决的 ``internal-v6-dev`` release。它把 112 条合成单段文档写入
一次性、版本化的 eval Qdrant collection 和本地 SQLite FTS5，然后用同一 Dense/Sparse
编码器实例逐 Query 执行当前 Recall 候选契约。输出分成 ``method_view`` 与
``evaluation_view``，不得用于 Gate A/B。

正式执行采用两阶段协议：``prepare`` 只做本地校验并冻结脱敏计划；``execute`` 只允许对
处于 PREPARED 状态的计划执行一次。失败后不得原地重试，也不会自动删除远端 collection。
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sqlite3
import subprocess
import uuid
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from linkrag_eval.config import EvalSettings
from linkrag_eval.store.ids import eval_chunk_id

ROUTE_EVIDENCE_VERSION = (
    "ROBUST-FUSION-INTERNAL-V6-DEV-ROUTE-EVIDENCE-2026-08-29-v1"
)
EXPECTED_RELEASE_VERSION = (
    "ROBUST-FUSION-INTERNAL-V6-DEV-ADJUDICATED-2026-08-29-v1"
)
EXPECTED_RELEASE_MANIFEST_SHA256 = (
    "ad32fbb08a6b076dced1e438ff51060c46073b932cd259ff89beb157e5453bac"
)
CANDIDATE_CONTRACT_VERSION = "robust-fusion-internal-v6-dev-route-evidence-v1"
CANDIDATE_PROFILE = "internal-v6-dev-production-route-profile-v1"
EXECUTION_CONFIRMATION = "EXECUTE_INTERNAL_V6_DEV_ROUTE_EVIDENCE_V1"
DEFAULT_DATASET_ID = 996_601
ROUTES = ("dense", "sparse", "bm25")
RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")

METHOD_VIEW_FORBIDDEN_FIELDS = frozenset(
    {
        "source_query_id",
        "source_chunk_id",
        "source_document_id",
        "source_relevance_label",
        "target_equivalence_group_id",
        "target_relation",
        "conflict_type",
        "adjudicability",
        "query_origin",
        "origin",
        "quota_cell",
        "pool_role",
        "pressure_chain",
        "construction_role",
        "query_family_id",
        "document_family_id",
        "version_family_id",
        "counterfactual_template_family_id",
        "evidence_locator_local",
        "evidence_span_local",
        "reviewer_a",
        "reviewer_b",
        "adjudicator",
        "review_status",
        "handbook_version",
        "exposure_status",
    }
)


@dataclass(frozen=True)
class InternalV6DevRelease:
    root: Path
    manifest: dict[str, Any]
    manifest_sha256: str
    queries: list[dict[str, str]]
    documents: list[dict[str, str]]
    evidence: list[dict[str, str]]
    families: list[dict[str, str]]
    case_mapping: list[dict[str, Any]]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise TypeError(f"{path}:{lineno} 必须是 JSON object")
        rows.append(value)
    return rows


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text("".join(canonical_json(row) + "\n" for row in rows), encoding="utf-8")
    path.chmod(0o600)


def verify_dev_release(root: Path) -> InternalV6DevRelease:
    """逐文件验证冻结 Dev release，并闭门检查 28/112/112/28 关系。"""

    root = root.resolve()
    manifest_path = root / "manifest.json"
    receipt_path = root / "manifest.sha256"
    if not manifest_path.is_file() or not receipt_path.is_file():
        raise RuntimeError(f"Dev release 缺少 manifest 或回执：{root}")
    manifest_sha256 = sha256_file(manifest_path)
    recorded = receipt_path.read_text(encoding="utf-8").split()[0]
    if recorded != manifest_sha256:
        raise RuntimeError("Dev release manifest 回执不匹配")
    if manifest_sha256 != EXPECTED_RELEASE_MANIFEST_SHA256:
        raise RuntimeError("Dev release manifest 不是主持人已冻结的预期版本")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("release_version") != EXPECTED_RELEASE_VERSION:
        raise RuntimeError("Dev release version 不匹配")
    if manifest.get("split_role") != "internal-v6-dev":
        raise RuntimeError("只允许 internal-v6-dev")
    if manifest.get("gate_eligibility") != "NOT_ELIGIBLE":
        raise RuntimeError("Dev release 的 Gate 资格状态异常")
    if manifest.get("gate_a_executed") or manifest.get("gate_b_executed"):
        raise RuntimeError("Dev release 不得带 Gate A/B 执行状态")
    if not manifest.get("annotation_ready"):
        raise RuntimeError("Dev release 尚未完成标注裁决")
    if manifest.get("retrieval_route_evidence_ready"):
        raise RuntimeError("输入 release 已宣称存在三路证据，拒绝重复物化")

    for item in manifest.get("files", []):
        path = root / str(item["path"])
        if not path.is_file():
            raise RuntimeError(f"Dev release 文件缺失：{path}")
        if path.stat().st_size != int(item["size_bytes"]):
            raise RuntimeError(f"Dev release 文件大小漂移：{path}")
        if sha256_file(path) != item["sha256"]:
            raise RuntimeError(f"Dev release 文件 hash 漂移：{path}")

    queries = read_tsv(root / "query_intake.tsv")
    documents = read_tsv(root / "document_intake.tsv")
    evidence = read_tsv(root / "evidence_intake.tsv")
    families = read_tsv(root / "family_assignment.tsv")
    case_mapping = read_jsonl(root / "case_mapping.jsonl")
    expected_counts = (28, 112, 112, 28, 28)
    actual_counts = (
        len(queries),
        len(documents),
        len(evidence),
        len(families),
        len(case_mapping),
    )
    if actual_counts != expected_counts:
        raise RuntimeError(f"Dev release 计数不符：{actual_counts} != {expected_counts}")

    query_ids = [row["source_query_id"] for row in queries]
    chunk_ids = [row["source_chunk_id"] for row in documents]
    if len(set(query_ids)) != len(query_ids) or len(set(chunk_ids)) != len(chunk_ids):
        raise RuntimeError("Dev release Query/Chunk ID 不唯一")
    for row in queries:
        if sha256_text(row["query_text_local"]) != row["query_sha256"]:
            raise RuntimeError(f"Query 正文 hash 不符：{row['source_query_id']}")
        if row["proposed_cohort"] != "internal-v6-dev":
            raise RuntimeError(f"Query cohort 非 Dev：{row['source_query_id']}")
    for row in documents:
        if sha256_text(row["document_text_local"]) != row["content_sha256"]:
            raise RuntimeError(f"Chunk 正文 hash 不符：{row['source_chunk_id']}")
        if row["exposure_status"] != "dev_exposed":
            raise RuntimeError(f"Chunk exposure 非 Dev：{row['source_chunk_id']}")

    evidence_units = [(row["source_query_id"], row["source_chunk_id"]) for row in evidence]
    if len(set(evidence_units)) != len(evidence_units):
        raise RuntimeError("Dev release evidence Query×Chunk 不唯一")
    if set(query_ids) != {query_id for query_id, _ in evidence_units}:
        raise RuntimeError("Dev release evidence 的 Query 外键不闭合")
    if not {chunk_id for _, chunk_id in evidence_units}.issubset(set(chunk_ids)):
        raise RuntimeError("Dev release evidence 的 Chunk 外键不闭合")
    per_query = Counter(query_id for query_id, _ in evidence_units)
    if set(per_query.values()) != {4}:
        raise RuntimeError("每个 Dev Query 必须恰有 target+3 candidates")

    return InternalV6DevRelease(
        root=root,
        manifest=manifest,
        manifest_sha256=manifest_sha256,
        queries=queries,
        documents=documents,
        evidence=evidence,
        families=families,
        case_mapping=case_mapping,
    )


def _opaque_query_id(release_version: str, source_query_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{release_version}:query:{source_query_id}"))


def _opaque_doc_id(release_version: str, source_chunk_id: str) -> int:
    raw = sha256_text(f"{release_version}:doc:{source_chunk_id}")
    return int(raw[:15], 16) + 1


def build_identity_maps(
    release: InternalV6DevRelease, *, dataset_id: int
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    if dataset_id <= 0:
        raise RuntimeError("dataset_id 必须为正整数")
    query_map = {
        row["source_query_id"]: _opaque_query_id(
            release.manifest["release_version"], row["source_query_id"]
        )
        for row in release.queries
    }
    chunk_map: dict[str, dict[str, Any]] = {}
    used_doc_ids: set[int] = set()
    used_chunk_ids: set[str] = set()
    for row in release.documents:
        source_chunk_id = row["source_chunk_id"]
        doc_id = _opaque_doc_id(release.manifest["release_version"], source_chunk_id)
        if doc_id in used_doc_ids:
            raise RuntimeError("确定性 doc_id 发生碰撞")
        used_doc_ids.add(doc_id)
        chunk_id = eval_chunk_id(dataset_id, doc_id, 0)
        if chunk_id in used_chunk_ids:
            raise RuntimeError("确定性 chunk_id 发生碰撞")
        used_chunk_ids.add(chunk_id)
        chunk_map[source_chunk_id] = {
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "dataset_id": dataset_id,
            "ordinal": 0,
        }
    return query_map, chunk_map


def _redacted_runtime_fingerprint(settings: EvalSettings) -> dict[str, Any]:
    return {
        "dense": {
            "provider": "openai_compatible",
            "model": settings.embed_model,
            "dim": settings.embed_dim,
            "batch_size": settings.embed_batch_size,
            "concurrency": settings.embed_concurrency,
            "timeout_ms": settings.embed_timeout_ms,
            "max_retries": 0,
            "endpoint_sha256": sha256_text(settings.embed_base_url.rstrip("/")),
            "api_key_present": bool(settings.embed_api_key.strip()),
        },
        "sparse": {
            "provider": settings.sparse_provider,
            "model": settings.sparse_model,
            "top_k": settings.sparse_top_k,
            "min_weight": settings.sparse_min_weight,
            "concurrency": settings.sparse_concurrency,
            "timeout_ms": settings.sparse_timeout_ms,
            "max_retries": 0,
            "endpoint_sha256": sha256_text(settings.sparse_base_url.rstrip("/")),
            "api_key_present": bool(settings.sparse_api_key.strip()),
        },
        "bm25": {
            "mode": settings.bm25_mode,
            "tokenizer": "linkrag_eval.store.sqlite_bm25.local_bm25_terms@v1",
            "coarse_weight": settings.bm25_sqlite_coarse_weight,
            "fine_weight": settings.bm25_sqlite_fine_weight,
        },
        "recall": {
            "route_top_ks": {
                "dense": settings.recall_dense_top_k,
                "sparse": settings.recall_sparse_top_k,
                "bm25": settings.recall_bm25_top_k,
            },
            "route_score_thresholds": {
                "dense": settings.recall_dense_score_threshold,
                "sparse": settings.recall_sparse_score_threshold,
            },
            "fusion_weights": {
                "dense": settings.recall_dense_weight,
                "sparse": settings.recall_sparse_weight,
                "bm25": settings.recall_bm25_weight,
            },
            "strict": True,
            "automatic_query_retry": 0,
        },
        "qdrant": {
            "host_sha256": sha256_text(settings.qdrant_host.rstrip("/")),
            "bucket_count": settings.qdrant_bucket_count,
            "routing_user_id": settings.user_id,
        },
    }


def validate_research_runtime(settings: EvalSettings) -> None:
    errors = []
    if settings.embed_model != "text-embedding-v4":
        errors.append("Dense 必须为 text-embedding-v4")
    if not settings.embed_base_url.strip() or not settings.embed_api_key.strip():
        errors.append("Dense endpoint/key 未配置")
    if settings.sparse_provider.lower() != "ark":
        errors.append("Learned Sparse provider 必须为 ark")
    if settings.sparse_model != "doubao-embedding-vision-251215":
        errors.append("Learned Sparse 模型必须为 doubao-embedding-vision-251215")
    if not settings.sparse_base_url.strip() or not settings.sparse_api_key.strip():
        errors.append("Sparse endpoint/key 未配置")
    if settings.bm25_mode != "sqlite_fts5":
        errors.append("BM25 必须为 sqlite_fts5")
    if "eval" not in settings.qdrant_prefix:
        errors.append("基础 Qdrant prefix 缺少 eval 护栏")
    if not settings.qdrant_host.strip():
        errors.append("Qdrant host 未配置")
    if errors:
        raise RuntimeError("；".join(errors))


def _git_state(root: Path) -> dict[str, Any]:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
        return {"git_sha": sha, "git_dirty": bool(status)}
    except (OSError, subprocess.CalledProcessError):
        return {"git_sha": "unknown", "git_dirty": True}


def _collection_prefix(run_id: str) -> str:
    normalized = run_id.replace("-", "_")
    prefix = f"eval_rf_internal_v6_dev_{normalized}"
    if len(prefix) > 120:
        prefix = f"eval_rf_internal_v6_dev_{sha256_text(run_id)[:16]}"
    return prefix


def build_run_plan(
    *,
    repo_root: Path,
    release_root: Path,
    output_root: Path,
    run_id: str,
    dataset_id: int,
    settings: EvalSettings,
) -> dict[str, Any]:
    if not RUN_ID_RE.fullmatch(run_id):
        raise RuntimeError("run_id 仅允许 3—64 位小写字母、数字和连字符")
    validate_research_runtime(settings)
    release = verify_dev_release(release_root)
    query_map, chunk_map = build_identity_maps(release, dataset_id=dataset_id)
    prefix = _collection_prefix(run_id)
    from linkrag_eval.store.vector_store import resolve_eval_qdrant_collection

    collection = resolve_eval_qdrant_collection(
        prefix=prefix,
        bucket_count=settings.qdrant_bucket_count,
        user_id=settings.user_id,
    )
    fingerprint = _redacted_runtime_fingerprint(settings)
    output_relative = output_root.resolve().relative_to(repo_root.resolve()).as_posix()
    release_relative = release_root.resolve().relative_to(repo_root.resolve()).as_posix()
    dense_doc_requests = math.ceil(len(release.documents) / settings.embed_batch_size)
    return {
        "plan_version": ROUTE_EVIDENCE_VERSION,
        "prepared_at_local": now_iso(),
        "run_id": run_id,
        "state": "PREPARED",
        "confirmation_token": EXECUTION_CONFIRMATION,
        "scope": {
            "split_role": "internal-v6-dev",
            "origin": "synthetic",
            "gate_eligibility": "NOT_ELIGIBLE",
            "gate_a_executed": False,
            "gate_b_executed": False,
            "formal_p4_02_snapshot": False,
            "purpose": "Dev-only route evidence and measurement calibration",
        },
        "input": {
            "release_path": release_relative,
            "release_version": release.manifest["release_version"],
            "release_manifest_sha256": release.manifest_sha256,
            "content_root_sha256": release.manifest["content_root_sha256"],
            "query_count": len(release.queries),
            "document_chunk_count": len(release.documents),
            "evidence_label_count": len(release.evidence),
        },
        "identity": {
            "dataset_id": dataset_id,
            "query_map_sha256": sha256_text(canonical_json(query_map)),
            "chunk_map_sha256": sha256_text(canonical_json(chunk_map)),
        },
        "candidate_contract": {
            "version": CANDIDATE_CONTRACT_VERSION,
            "profile": CANDIDATE_PROFILE,
            "required_sources": list(ROUTES),
            "enabled_sources": list(ROUTES),
            "candidate_union_top_k": len(release.documents),
        },
        "runtime_fingerprint": fingerprint,
        "storage": {
            "output_path": output_relative,
            "qdrant_prefix": prefix,
            "qdrant_collection": collection,
            "metadata_sqlite": f"{output_relative}/storage/metadata.sqlite3",
            "bm25_sqlite": f"{output_relative}/storage/bm25.sqlite3",
            "refuse_existing_qdrant_collection": True,
            "delete_or_overwrite_existing_collection": False,
        },
        "cost_envelope": {
            "dense_document_requests": dense_doc_requests,
            "dense_query_requests": len(release.queries),
            "sparse_document_requests": len(release.documents),
            "sparse_query_requests": len(release.queries),
            "document_texts": len(release.documents),
            "query_texts": len(release.queries),
            "judge_llm_requests": 0,
            "automatic_retries": 0,
            "monetary_upper_bound": None,
        },
        "code": {
            "linkrag_eval": _git_state(repo_root),
            "dirty_dev_run_allowed": True,
            "dirty_run_not_sealable_as_formal_snapshot": True,
        },
    }


def prepare_run(
    *,
    repo_root: Path,
    release_root: Path,
    output_root: Path,
    run_id: str,
    dataset_id: int,
    settings: EvalSettings,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    release_root = release_root.resolve()
    output_root = output_root.resolve()
    for path in (release_root, output_root):
        if not path.is_relative_to(repo_root):
            raise RuntimeError(f"路径必须位于仓库内：{path}")
    if output_root.exists():
        raise RuntimeError(f"运行目录已存在，拒绝覆盖：{output_root}")
    plan = build_run_plan(
        repo_root=repo_root,
        release_root=release_root,
        output_root=output_root,
        run_id=run_id,
        dataset_id=dataset_id,
        settings=settings,
    )
    output_root.mkdir(parents=True, mode=0o700)
    output_root.chmod(0o700)
    storage_root = output_root / "storage"
    storage_root.mkdir(mode=0o700)
    storage_root.chmod(0o700)
    write_json(output_root / "plan.json", plan)
    plan_sha256 = sha256_file(output_root / "plan.json")
    (output_root / "plan.sha256").write_text(
        f"{plan_sha256}  plan.json\n", encoding="utf-8"
    )
    (output_root / "plan.sha256").chmod(0o400)
    write_json(
        output_root / "run_state.json",
        {
            "run_id": run_id,
            "state": "PREPARED",
            "updated_at_local": now_iso(),
            "plan_sha256": plan_sha256,
            "execution_attempts": 0,
            "gate_a_executed": False,
            "gate_b_executed": False,
        },
    )
    return {
        "status": "PREPARED",
        "run_id": run_id,
        "plan_path": str(output_root / "plan.json"),
        "plan_sha256": plan_sha256,
        "qdrant_collection": plan["storage"]["qdrant_collection"],
        "cost_envelope": plan["cost_envelope"],
        "confirmation_token": EXECUTION_CONFIRMATION,
    }


def verify_prepared_plan(repo_root: Path, plan_path: Path) -> tuple[dict[str, Any], Path]:
    repo_root = repo_root.resolve()
    plan_path = plan_path.resolve()
    if not plan_path.is_relative_to(repo_root):
        raise RuntimeError("plan 必须位于仓库内")
    output_root = plan_path.parent
    receipt = output_root / "plan.sha256"
    state_path = output_root / "run_state.json"
    if not receipt.is_file() or not state_path.is_file():
        raise RuntimeError("prepared plan 缺少回执或状态文件")
    recorded = receipt.read_text(encoding="utf-8").split()[0]
    if sha256_file(plan_path) != recorded:
        raise RuntimeError("prepared plan hash 不匹配")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if plan.get("plan_version") != ROUTE_EVIDENCE_VERSION:
        raise RuntimeError("prepared plan 版本不符")
    if plan.get("state") != "PREPARED" or state.get("state") != "PREPARED":
        raise RuntimeError("prepared plan 已执行或状态异常，拒绝原地重试")
    if state.get("execution_attempts") != 0:
        raise RuntimeError("prepared plan 已有执行尝试，拒绝原地重试")
    expected_output = (repo_root / plan["storage"]["output_path"]).resolve()
    if expected_output != output_root:
        raise RuntimeError("prepared plan output 路径不匹配")
    return plan, output_root


def ensure_method_view_safe(rows: Sequence[Mapping[str, Any]]) -> None:
    def walk(value: Any, location: str) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if key in METHOD_VIEW_FORBIDDEN_FIELDS:
                    raise RuntimeError(f"method_view 含禁止字段：{location}.{key}")
                walk(item, f"{location}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{location}[{index}]")

    for index, row in enumerate(rows):
        walk(row, f"row[{index}]")


def serialize_candidate_response(
    *,
    query_uid: str,
    response: Any,
    expected_chunk_ids: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """把 RecallResponse 转为不含评价字段的候选行，并验证三路闭门契约。"""

    if response.failed_sources:
        raise RuntimeError(f"三路召回存在失败来源：{response.failed_sources}")
    route_hits = response.route_hits or {}
    if set(route_hits) != set(ROUTES):
        raise RuntimeError(f"route_hits 路集合不符：{sorted(route_hits)}")

    route_maps: dict[str, dict[str, dict[str, Any]]] = {}
    for route in ROUTES:
        seen: set[str] = set()
        route_map: dict[str, dict[str, Any]] = {}
        for rank, hit in enumerate(route_hits[route], start=1):
            chunk_id = str(hit.chunk_id)
            if chunk_id in seen:
                raise RuntimeError(f"{query_uid}/{route} 出现重复 chunk_id")
            if chunk_id not in expected_chunk_ids:
                raise RuntimeError(f"{query_uid}/{route} 命中非本 release chunk")
            score = float(hit.score)
            if not math.isfinite(score):
                raise RuntimeError(f"{query_uid}/{route} score 非有限数")
            seen.add(chunk_id)
            route_map[chunk_id] = {"retrieved": True, "rank": rank, "raw_score": score}
        route_maps[route] = route_map

    rows: list[dict[str, Any]] = []
    seen_candidates: set[str] = set()
    for rank, hit in enumerate(response.candidate_hits, start=1):
        chunk_id = str(hit.chunk_id)
        if chunk_id in seen_candidates:
            raise RuntimeError(f"{query_uid} candidate_hits 出现重复 chunk_id")
        if chunk_id not in expected_chunk_ids:
            raise RuntimeError(f"{query_uid} candidate_hits 含非本 release chunk")
        fused_score = float(hit.fused_score)
        if not math.isfinite(fused_score):
            raise RuntimeError(f"{query_uid} fused_score 非有限数")
        seen_candidates.add(chunk_id)
        rows.append(
            {
                "query_uid": query_uid,
                "candidate_rank": rank,
                "chunk_id": chunk_id,
                "doc_id": int(hit.doc_id),
                "dataset_id": int(hit.dataset_id),
                "fused_score": fused_score,
                "route_evidence": {
                    route: route_maps[route].get(
                        chunk_id, {"retrieved": False, "rank": None, "raw_score": None}
                    )
                    for route in ROUTES
                },
            }
        )
    route_union = set().union(*(set(route_map) for route_map in route_maps.values()))
    if seen_candidates != route_union:
        raise RuntimeError("candidate_hits 与逐路命中并集不一致")
    ensure_method_view_safe(rows)
    summary = {
        "query_uid": query_uid,
        "elapsed_ms": int(response.elapsed_ms),
        "candidate_count": len(rows),
        "per_source_counts": {route: len(route_maps[route]) for route in ROUTES},
        "failed_sources": [],
    }
    return rows, summary


def build_views(
    *,
    release: InternalV6DevRelease,
    dataset_id: int,
    candidate_rows: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    query_map, chunk_map = build_identity_maps(release, dataset_id=dataset_id)
    method_queries = [
        {
            "query_uid": query_map[row["source_query_id"]],
            "dataset_ids": [dataset_id],
            "query_text": row["query_text_local"],
            "query_sha256": row["query_sha256"],
        }
        for row in release.queries
    ]
    method_chunks = [
        {
            **chunk_map[row["source_chunk_id"]],
            "content": row["document_text_local"],
            "content_sha256": row["content_sha256"],
        }
        for row in release.documents
    ]
    ensure_method_view_safe(method_queries)
    ensure_method_view_safe(method_chunks)
    ensure_method_view_safe(list(candidate_rows))

    candidate_by_unit = {
        (str(row["query_uid"]), str(row["chunk_id"])): row for row in candidate_rows
    }
    relations = []
    for row in release.evidence:
        query_uid = query_map[row["source_query_id"]]
        mapping = chunk_map[row["source_chunk_id"]]
        candidate = candidate_by_unit.get((query_uid, mapping["chunk_id"]))
        relations.append(
            {
                "query_uid": query_uid,
                "chunk_id": mapping["chunk_id"],
                "source_query_id": row["source_query_id"],
                "source_chunk_id": row["source_chunk_id"],
                "source_relevance_label": row["source_relevance_label"],
                "target_equivalence_group_id": row["target_equivalence_group_id"],
                "target_relation": row["target_relation"],
                "conflict_type": row["conflict_type"],
                "adjudicability": row["adjudicability"],
                "evidence_locator_local": row["evidence_locator_local"],
                "review_status": row["review_status"],
                "handbook_version": row["handbook_version"],
                "candidate_pool_member": candidate is not None,
                "candidate_rank": candidate["candidate_rank"] if candidate else None,
                "fused_score": candidate["fused_score"] if candidate else None,
                "route_evidence": (
                    candidate["route_evidence"]
                    if candidate
                    else {
                        route: {"retrieved": False, "rank": None, "raw_score": None}
                        for route in ROUTES
                    }
                ),
            }
        )

    query_by_family = {
        row["query_family_id"]: query_map[row["source_query_id"]] for row in release.queries
    }
    families = [
        {
            "query_uid": query_by_family[row["query_family_id"]],
            **row,
        }
        for row in release.families
    ]
    return {
        "method_queries": method_queries,
        "method_chunks": method_chunks,
        "method_candidates": [dict(row) for row in candidate_rows],
        "evaluation_relations": relations,
        "evaluation_families": families,
    }


def _runtime_matches_plan(settings: EvalSettings, plan: Mapping[str, Any]) -> None:
    validate_research_runtime(settings)
    current = _redacted_runtime_fingerprint(settings)
    if canonical_json(current) != canonical_json(plan["runtime_fingerprint"]):
        raise RuntimeError("当前脱敏运行配置与 prepared plan 不一致")


async def _qdrant_collection_exists(settings: EvalSettings, collection: str) -> bool:
    from qdrant_client import AsyncQdrantClient

    client = AsyncQdrantClient(url=settings.qdrant_host, api_key=None)
    try:
        return bool(await client.collection_exists(collection))
    finally:
        await client.close()


def _build_zero_retry_encoders(settings: EvalSettings) -> tuple[Any, Any]:
    from linkrag_eval.llm.dense_client import OpenAIDenseEmbedder
    from linkrag_eval.llm.sparse_client import ArkSparseEncoder

    dense = OpenAIDenseEmbedder(
        api_key=settings.embed_api_key,
        model=settings.embed_model,
        base_url=settings.embed_base_url,
        dim=settings.embed_dim,
        batch_size=settings.embed_batch_size,
        concurrency=settings.embed_concurrency,
        timeout_ms=settings.embed_timeout_ms,
        max_retries=0,
    )
    sparse = ArkSparseEncoder(
        api_key=settings.sparse_api_key,
        model=settings.sparse_model,
        base_url=settings.sparse_base_url,
        top_k=settings.sparse_top_k,
        min_weight=settings.sparse_min_weight,
        timeout_ms=settings.sparse_timeout_ms,
        max_retries=0,
        concurrency=settings.sparse_concurrency,
    )
    return dense, sparse


def _write_run_state(output_root: Path, plan: Mapping[str, Any], state: str, **extra: Any) -> None:
    write_json(
        output_root / "run_state.json",
        {
            "run_id": plan["run_id"],
            "state": state,
            "updated_at_local": now_iso(),
            "plan_sha256": sha256_file(output_root / "plan.json"),
            "execution_attempts": 1,
            "gate_a_executed": False,
            "gate_b_executed": False,
            **extra,
        },
    )


def _checkpoint_sqlite(path: Path) -> None:
    if not path.is_file():
        return
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def _manifest_files(output_root: Path) -> list[dict[str, Any]]:
    excluded = {"manifest.json", "manifest.sha256", "plan.json", "plan.sha256", "run_state.json"}
    rows = []
    for path in sorted(output_root.rglob("*")):
        if (
            not path.is_file()
            or path.name in excluded
            or path.name.endswith(("-shm", "-wal", "-journal"))
        ):
            continue
        rows.append(
            {
                "path": path.relative_to(output_root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return rows


async def execute_run(
    *,
    repo_root: Path,
    plan_path: Path,
    confirmation: str,
    settings: EvalSettings,
    progress: Any | None = None,
) -> dict[str, Any]:
    """执行一次 Dev 三路证据运行；没有自动重试，也不清理已写远端状态。"""

    if confirmation != EXECUTION_CONFIRMATION:
        raise RuntimeError("缺少精确执行确认 token")
    plan, output_root = verify_prepared_plan(repo_root, plan_path)
    _runtime_matches_plan(settings, plan)
    release_root = (repo_root.resolve() / plan["input"]["release_path"]).resolve()
    release = verify_dev_release(release_root)
    if release.manifest_sha256 != plan["input"]["release_manifest_sha256"]:
        raise RuntimeError("prepared plan 绑定的 release 已变化")
    dataset_id = int(plan["identity"]["dataset_id"])
    query_map, chunk_map = build_identity_maps(release, dataset_id=dataset_id)
    if sha256_text(canonical_json(query_map)) != plan["identity"]["query_map_sha256"]:
        raise RuntimeError("prepared query identity map 漂移")
    if sha256_text(canonical_json(chunk_map)) != plan["identity"]["chunk_map_sha256"]:
        raise RuntimeError("prepared chunk identity map 漂移")

    collection = plan["storage"]["qdrant_collection"]
    storage_root = output_root / "storage"
    if not storage_root.is_dir():
        raise RuntimeError("prepared plan 缺少本地隔离 storage 目录")
    unexpected_storage = sorted(path.name for path in storage_root.iterdir())
    if unexpected_storage:
        raise RuntimeError(
            f"本地隔离 storage 目录非空，拒绝覆盖：{unexpected_storage}"
        )
    metadata_path = storage_root / "metadata.sqlite3"
    bm25_path = storage_root / "bm25.sqlite3"
    for path in (metadata_path, bm25_path):
        if path.exists():
            raise RuntimeError(f"本地隔离存储已存在，拒绝覆盖：{path}")

    # 从第一次远端探测开始就计为唯一执行尝试。即使仅在 collection existence check
    # 处失败，也必须重新 prepare 新 run-id，不能让同一计划回到 PREPARED 后原地重跑。
    _write_run_state(output_root, plan, "RUNNING", started_at_local=now_iso())

    dense = None
    sparse = None
    close_engines = None
    try:
        if await _qdrant_collection_exists(settings, collection):
            raise RuntimeError(f"隔离 Qdrant collection 已存在，拒绝覆盖：{collection}")

        from linkrag_eval.compute.rag_adapter import RagProductComputer
        from linkrag_eval.retrieval.recall_adapter import execute_candidate_contract_once
        from linkrag_eval.retrieval.recall_factory import build_eval_recall_pipeline
        from linkrag_eval.store.corpus_repo import EvalCorpusRepo
        from linkrag_eval.store.engine import close_eval_engines
        from linkrag_eval.store.indexer import EvalPassage, EvalVectorIndexer
        from linkrag_eval.store.vector_store import build_eval_vector_store

        close_engines = close_eval_engines
        run_settings = settings.model_copy(
            update={
                "qdrant_prefix": plan["storage"]["qdrant_prefix"],
                "bm25_mode": "sqlite_fts5",
                "bm25_sqlite_path": str(bm25_path),
                "db_url": f"sqlite+aiosqlite:///{metadata_path}",
            }
        )
        dense, sparse = _build_zero_retry_encoders(run_settings)
        computer = RagProductComputer(dense_encoder=dense, sparse_encoder=sparse)
        repo = EvalCorpusRepo(url=run_settings.db_url)
        await repo.init_schema()
        await repo.register_dataset(
            dataset_id,
            name=f"internal_v6_dev_{plan['run_id']}",
            source_type="synth",
            domain="robust_fusion_calibration",
            genre="synthetic_single_passage",
            ingestion_ref=release.manifest_sha256,
            note="Dev-only; NOT_ELIGIBLE for Gate A/B",
        )
        indexer = EvalVectorIndexer(
            computer=computer,
            vector_store=build_eval_vector_store(settings=run_settings),
            corpus_repo=repo,
            with_sparse=True,
            bm25_mode="sqlite_fts5",
            run_id=plan["run_id"],
        )
        passages = [
            EvalPassage(
                source_passage_id=row["source_chunk_id"],
                content=row["document_text_local"],
                doc_id=int(chunk_map[row["source_chunk_id"]]["doc_id"]),
                ordinal=0,
            )
            for row in release.documents
        ]
        batch_size = int(run_settings.embed_batch_size)
        indexed = 0
        for start in range(0, len(passages), batch_size):
            batch = passages[start : start + batch_size]
            indexed += await indexer.index_passages(dataset_id, batch)
            if progress:
                progress(f"ingest {indexed}/{len(passages)}")
        if indexed != len(passages):
            raise RuntimeError(f"索引计数不符：{indexed} != {len(passages)}")
        stored = await repo.fetch_chunks_for_datasets([dataset_id])
        if len(stored) != len(passages):
            raise RuntimeError("隔离 metadata SQLite 的 Chunk 数不符")
        expected_hashes = {
            chunk_map[row["source_chunk_id"]]["chunk_id"]: row["content_sha256"]
            for row in release.documents
        }
        if {row.chunk_id: row.content_hash for row in stored} != expected_hashes:
            raise RuntimeError("隔离 metadata SQLite 的 Chunk/hash 不符")

        pipeline = build_eval_recall_pipeline(
            settings=run_settings,
            dense_encoder=dense,
            sparse_encoder=sparse,
            strict=True,
        )
        expected_chunk_ids = {str(value["chunk_id"]) for value in chunk_map.values()}
        all_candidate_rows: list[dict[str, Any]] = []
        query_summaries: list[dict[str, Any]] = []
        partial_events = output_root / "runtime" / "partial_query_events.jsonl"
        partial_events.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        query_rows = sorted(release.queries, key=lambda row: row["source_query_id"])
        for index, query in enumerate(query_rows, start=1):
            query_uid = query_map[query["source_query_id"]]
            response = await execute_candidate_contract_once(
                pipeline,
                query=query["query_text_local"],
                user_id=run_settings.user_id,
                dataset_ids=[dataset_id],
                top_k=len(release.documents),
                bm25_top_k=run_settings.recall_bm25_top_k,
                dense_top_k=run_settings.recall_dense_top_k,
                sparse_top_k=run_settings.recall_sparse_top_k,
                dense_score_threshold=run_settings.recall_dense_score_threshold,
                sparse_score_threshold=run_settings.recall_sparse_score_threshold,
                enabled_sources=list(ROUTES),
                required_sources=list(ROUTES),
                fusion_weights={
                    "dense": run_settings.recall_dense_weight,
                    "sparse": run_settings.recall_sparse_weight,
                    "bm25": run_settings.recall_bm25_weight,
                },
                candidate_contract_version=CANDIDATE_CONTRACT_VERSION,
                candidate_profile=CANDIDATE_PROFILE,
            )
            rows, summary = serialize_candidate_response(
                query_uid=query_uid,
                response=response,
                expected_chunk_ids=expected_chunk_ids,
            )
            all_candidate_rows.extend(rows)
            query_summaries.append(summary)
            with partial_events.open("a", encoding="utf-8") as handle:
                handle.write(
                    canonical_json(
                        {
                            "query_index": index,
                            "query_uid": query_uid,
                            "status": "COMPLETED",
                            "candidate_count": len(rows),
                        }
                    )
                    + "\n"
                )
            partial_events.chmod(0o600)
            if progress:
                progress(f"recall {index}/{len(query_rows)} candidates={len(rows)}")

        views = build_views(
            release=release,
            dataset_id=dataset_id,
            candidate_rows=all_candidate_rows,
        )
        write_jsonl(output_root / "method_view" / "queries.jsonl", views["method_queries"])
        write_jsonl(output_root / "method_view" / "chunks.jsonl", views["method_chunks"])
        write_jsonl(
            output_root / "method_view" / "candidates.jsonl", views["method_candidates"]
        )
        write_jsonl(
            output_root / "evaluation_view" / "relations.jsonl",
            views["evaluation_relations"],
        )
        write_jsonl(
            output_root / "evaluation_view" / "families.jsonl",
            views["evaluation_families"],
        )
        write_jsonl(output_root / "runtime" / "query_summaries.jsonl", query_summaries)
        write_json(
            output_root / "runtime" / "config_snapshot.json",
            {
                "runtime_fingerprint": plan["runtime_fingerprint"],
                "candidate_contract": plan["candidate_contract"],
                "qdrant_collection": collection,
                "secrets_persisted": False,
            },
        )

        target_relations = [
            row for row in views["evaluation_relations"] if row["source_relevance_label"] == "relevant_gold"
        ]
        target_union_count = sum(bool(row["candidate_pool_member"]) for row in target_relations)
        labeled_union_count = sum(
            bool(row["candidate_pool_member"]) for row in views["evaluation_relations"]
        )
        summary = {
            "query_count": len(query_rows),
            "document_chunk_count": len(release.documents),
            "indexed_chunk_count": indexed,
            "candidate_row_count": len(all_candidate_rows),
            "labeled_relation_count": len(views["evaluation_relations"]),
            "labeled_candidate_union_count": labeled_union_count,
            "target_count": len(target_relations),
            "target_candidate_union_count": target_union_count,
            "queries_with_failed_sources": 0,
            "route_query_counts": {
                route: sum(summary["per_source_counts"][route] > 0 for summary in query_summaries)
                for route in ROUTES
            },
        }
        write_json(output_root / "runtime" / "run_summary.json", summary)
        readme = (
            "# Internal Stress v6 Dev 三路证据 v1\n\n"
            "本制品只服务 Dev 构念、检索和测量校准；它不是正式 P4-02 快照，"
            "不具备 Gate A/B 资格。`method_view/` 不含人工关系、冲突类型、来源配额或 family "
            "字段；`evaluation_view/` 只供评价和审计。所有向量与分数均由当前冻结的 Dense、"
            "Learned Sparse 和 SQLite FTS5 路径重算，未复制历史分数。\n"
        )
        (output_root / "README.md").write_text(readme, encoding="utf-8")
        (output_root / "README.md").chmod(0o600)

        await close_eval_engines()
        close_engines = None
        _checkpoint_sqlite(metadata_path)
        _checkpoint_sqlite(bm25_path)
        files = _manifest_files(output_root)
        content_root_sha256 = sha256_text(canonical_json(files))
        manifest = {
            "evidence_version": ROUTE_EVIDENCE_VERSION,
            "generated_at_local": now_iso(),
            "run_id": plan["run_id"],
            "plan_sha256": sha256_file(output_root / "plan.json"),
            "input_release_version": release.manifest["release_version"],
            "input_release_manifest_sha256": release.manifest_sha256,
            "split_role": "internal-v6-dev",
            "origin": "synthetic",
            "formal_p4_02_snapshot": False,
            "retrieval_route_evidence_ready": True,
            "method_evaluation_views_physically_separated": True,
            "automatic_retries": 0,
            "gate_eligibility": "NOT_ELIGIBLE",
            "gate_a_executed": False,
            "gate_b_executed": False,
            "candidate_contract": plan["candidate_contract"],
            "runtime_fingerprint": plan["runtime_fingerprint"],
            "qdrant_collection": collection,
            "summary": summary,
            "files": files,
            "content_root_sha256": content_root_sha256,
        }
        write_json(output_root / "manifest.json", manifest)
        manifest_sha256 = sha256_file(output_root / "manifest.json")
        (output_root / "manifest.sha256").write_text(
            f"{manifest_sha256}  manifest.json\n", encoding="utf-8"
        )
        (output_root / "manifest.sha256").chmod(0o400)
        _write_run_state(
            output_root,
            plan,
            "COMPLETED",
            completed_at_local=now_iso(),
            manifest_sha256=manifest_sha256,
            content_root_sha256=content_root_sha256,
            qdrant_collection=collection,
        )
        return {
            "status": "COMPLETED_DEV_ONLY",
            "run_id": plan["run_id"],
            "manifest_path": str(output_root / "manifest.json"),
            "manifest_sha256": manifest_sha256,
            "content_root_sha256": content_root_sha256,
            "qdrant_collection": collection,
            "summary": summary,
            "gate_eligibility": "NOT_ELIGIBLE",
        }
    except Exception as exc:
        _write_run_state(
            output_root,
            plan,
            "FAILED_NO_AUTORETRY",
            failed_at_local=now_iso(),
            error_type=type(exc).__name__,
            error_message=str(exc)[:1000],
            qdrant_collection=collection,
            cleanup_performed=False,
        )
        raise
    finally:
        if close_engines is not None:
            await close_engines()
        for encoder in (dense, sparse):
            closer = getattr(encoder, "aclose", None)
            if closer is not None:
                await closer()
