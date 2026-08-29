#!/usr/bin/env python3
"""Prepare or verify the P2-01 Internal-v6 Dev similarity calibration artifact."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import platform
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from linkrag_eval.robust_fusion.similarity import vector_float32_sha256
from linkrag_eval.robust_fusion.similarity_dev_calibration import (
    AUDIT_MODEL_ID,
    AUDIT_REVISION,
    CALIBRATION_VERSION,
    MAIN_MODEL_ID,
    MAIN_REVISION,
    QUALIFICATION_SHA256,
    add_model_agreement,
    assign_length_strata,
    build_provisional_calibration,
    build_reference_sets,
    canonical_json,
    human_audit_rules,
    load_frozen_dev_inputs,
    normalize_similarity_text,
    score_candidates,
    select_blind_human_sample,
    sha256_file,
    sha256_text,
    verify_encoder_roles,
    write_json,
    write_jsonl,
)

DEFAULT_ROUTE_ROOT = Path(
    "runs/robust_fusion/internal_v6_route_evidence_v1/"
    "internal-v6-dev-route-evidence-v5-20260829"
)
DEFAULT_RELEASE_ROOT = Path(
    "data/robust_fusion/internal_stress_v6/dev/releases/adjudicated_synthetic_v1"
)
DEFAULT_QUALIFICATION_ROOT = Path(
    "runs/robust_fusion/contracts/similarity-encoder-qualification-v3"
)
DEFAULT_MODEL_CACHE = Path("data/robust_fusion/models/huggingface")
DEFAULT_OUTPUT_ROOT = Path(
    "runs/robust_fusion/similarity_dev_calibration_v1/"
    "internal-v6-dev-similarity-calibration-v1-20260829"
)
STATUS = "AWAITING_HUMAN_SUBMISSIONS"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def resolve_in_repo(repo_root: Path, path: Path) -> Path:
    resolved = (path if path.is_absolute() else repo_root / path).resolve()
    if not resolved.is_relative_to(repo_root):
        raise RuntimeError(f"path must remain inside repository: {resolved}")
    return resolved


def git_output(repo_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo_root, check=True, capture_output=True, text=True
    ).stdout.strip()


def model_snapshot(cache_root: Path, model_id: str, revision: str) -> Path:
    path = cache_root / ("models--" + model_id.replace("/", "--")) / "snapshots" / revision
    if not path.is_dir():
        raise RuntimeError(f"pinned local model snapshot missing: {path}")
    return path


def load_qualification(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest_path = root / "manifest.json"
    if sha256_file(manifest_path) != QUALIFICATION_SHA256:
        raise RuntimeError("similarity encoder qualification manifest drift")
    receipt = (root / "manifest.sha256").read_text(encoding="utf-8").split()[0]
    if receipt != QUALIFICATION_SHA256:
        raise RuntimeError("similarity encoder qualification receipt drift")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_role = {row["role"]: row for row in manifest["models"]}
    main = by_role.get("main_similarity_encoder", {})
    audit = by_role.get("independent_audit_encoder", {})
    verify_encoder_roles(main, audit)
    if manifest.get("status") != "QUALIFIED_PRESELECTED_PENDING_DEV_CALIBRATION":
        raise RuntimeError("encoder qualification status is not eligible for Dev calibration")
    return manifest, main, audit


def encoder_provenance(model_spec: dict[str, Any]) -> dict[str, Any]:
    """Keep the model, tokenizer, config, and weight identity needed for replay."""
    keys = (
        "role",
        "model_id",
        "revision",
        "tokenizer_id",
        "tokenizer_revision",
        "architecture_family",
        "dimension",
        "max_tokens",
        "input_prefix",
        "input_contract",
        "pooling",
        "output_layer",
        "l2_normalize",
        "stored_dtype",
        "cosine_accumulation_dtype",
        "metadata_files",
        "weight_files_verified",
    )
    return {key: model_spec[key] for key in keys}


def encode_model(
    model_spec: dict[str, Any], cache_root: Path, ordered_chunks: list[dict[str, Any]]
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    import torch
    from sentence_transformers import SentenceTransformer

    torch.manual_seed(0)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    snapshot = model_snapshot(cache_root, model_spec["model_id"], model_spec["revision"])
    model = SentenceTransformer(str(snapshot), device="cpu", trust_remote_code=False)
    if model.max_seq_length != model_spec["max_tokens"]:
        raise RuntimeError(f"model max length drift: {model_spec['model_id']}")
    model.tokenizer.truncation_side = "right"
    normalized = [
        model_spec["input_prefix"] + normalize_similarity_text(str(row["content"]))
        for row in ordered_chunks
    ]
    token_counts = [
        len(model.tokenizer(text, add_special_tokens=True, truncation=False)["input_ids"])
        for text in normalized
    ]
    vectors = model.encode(
        normalized,
        batch_size=32,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).astype("<f4", copy=False)
    if vectors.shape != (len(ordered_chunks), model_spec["dimension"]):
        raise RuntimeError(f"encoder output shape drift: {model_spec['model_id']}:{vectors.shape}")
    metadata: list[dict[str, Any]] = []
    for row, text, count, vector in zip(ordered_chunks, normalized, token_counts, vectors):
        metadata.append(
            {
                "chunk_id": row["chunk_id"],
                "raw_content_sha256": row["content_sha256"],
                "normalized_prefixed_input_sha256": sha256_text(text),
                "untruncated_token_count": count,
                "max_tokens": model_spec["max_tokens"],
                "truncation_side": "right",
                "was_truncated": count > model_spec["max_tokens"],
                "vector_float32_sha256": vector_float32_sha256(
                    vector, expected_dim=model_spec["dimension"]
                ),
            }
        )
    return vectors, metadata


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    path.chmod(0o600)


def deterministic_order(rows: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: hashlib.sha256(f"{role}:{row['audit_id']}".encode()).hexdigest(),
    )


def materialize_human_packages(
    output_root: Path,
    sample: list[dict[str, Any]],
    chunks_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    human_root = output_root / "human_audit"
    facilitator_root = human_root / "facilitator"
    facilitator_root.mkdir(parents=True, mode=0o700)
    facilitator_root.chmod(0o700)
    registry: list[dict[str, Any]] = []
    for row in sample:
        audit_id = "RF-SIM-" + sha256_text(
            f"{CALIBRATION_VERSION}:{row['query_uid']}:{row['candidate_chunk_id']}"
        )[:12].upper()
        registry.append({"audit_id": audit_id, **row})
    write_jsonl(facilitator_root / "sample_registry.jsonl", registry)

    instruction = (
        "独立完成本目录 pairs.csv 的全部 24 对文本：只判断两段文本的语义接近程度，"
        "不要判断哪段正确，也不要与另一位研究员讨论。将 submission_template.csv 复制为 "
        "submission.csv，逐行填写 1–5 分、confidence 与 uncertain；uncertain=yes 时 note 必填。"
        "不要改 audit_id 或表头。1=不同主题/实体/事实槽；2=同领域但实体或事实槽不同；"
        "3=同实体/主题且部分事实槽或条件重合；4=同一事实槽且语义高度接近（允许关键事实/条件不同）；"
        "5=近乎等价或紧密改写。"
    )
    package_records: list[dict[str, Any]] = []
    for role in ("A", "B"):
        role_root = human_root / f"annotator_{role.lower()}"
        role_root.mkdir(parents=True, mode=0o700)
        role_root.chmod(0o700)
        pairs: list[dict[str, Any]] = []
        templates: list[dict[str, Any]] = []
        for item in deterministic_order(registry, role):
            reference = chunks_by_id[item["argmax_reference_local_chunk_id"]]["content"]
            candidate = chunks_by_id[item["candidate_chunk_id"]]["content"]
            swap = int(sha256_text(f"{role}:swap:{item['audit_id']}")[-1], 16) % 2 == 1
            pairs.append(
                {
                    "audit_id": item["audit_id"],
                    "text_1": candidate if swap else reference,
                    "text_2": reference if swap else candidate,
                }
            )
            templates.append(
                {
                    "audit_id": item["audit_id"],
                    "human_similarity_ordinal": "",
                    "confidence": "",
                    "uncertain": "",
                    "note": "",
                }
            )
        write_csv(role_root / "pairs.csv", pairs, ["audit_id", "text_1", "text_2"])
        write_csv(
            role_root / "submission_template.csv",
            templates,
            ["audit_id", "human_similarity_ordinal", "confidence", "uncertain", "note"],
        )
        (role_root / "README.txt").write_text(instruction + "\n", encoding="utf-8")
        (role_root / "README.txt").chmod(0o600)
        manifest = {
            "calibration_version": CALIBRATION_VERSION,
            "role": role,
            "status": STATUS,
            "row_count": len(pairs),
            "contains_answer_key": False,
            "contains_model_scores": False,
            "contains_relation_labels": False,
            "files": [
                {"path": name, "sha256": sha256_file(role_root / name)}
                for name in ("README.txt", "pairs.csv", "submission_template.csv")
            ],
        }
        write_json(role_root / "package_manifest.json", manifest)
        (role_root / "package_manifest.sha256").write_text(
            f"{sha256_file(role_root / 'package_manifest.json')}  package_manifest.json\n",
            encoding="utf-8",
        )
        (role_root / "package_manifest.sha256").chmod(0o400)
        package_records.append(
            {
                "role": role,
                "relative_path": role_root.relative_to(output_root).as_posix(),
                "row_count": len(pairs),
                "package_manifest_sha256": sha256_file(role_root / "package_manifest.json"),
            }
        )
    return package_records


def grouped_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    dimensions = ("target_relation", "conflict_type", "length_stratum", "candidate_origin")
    output: dict[str, Any] = {}
    for dimension in dimensions:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[str(row[dimension])].append(row)
        output[dimension] = {
            key: {
                "count": len(items),
                "main_mean": float(np.mean([item["main_similarity"] for item in items])),
                "main_min": min(item["main_similarity"] for item in items),
                "main_max": max(item["main_similarity"] for item in items),
                "audit_mean": float(np.mean([item["audit_similarity"] for item in items])),
                "main_truncated_count": sum(bool(item["main_was_truncated"]) for item in items),
                "audit_truncated_count": sum(bool(item["audit_was_truncated"]) for item in items),
            }
            for key, items in sorted(groups.items())
        }
    output["encoder_agreement_region"] = dict(
        sorted(Counter(row["encoder_agreement_region"] for row in rows).items())
    )
    return output


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    route_root = resolve_in_repo(repo_root, args.route_root)
    release_root = resolve_in_repo(repo_root, args.release_root)
    qualification_root = resolve_in_repo(repo_root, args.qualification_root)
    cache_root = resolve_in_repo(repo_root, args.model_cache)
    output_root = resolve_in_repo(repo_root, args.output_root)
    if output_root.exists():
        raise RuntimeError(f"refusing to overwrite calibration artifact: {output_root}")
    output_root.mkdir(parents=True, mode=0o700)
    output_root.chmod(0o700)

    dev = load_frozen_dev_inputs(route_root)
    _qualification, main_spec, audit_spec = load_qualification(qualification_root)
    release_manifest = release_root / "manifest.json"
    if sha256_file(release_manifest) != dev["manifest"]["input_release_manifest_sha256"]:
        raise RuntimeError("bound adjudicated release manifest drift")

    reference_sets, candidates = build_reference_sets(dev["chunks"], dev["relations"])
    ordered_chunks = sorted(dev["chunks"], key=lambda row: str(row["chunk_id"]))
    chunks_by_id = {str(row["chunk_id"]): row for row in ordered_chunks}
    main_vectors, main_meta = encode_model(main_spec, cache_root, ordered_chunks)
    audit_vectors, audit_meta = encode_model(audit_spec, cache_root, ordered_chunks)
    vector_dir = output_root / "vectors"
    vector_dir.mkdir(mode=0o700)
    np.save(vector_dir / "main.float32.npy", main_vectors, allow_pickle=False)
    np.save(vector_dir / "audit.float32.npy", audit_vectors, allow_pickle=False)
    (vector_dir / "main.float32.npy").chmod(0o600)
    (vector_dir / "audit.float32.npy").chmod(0o600)
    vector_index = [
        {"vector_row": index, "chunk_id": row["chunk_id"]}
        for index, row in enumerate(ordered_chunks)
    ]
    write_jsonl(vector_dir / "index.jsonl", vector_index)
    main_by_id = {row["chunk_id"]: main_vectors[index] for index, row in enumerate(ordered_chunks)}
    audit_by_id = {row["chunk_id"]: audit_vectors[index] for index, row in enumerate(ordered_chunks)}
    main_scores = score_candidates(
        reference_sets, candidates, main_by_id, expected_dim=main_spec["dimension"]
    )
    audit_scores = score_candidates(
        reference_sets, candidates, audit_by_id, expected_dim=audit_spec["dimension"]
    )
    audit_by_candidate = {row["candidate_chunk_id"]: row for row in audit_scores}
    main_meta_by_id = {row["chunk_id"]: row for row in main_meta}
    audit_meta_by_id = {row["chunk_id"]: row for row in audit_meta}
    candidate_source = {row["chunk_id"]: row for row in candidates}
    rows: list[dict[str, Any]] = []
    for row in main_scores:
        chunk_id = row["candidate_chunk_id"]
        audit_row = audit_by_candidate[chunk_id]
        source = candidate_source[chunk_id]
        main_similarity = row["max_cosine_similarity"]
        rows.append(
            {
                **{key: value for key, value in row.items() if key != "max_cosine_similarity"},
                "main_similarity": main_similarity,
                "audit_similarity": audit_row["max_cosine_similarity"],
                "audit_argmax_reference_id": audit_row["argmax_reference_id"],
                "audit_candidate_vector_sha256": audit_row["candidate_vector_sha256"],
                "main_untruncated_token_count": main_meta_by_id[chunk_id]["untruncated_token_count"],
                "audit_untruncated_token_count": audit_meta_by_id[chunk_id]["untruncated_token_count"],
                "main_was_truncated": main_meta_by_id[chunk_id]["was_truncated"],
                "audit_was_truncated": audit_meta_by_id[chunk_id]["was_truncated"],
                "candidate_origin": "synthetic",
                "source_system": "internal_v6_deepseek_synthetic_dev_double_reviewed",
                "dataset_id": 996601,
                "candidate_content_sha256": source["content_sha256"],
            }
        )
    token_counts = {row["chunk_id"]: row["untruncated_token_count"] for row in main_meta}
    length_rule = assign_length_strata(rows, token_counts)
    add_model_agreement(rows)
    provisional = build_provisional_calibration(rows)
    sample = select_blind_human_sample(rows)
    rules = human_audit_rules(len(sample))

    # Complete reference member provenance only after both vectors exist.
    reference_output: list[dict[str, Any]] = []
    for reference in reference_sets:
        copied = {key: value for key, value in reference.items() if key != "members"}
        copied["dataset_id"] = 996601
        copied["dataset_revision"] = dev["manifest"]["input_release_version"]
        copied["cohort_id"] = "internal-v6-dev"
        copied["split_role"] = "internal-v6-dev"
        copied["members"] = []
        for member in reference["members"]:
            chunk_id = member["local_chunk_id"]
            copied["members"].append(
                {
                    **{key: value for key, value in member.items() if key != "content"},
                    "normalized_input_sha256": main_meta_by_id[chunk_id][
                        "normalized_prefixed_input_sha256"
                    ],
                    "main_vector_sha256": main_meta_by_id[chunk_id]["vector_float32_sha256"],
                    "audit_vector_sha256": audit_meta_by_id[chunk_id]["vector_float32_sha256"],
                }
            )
        reference_output.append(copied)

    write_jsonl(output_root / "reference_sets.jsonl", reference_output)
    write_jsonl(output_root / "candidate_similarity.jsonl", rows)
    write_jsonl(output_root / "main_input_vectors.jsonl", main_meta)
    write_jsonl(output_root / "audit_input_vectors.jsonl", audit_meta)
    write_json(output_root / "length_stratification.json", length_rule)
    write_json(output_root / "stratified_summary.json", grouped_summary(rows))
    write_json(output_root / "provisional_calibration.json", provisional)
    write_json(output_root / "human_audit_rules.json", rules)
    packages = materialize_human_packages(output_root, sample, chunks_by_id)

    script_path = Path(__file__).resolve()
    module_path = repo_root / "src/linkrag_eval/robust_fusion/similarity_dev_calibration.py"
    primitive_path = repo_root / "src/linkrag_eval/robust_fusion/similarity.py"
    code = {
        "git_head": git_output(repo_root, "rev-parse", "HEAD"),
        "git_status_sha256": sha256_text(git_output(repo_root, "status", "--porcelain=v1")),
        "files": [
            {"path": path.relative_to(repo_root).as_posix(), "sha256": sha256_file(path)}
            for path in (script_path, module_path, primitive_path)
        ],
    }
    config = {
        "calibration_version": CALIBRATION_VERSION,
        "estimand": "S_qg(c)=max_h_in_A_qg cosine(z(c),z(h))",
        "reference_member_rule": "evaluation_view source_relevance_label=relevant_gold and target_relation=equivalent",
        "candidate_rule": "exclude relevant_gold self-reference; score equivalent/factual_conflict/other_incorrect",
        "main_encoder": encoder_provenance(main_spec),
        "audit_encoder": encoder_provenance(audit_spec),
        "runtime": {
            "python": platform.python_version(),
            "sentence_transformers": importlib.metadata.version("sentence-transformers"),
            "transformers": importlib.metadata.version("transformers"),
            "torch": importlib.metadata.version("torch"),
            "numpy": importlib.metadata.version("numpy"),
            "device": "cpu",
            "torch_num_threads": 1,
            "deterministic_algorithms": True,
        },
        "cosine": "float32 inputs; float64 accumulation; no score rounding",
        "length_stratification": length_rule,
        "sampling": "4 rows per target_relation x relative-length cell; within-cell lowest/highest encoder percentile gaps plus alternating extremes; all conflict types required",
        "rules_sha256": sha256_file(output_root / "human_audit_rules.json"),
    }
    write_json(output_root / "computation_config.json", config)
    status = {
        "calibration_version": CALIBRATION_VERSION,
        "status": STATUS,
        "automatic_part_complete": True,
        "formal_numeric_freeze_complete": False,
        "p2_01_complete": False,
        "p2_04_complete": False,
        "gate_a_executed": False,
        "gate_b_executed": False,
        "gate_a_authorized": False,
        "human_submission_count": 0,
        "required_human_submission_count": 2,
        "rows_per_researcher": len(sample),
        "generated_at_local": now_iso(),
    }
    write_json(output_root / "status.json", status)

    managed_files = sorted(
        path for path in output_root.rglob("*") if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"}
    )
    manifest = {
        "calibration_version": CALIBRATION_VERSION,
        "status": STATUS,
        "input_provenance": {
            "route_run_id": dev["manifest"]["run_id"],
            "route_manifest_sha256": sha256_file(route_root / "manifest.json"),
            "route_content_root_sha256": dev["manifest"]["content_root_sha256"],
            "adjudicated_release_manifest_sha256": sha256_file(release_manifest),
            "qualification_manifest_sha256": sha256_file(qualification_root / "manifest.json"),
        },
        "summary": {
            "reference_set_count": len(reference_output),
            "reference_member_count": sum(len(row["members"]) for row in reference_output),
            "scored_candidate_count": len(rows),
            "human_sample_count": len(sample),
            "relation_counts": dict(sorted(Counter(row["target_relation"] for row in rows).items())),
            "main_truncated_count": sum(row["main_was_truncated"] for row in rows),
            "audit_truncated_count": sum(row["audit_was_truncated"] for row in rows),
        },
        "encoders": {
            "main": {"model_id": MAIN_MODEL_ID, "revision": MAIN_REVISION},
            "independent_audit": {"model_id": AUDIT_MODEL_ID, "revision": AUDIT_REVISION},
        },
        "code": code,
        "computation_code_sha256": sha256_text(canonical_json(code)),
        "computation_config_sha256": sha256_file(output_root / "computation_config.json"),
        "human_packages": packages,
        "method_evaluation_views_physically_separated": True,
        "formal_numeric_freeze_complete": False,
        "gate_a_executed": False,
        "gate_b_executed": False,
        "gate_a_authorized": False,
        "files": [
            {
                "path": path.relative_to(output_root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in managed_files
        ],
    }
    write_json(output_root / "manifest.json", manifest)
    (output_root / "manifest.sha256").write_text(
        f"{sha256_file(output_root / 'manifest.json')}  manifest.json\n", encoding="utf-8"
    )
    (output_root / "manifest.sha256").chmod(0o400)
    return {
        "status": STATUS,
        "output_root": str(output_root),
        "manifest_sha256": sha256_file(output_root / "manifest.json"),
        "rows_per_researcher": len(sample),
    }


def verify(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    output_root = resolve_in_repo(repo_root, args.output_root)
    manifest_path = output_root / "manifest.json"
    manifest_sha = sha256_file(manifest_path)
    if (output_root / "manifest.sha256").read_text(encoding="utf-8").split()[0] != manifest_sha:
        raise RuntimeError("calibration manifest receipt mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for row in manifest["files"]:
        path = output_root / row["path"]
        if not path.is_file() or path.stat().st_size != row["size_bytes"] or sha256_file(path) != row["sha256"]:
            raise RuntimeError(f"calibration artifact file drift: {row['path']}")
    if manifest["status"] != STATUS or manifest["gate_a_authorized"]:
        raise RuntimeError("calibration artifact crossed its Dev-only boundary")
    index = [json.loads(line) for line in (output_root / "vectors/index.jsonl").read_text(encoding="utf-8").splitlines()]
    main = np.load(output_root / "vectors/main.float32.npy", allow_pickle=False)
    audit = np.load(output_root / "vectors/audit.float32.npy", allow_pickle=False)
    if main.shape != (len(index), 768) or audit.shape != (len(index), 512):
        raise RuntimeError("stored vector matrix shape mismatch")
    metadata = {
        "main": [json.loads(line) for line in (output_root / "main_input_vectors.jsonl").read_text(encoding="utf-8").splitlines()],
        "audit": [json.loads(line) for line in (output_root / "audit_input_vectors.jsonl").read_text(encoding="utf-8").splitlines()],
    }
    for name, vectors, expected_dim in (("main", main, 768), ("audit", audit, 512)):
        by_chunk = {row["chunk_id"]: row for row in metadata[name]}
        for row in index:
            actual = vector_float32_sha256(vectors[row["vector_row"]], expected_dim=expected_dim)
            if actual != by_chunk[row["chunk_id"]]["vector_float32_sha256"]:
                raise RuntimeError(f"stored vector hash mismatch: {name}:{row['chunk_id']}")
    for role in ("a", "b"):
        package = output_root / f"human_audit/annotator_{role}"
        forbidden = ("target_relation", "conflict_type", "main_similarity", "audit_similarity", "query_uid", "chunk_id")
        text = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.csv"))
        if any(token in text for token in forbidden):
            raise RuntimeError(f"human package leaks answer/model metadata: {role}")
        package_manifest = json.loads((package / "package_manifest.json").read_text(encoding="utf-8"))
        if package_manifest["contains_answer_key"] or package_manifest["row_count"] != 24:
            raise RuntimeError(f"human package contract failure: {role}")
    return {
        "status": "VERIFIED_AWAITING_HUMAN_SUBMISSIONS",
        "manifest_sha256": manifest_sha,
        "verified_file_count": len(manifest["files"]),
        "verified_vector_count": len(index),
        "rows_per_researcher": manifest["summary"]["human_sample_count"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    verify_parser = subparsers.add_parser("verify")
    for subparser in (prepare_parser, verify_parser):
        subparser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    prepare_parser.add_argument("--route-root", type=Path, default=DEFAULT_ROUTE_ROOT)
    prepare_parser.add_argument("--release-root", type=Path, default=DEFAULT_RELEASE_ROOT)
    prepare_parser.add_argument("--qualification-root", type=Path, default=DEFAULT_QUALIFICATION_ROOT)
    prepare_parser.add_argument("--model-cache", type=Path, default=DEFAULT_MODEL_CACHE)
    args = parser.parse_args()
    result = prepare(args) if args.command == "prepare" else verify(args)
    print(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
