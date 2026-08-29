#!/usr/bin/env python3
"""Execute frozen R2 encoders once and create four isolated blind packages."""

from __future__ import annotations

import csv
import json
import platform
import time
from pathlib import Path
from typing import Any

import numpy as np

from linkrag_eval.robust_fusion.r2_automatic_execution import (
    AUTOMATIC_EXECUTOR_ID,
    build_blind_packages,
    build_encoder_inputs,
    build_scored_candidate_frame,
    truncation_summary,
)
from linkrag_eval.robust_fusion.r2_measurement import (
    AUDIT_ENCODER,
    MAIN_ENCODER,
    build_candidate_rows,
    score_candidate_vectors,
)
from linkrag_eval.robust_fusion.similarity_dev_calibration import (
    sha256_file,
    write_json,
    write_jsonl,
)
from scripts.prepare_robust_fusion_r2_automatic_execution import (
    CODE_FILES,
    PREP_ROOT,
    QUALIFICATION_ROOT,
    REPO_ROOT,
    SOURCE_ROOT,
    SPEC,
)
from scripts.run_robust_fusion_r2_measurement import OUTPUT_ROOT, verify_preregistration
from scripts.run_robust_fusion_similarity_dev_calibration import (
    encode_model,
    encoder_provenance,
    load_qualification,
)

MODEL_CACHE = REPO_ROOT / "data/robust_fusion/models/huggingface"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
    path.chmod(0o600)


def verify_automatic_preparation() -> dict[str, Any]:
    verify_preregistration()
    receipt = json.loads((PREP_ROOT / "receipt.json").read_text(encoding="utf-8"))
    manifest_path = PREP_ROOT / "manifest.json"
    if sha256_file(manifest_path) != receipt["manifest_sha256"]:
        raise RuntimeError("R2 automatic preparation manifest drift")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    current = (str(SPEC.relative_to(REPO_ROOT)), *CODE_FILES)
    for relative, sealed in zip(current, manifest["snapshot_files"], strict=True):
        if sha256_file(REPO_ROOT / relative) != sealed["sha256"]:
            raise RuntimeError(f"R2 automatic implementation drift: {relative}")
    for sealed in manifest["source_lock"]:
        if sha256_file(REPO_ROOT / sealed["path"]) != sealed["sha256"]:
            raise RuntimeError("R2 formal source lock drift")
    return receipt


def _package_instruction(task: str) -> str:
    common = (
        "你是独立研究员。只处理本目录，不查看另一位研究员或另一任务的文件，不讨论答案。"
        "将 submission_template.csv 复制为 submission.csv，填写全部256行；不得修改表头或 audit_id。"
        "模型输出和构造过程不是真值；本包不含模型分数或答案键。"
    )
    if task == "relation":
        return common + (
            " valid_reference 与 unique_target_group 填 yes/no；target_relation 填 equivalent 或 factual_conflict；"
            "仅当 factual_conflict 时 conflict_type 填 numeric、version_time、negation_direction 或 applicability_condition，"
            "否则留空；uncertain 填 yes/no，yes 时 notes 必填。"
        )
    return common + (
        " similarity_1_to_7 填整数：1=主题/实体/事件基本无关；2=仅宽泛主题或少量词面；"
        "3=同领域/实体但事件或谓词不同；4=同一事件框架但多个关键槽或语义关系不同；"
        "5=高度相似且有明显结构改写或一个关键槽差异；6=极高相似、近似复述或单一局部差异；"
        "7=命题等价、仅措辞/句法变化。uncertain 填 yes/no，yes 时 notes 必填。"
    )


def execute() -> dict[str, Any]:
    receipt = verify_automatic_preparation()
    automatic = OUTPUT_ROOT / "automatic"
    human_root = OUTPUT_ROOT / "human_packages"
    if automatic.exists() or human_root.exists():
        raise RuntimeError("R2 automatic execution output exists; replay refused")
    families = _read_jsonl(SOURCE_ROOT / "families.jsonl")
    if len(families) != 128:
        raise RuntimeError("R2 formal family denominator drift")
    _qualification, main_spec, audit_spec = load_qualification(QUALIFICATION_ROOT)
    if f"{main_spec['model_id']}@{main_spec['revision']}" != MAIN_ENCODER:
        raise RuntimeError("R2 main encoder identity/role drift")
    if f"{audit_spec['model_id']}@{audit_spec['revision']}" != AUDIT_ENCODER:
        raise RuntimeError("R2 sensitivity encoder identity/role drift")
    inputs = build_encoder_inputs(families)
    started_ns = time.time_ns()
    automatic.mkdir(mode=0o700)
    write_json(
        automatic / "execution_started.json",
        {
            "status": "ENCODER_EXECUTION_STARTED_NO_AUTOMATIC_RETRY",
            "automatic_executor_id": AUTOMATIC_EXECUTOR_ID,
            "started_at_unix_ns": started_ns,
            "preparation_manifest_sha256": receipt["manifest_sha256"],
            "input_count": 384,
        },
    )
    main_vectors, main_metadata = encode_model(main_spec, MODEL_CACHE, inputs)
    audit_vectors, audit_metadata = encode_model(audit_spec, MODEL_CACHE, inputs)
    vectors_root = automatic / "vectors"
    vectors_root.mkdir(mode=0o700)
    np.save(vectors_root / "main.float32.npy", main_vectors, allow_pickle=False)
    np.save(vectors_root / "audit.float32.npy", audit_vectors, allow_pickle=False)
    write_jsonl(automatic / "main_input_metadata.jsonl", main_metadata)
    write_jsonl(automatic / "audit_input_metadata.jsonl", audit_metadata)
    write_jsonl(
        vectors_root / "index.jsonl",
        [{"vector_row": index, "chunk_id": row["chunk_id"]} for index, row in enumerate(inputs)],
    )
    index = {str(row["chunk_id"]): position for position, row in enumerate(inputs)}
    candidates = build_candidate_rows(families)
    candidate_vectors_main = {}
    candidate_vectors_audit = {}
    reference_vectors_main = {}
    reference_vectors_audit = {}
    for row in candidates:
        family_id = str(row["family_id"])
        source_id = f"{family_id}::{'CAND-1' if str(row['candidate_id']).endswith('::A') else 'CAND-2'}"
        candidate_vectors_main[str(row["candidate_id"])] = main_vectors[index[source_id]]
        candidate_vectors_audit[str(row["candidate_id"])] = audit_vectors[index[source_id]]
        reference_vectors_main[family_id] = [main_vectors[index[f"{family_id}::REF"]]]
        reference_vectors_audit[family_id] = [audit_vectors[index[f"{family_id}::REF"]]]
    main_rows = score_candidate_vectors(candidates, candidate_vectors=candidate_vectors_main, reference_vectors=reference_vectors_main)
    audit_rows = score_candidate_vectors(candidates, candidate_vectors=candidate_vectors_audit, reference_vectors=reference_vectors_audit)
    main_scores = {
        f"{row['candidate_id'].split('::')[0]}::{'CAND-1' if row['candidate_id'].endswith('::A') else 'CAND-2'}": row["similarity"]
        for row in main_rows
    }
    audit_scores = {
        f"{row['candidate_id'].split('::')[0]}::{'CAND-1' if row['candidate_id'].endswith('::A') else 'CAND-2'}": row["similarity"]
        for row in audit_rows
    }
    scored = build_scored_candidate_frame(families, main_scores=main_scores, audit_scores=audit_scores)
    write_jsonl(automatic / "candidate_similarity.jsonl", scored)
    write_json(
        automatic / "computation_config.json",
        {
            "automatic_executor_id": AUTOMATIC_EXECUTOR_ID,
            "estimand": "S_qg(c)=max_h_in_A_qg cosine(z(c),z(h)); exactly one locked Clean reference per family",
            "query_candidate_similarity_computed": False,
            "main_encoder": encoder_provenance(main_spec),
            "sensitivity_encoder": encoder_provenance(audit_spec),
            "cosine": "float32 normalized vectors; float64 accumulation; no rounding",
            "main_truncation": truncation_summary(families, main_metadata),
            "sensitivity_truncation": truncation_summary(families, audit_metadata),
            "python": platform.python_version(),
        },
    )
    registry, packages = build_blind_packages(families)
    facilitator = human_root / "facilitator"
    facilitator.mkdir(parents=True, mode=0o700)
    write_jsonl(facilitator / "blind_registry_not_truth.jsonl", registry)
    package_records = []
    for (reviewer, task), rows in packages.items():
        root = human_root / task / f"annotator_{reviewer.lower()}"
        root.mkdir(parents=True, mode=0o700)
        _write_csv(root / "pairs.csv", rows, ["audit_id", "query", "reference", "candidate"])
        if task == "relation":
            templates = [
                {"audit_id": row["audit_id"], "valid_reference": "", "unique_target_group": "", "target_relation": "", "conflict_type": "", "uncertain": "", "notes": ""}
                for row in rows
            ]
            fields = ["audit_id", "valid_reference", "unique_target_group", "target_relation", "conflict_type", "uncertain", "notes"]
        else:
            templates = [{"audit_id": row["audit_id"], "similarity_1_to_7": "", "uncertain": "", "notes": ""} for row in rows]
            fields = ["audit_id", "similarity_1_to_7", "uncertain", "notes"]
        _write_csv(root / "submission_template.csv", templates, fields)
        (root / "README.txt").write_text(_package_instruction(task) + "\n", encoding="utf-8")
        (root / "README.txt").chmod(0o600)
        manifest = {
            "status": "BLIND_HUMAN_PACKAGE_AWAITING_REAL_RESEARCHER",
            "reviewer": reviewer,
            "task": task,
            "rows": 256,
            "contains_answer_key": False,
            "contains_model_scores": False,
            "contains_generator_or_construction_role": False,
            "files": [
                {"name": name, "sha256": sha256_file(root / name)}
                for name in ("README.txt", "pairs.csv", "submission_template.csv")
            ],
        }
        write_json(root / "package_manifest.json", manifest)
        package_records.append({"reviewer": reviewer, "task": task, "path": str(root.relative_to(REPO_ROOT)), "manifest_sha256": sha256_file(root / "package_manifest.json")})
    managed = [path for path in automatic.rglob("*") if path.is_file()]
    manifest = {
        "status": "R2_AUTOMATIC_COMPLETE_AWAITING_FOUR_HUMAN_SUBMISSIONS",
        "automatic_executor_id": AUTOMATIC_EXECUTOR_ID,
        "started_at_unix_ns": started_ns,
        "completed_at_unix_ns": time.time_ns(),
        "fixed_families": 128,
        "fixed_candidate_denominator": 256,
        "encoder_input_count_each": 384,
        "main_vector_shape": list(main_vectors.shape),
        "sensitivity_vector_shape": list(audit_vectors.shape),
        "source_lock_sha256": sha256_file(SOURCE_ROOT / "lock.json"),
        "preparation_manifest_sha256": receipt["manifest_sha256"],
        "files": [{"path": str(path.relative_to(OUTPUT_ROOT)), "sha256": sha256_file(path), "size_bytes": path.stat().st_size} for path in sorted(managed)],
        "human_packages": package_records,
        "human_rows_per_researcher": {"relation": 256, "similarity": 256, "total": 512},
        "formal_measurement_decision": "AWAITING_HUMAN_SUBMISSIONS",
        "readiness_run": False,
        "gate_a_run": False,
        "blind_read": False,
    }
    write_json(automatic / "manifest.json", manifest)
    return {"status": manifest["status"], "manifest_sha256": sha256_file(automatic / "manifest.json"), "human_packages": package_records}


if __name__ == "__main__":
    print(json.dumps(execute(), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
