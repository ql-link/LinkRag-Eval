#!/usr/bin/env python3
"""Run the outcome-aware, read-only R2 similarity failure diagnostic."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from linkrag_eval.robust_fusion.r2_similarity_diagnostic import (
    clustered_bootstrap,
    detect_language,
    fallacy_scan,
    grouped_summaries,
    influence_diagnostics,
    summarize_rows,
    surface_metrics,
    truncation_boundary,
)
from linkrag_eval.robust_fusion.similarity_dev_calibration import (
    canonical_json,
    sha256_file,
    write_json,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
V1_ROOT = REPO_ROOT / (
    "runs/robust_fusion/similarity_dev_calibration_v1/"
    "internal-v6-dev-similarity-calibration-v1-20260829"
)
SUPPLEMENT_ROOT = REPO_ROOT / (
    "runs/robust_fusion/similarity_dev_support_supplement_v1/"
    "internal-v6-dev-similarity-support-supplement-v1-20260829"
)
OUTPUT_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_similarity_diagnostic_v1/"
    "robust-fusion-r2-similarity-diagnostic-v1-20260829"
)
RESEARCH_ID = "ROBUST-FUSION-R2-2026-08-29"
RECORD_ID = "ROBUST-FUSION-RESEARCH-R2-2026-08-29-v1-DRAFT"
DIAGNOSTIC_ID = "ROBUST-FUSION-R2-SIMILARITY-DIAGNOSTIC-2026-08-29-v1"
FINAL_OUTPUTS = (
    "diagnostic_results.json",
    "diagnostic_rows.jsonl",
    "diagnostic_report.md",
    "manifest.json",
    "manifest.sha256",
    "receipt.json",
    "receipt.sha256",
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _verify_sidecar(path: Path) -> str:
    sidecar = path.with_suffix(".sha256")
    parts = sidecar.read_text(encoding="utf-8").split()
    if len(parts) != 2 or parts[1] != path.name:
        raise RuntimeError(f"invalid SHA-256 sidecar: {sidecar}")
    observed = sha256_file(path)
    if observed != parts[0]:
        raise RuntimeError(f"locked diagnostic setup drift: {path}")
    return observed


def verify_pre_execution_lock(output_root: Path = OUTPUT_ROOT) -> dict[str, Any]:
    required = (
        "diagnostic_plan.md",
        "input_manifest.json",
        "input_manifest_addendum_v1.json",
        "input_manifest_addendum_v2.json",
        "schema_mapping_spec.json",
    )
    hashes = {name: _verify_sidecar(output_root / name) for name in required}
    plan_lock = json.loads((output_root / "plan_lock.json").read_text(encoding="utf-8"))
    if plan_lock["status"] != "OUTCOME_AWARE_EXPLORATORY_PLAN_LOCKED_BEFORE_DIAGNOSTIC":
        raise RuntimeError("invalid R2 diagnostic plan lock state")
    if plan_lock["diagnostic_plan"]["sha256"] != hashes["diagnostic_plan.md"]:
        raise RuntimeError("diagnostic plan lock hash drift")
    if plan_lock["input_manifest"]["sha256"] != hashes["input_manifest.json"]:
        raise RuntimeError("diagnostic input-manifest lock hash drift")

    input_records = []
    for name in (
        "input_manifest.json",
        "input_manifest_addendum_v1.json",
        "input_manifest_addendum_v2.json",
    ):
        payload = json.loads((output_root / name).read_text(encoding="utf-8"))
        input_records.extend(
            payload.get("allowed_inputs", payload.get("allowed_inputs_added", []))
        )
    paths = [record["path"] for record in input_records]
    if len(paths) != len(set(paths)):
        raise RuntimeError("duplicate path across R2 diagnostic input manifests")
    for record in input_records:
        path = (REPO_ROOT / record["path"]).resolve()
        if not path.is_relative_to(REPO_ROOT.resolve()):
            raise RuntimeError(f"diagnostic input escapes repository: {path}")
        lowered = path.as_posix().lower()
        if any(token in lowered for token in ("/gate_a/", "/gate_b/", "/blind/")):
            raise RuntimeError(f"forbidden Gate/Blind input: {path}")
        if sha256_file(path) != record["sha256"]:
            raise RuntimeError(f"R1 read-only diagnostic input drift: {path}")
    return {"setup_hashes": hashes, "input_records": input_records}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_v1_pairs(path: Path) -> dict[str, tuple[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["audit_id", "text_1", "text_2"]:
            raise RuntimeError("v1 pair-table schema drift")
        rows = list(reader)
    output = {row["audit_id"]: (row["text_1"], row["text_2"]) for row in rows}
    if len(output) != len(rows):
        raise RuntimeError("duplicate v1 pair audit IDs")
    return output


def build_v1_rows() -> list[dict[str, Any]]:
    scores = read_jsonl(V1_ROOT / "human_audit/facilitator/adjudication_v1/final_scores.jsonl")
    pairs = _read_v1_pairs(V1_ROOT / "human_audit/annotator_a/pairs.csv")
    if len(scores) != 24 or set(pairs) != {row["audit_id"] for row in scores}:
        raise RuntimeError("v1 final-score/pair frame drift")
    output = []
    for row in scores:
        first, second = pairs[row["audit_id"]]
        matches = [text for text in (first, second) if _sha256_text(text) == row["candidate_raw_content_sha256"]]
        if len(matches) != 1:
            raise RuntimeError(f"v1 candidate text hash mapping failed: {row['audit_id']}")
        candidate = matches[0]
        reference = second if candidate == first else first
        surface = surface_metrics(reference, candidate)
        output.append(
            {
                "cohort": "v1",
                "sample_id": row["audit_id"],
                "family_id": row["query_uid"],
                "candidate_id": row["candidate_chunk_id"],
                "length_stratum": row["length_stratum"],
                "language": detect_language(reference + " " + candidate),
                "relation": row["target_relation"],
                "conflict_type": row["conflict_type"],
                "human_score": int(row["final_human_similarity_ordinal"]),
                "main_similarity": float(row["main_similarity"]),
                "audit_similarity": float(row["audit_similarity"]),
                "main_was_truncated": bool(row["main_was_truncated"]),
                "audit_was_truncated": bool(row["audit_was_truncated"]),
                "template_hash": None,
                "candidate_text_sha256": _sha256_text(candidate),
                "reference_text_sha256": _sha256_text(reference),
                **surface,
            }
        )
    return sorted(output, key=lambda row: row["sample_id"])


def build_supplement_rows() -> list[dict[str, Any]]:
    families = {
        row["query_family_id"]: row for row in read_jsonl(SUPPLEMENT_ROOT / "data/families.jsonl")
    }
    scores = {
        row["candidate_id"]: row
        for row in read_jsonl(SUPPLEMENT_ROOT / "automatic/candidate_similarity.jsonl")
    }
    relations = {
        row["candidate_id"]: row["final_relation_truth"]
        for row in read_jsonl(
            SUPPLEMENT_ROOT
            / "human_review/facilitator/finalization_v1/final_relation_records.jsonl"
        )
    }
    human = read_jsonl(
        SUPPLEMENT_ROOT
        / "human_review/facilitator/finalization_v1/final_similarity_records.jsonl"
    )
    if len(human) != 48 or len(families) != 72 or len(relations) != 144:
        raise RuntimeError("supplement locked frame drift")
    output = []
    for row in human:
        family = families[row["query_family_id"]]
        score = scores[row["candidate_id"]]
        truth = relations[row["candidate_id"]]
        if family["language"] not in {"zh", "en"}:
            raise RuntimeError("supplement language metadata drift")
        if row["candidate_id"] == family["equivalent_candidate_id"]:
            candidate = family["equivalent_candidate"]
        elif row["candidate_id"] == family["conflict_candidate_id"]:
            candidate = family["factual_conflict_candidate"]
        else:
            raise RuntimeError(f"supplement candidate/family mapping failed: {row['candidate_id']}")
        relation = truth["target_relation"]
        conflict_type = (
            family["conflict_type_preregistered"]
            if relation == "factual_conflict"
            else "not_applicable"
        )
        surface = surface_metrics(family["reference"], candidate)
        output.append(
            {
                "cohort": "supplement",
                "sample_id": row["similarity_audit_id"],
                "family_id": row["query_family_id"],
                "candidate_id": row["candidate_id"],
                "length_stratum": row["length_stratum"],
                "language": family["language"],
                "relation": relation,
                "conflict_type": conflict_type,
                "human_score": int(row["final_human_similarity_ordinal"]),
                "main_similarity": float(row["main_similarity"]),
                "audit_similarity": float(row["audit_similarity"]),
                "main_was_truncated": bool(score["main_was_truncated"]),
                "audit_was_truncated": bool(score["audit_was_truncated"]),
                "template_hash": family["candidate_surface_template_sha256"],
                "candidate_text_sha256": _sha256_text(candidate),
                "reference_text_sha256": _sha256_text(family["reference"]),
                **surface,
            }
        )
    return sorted(output, key=lambda row: row["sample_id"])


def _difference(left: Any, right: Any) -> float | None:
    return None if left is None or right is None else float(right) - float(left)


def build_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cohorts = {
        cohort: [row for row in rows if row["cohort"] == cohort]
        for cohort in ("v1", "supplement")
    }
    if len(cohorts["v1"]) != 24 or len(cohorts["supplement"]) != 48:
        raise RuntimeError("R1 diagnostic row-count drift")
    cohort_summaries = {name: summarize_rows(values) for name, values in cohorts.items()}
    v1_summary = cohort_summaries["v1"]
    supplement_summary = cohort_summaries["supplement"]
    v1_review = json.loads(
        (V1_ROOT / "human_audit/facilitator/adjudication_v1/final_review.json").read_text(
            encoding="utf-8"
        )
    )
    supplement_validity = json.loads(
        (
            SUPPLEMENT_ROOT
            / "human_review/facilitator/finalization_v1/human_validity.json"
        ).read_text(encoding="utf-8")
    )
    final_decision = json.loads(
        (
            SUPPLEMENT_ROOT
            / "human_review/facilitator/finalization_v1/final_decision.json"
        ).read_text(encoding="utf-8")
    )
    if final_decision["status"] != "P2_TERMINAL_INCONCLUSIVE_GATE_A_UNAUTHORIZED":
        raise RuntimeError("R1 terminal decision drift")

    strata = grouped_summaries(
        rows,
        (
            ("cohort", "length_stratum"),
            ("cohort", "language"),
            ("cohort", "relation"),
            ("cohort", "conflict_type"),
            ("cohort", "length_stratum", "language"),
            ("cohort", "relation", "conflict_type"),
        ),
    )
    bootstrap = {
        "v1": clustered_bootstrap(cohorts["v1"]),
        "supplement": clustered_bootstrap(cohorts["supplement"]),
        "combined": clustered_bootstrap(rows),
    }
    influence = {
        "v1": influence_diagnostics(cohorts["v1"]),
        "supplement": influence_diagnostics(cohorts["supplement"]),
        "combined": influence_diagnostics(rows),
    }
    distribution_shift = {
        "direction": "supplement_minus_v1",
        "human_range_delta": _difference(
            v1_summary["human"]["range"], supplement_summary["human"]["range"]
        ),
        "human_variance_delta": _difference(
            v1_summary["human"]["variance_ddof1"],
            supplement_summary["human"]["variance_ddof1"],
        ),
        "human_pairwise_tie_fraction_delta": _difference(
            v1_summary["human"]["pairwise_tie_fraction"],
            supplement_summary["human"]["pairwise_tie_fraction"],
        ),
        "human_ceiling_fraction_delta": _difference(
            v1_summary["human"]["ceiling_fraction_score_5"],
            supplement_summary["human"]["ceiling_fraction_score_5"],
        ),
        "human_normalized_entropy_delta": _difference(
            v1_summary["human"]["normalized_entropy"],
            supplement_summary["human"]["normalized_entropy"],
        ),
        "main_range_ratio_supplement_over_v1": (
            supplement_summary["main_encoder"]["range"]
            / v1_summary["main_encoder"]["range"]
        ),
        "main_variance_ratio_supplement_over_v1": (
            supplement_summary["main_encoder"]["variance_ddof1"]
            / v1_summary["main_encoder"]["variance_ddof1"]
        ),
        "audit_range_ratio_supplement_over_v1": (
            supplement_summary["audit_encoder"]["range"]
            / v1_summary["audit_encoder"]["range"]
        ),
        "audit_variance_ratio_supplement_over_v1": (
            supplement_summary["audit_encoder"]["variance_ddof1"]
            / v1_summary["audit_encoder"]["variance_ddof1"]
        ),
        "single_slot_proxy_fraction_delta": _difference(
            v1_summary["surface"]["single_slot_proxy_fraction"],
            supplement_summary["surface"]["single_slot_proxy_fraction"],
        ),
    }
    evidence_table = [
        {
            "layer": "annotation_consistency",
            "evidence": {
                "v1_qwk": v1_review["inter_reviewer"]["quadratic_weighted_kappa"],
                "v1_within_one": v1_review["inter_reviewer"]["within_one_fraction"],
                "supplement_qwk": supplement_validity["supplement_only"]["inter_reviewer"][
                    "quadratic_weighted_kappa"
                ],
                "supplement_exact_fraction": supplement_validity["supplement_only"][
                    "inter_reviewer"
                ]["exact_agreement_fraction"],
            },
            "inference": "Low inter-reviewer reliability is not supported as the primary explanation.",
            "cannot_distinguish": "High agreement does not prove that the ordinal scale has enough resolution in the high-similarity region.",
        },
        {
            "layer": "relation_data_quality",
            "evidence": {
                "supplement_final_relation_rows": 144,
                "supplement_relation_ab_exact": True,
                "construction_role_used_as_truth": False,
            },
            "inference": "Mechanical relation-label disagreement is not supported as the immediate cause.",
            "cannot_distinguish": "Exact agreement cannot establish ecological diversity or external validity of deterministic microfacts.",
        },
        {
            "layer": "calibration_sample_distribution",
            "evidence": distribution_shift,
            "inference": "Range restriction, repetitive surface construction, or ordinal compression remain plausible when their descriptive indicators are stronger in the supplement.",
            "cannot_distinguish": "These correlated design features cannot be separated causally in the outcome-aware R1 data.",
        },
        {
            "layer": "main_encoder_fit",
            "evidence": {
                "v1_main_human": v1_summary["correlations"]["main_human"],
                "supplement_main_human": supplement_summary["correlations"]["main_human"],
                "v1_audit_human": v1_summary["correlations"]["audit_human"],
                "supplement_audit_human": supplement_summary["correlations"]["audit_human"],
            },
            "inference": "A sample-dependent mismatch between E5 ranks and the human ordinal construct is supported descriptively.",
            "cannot_distinguish": "R1 cannot separate encoder limitation from restricted range, text templates, scale compression, or their interaction; DistilUSE is not promoted.",
        },
        {
            "layer": "aggregation_scope",
            "evidence": {
                "overall": summarize_rows(rows)["correlations"],
                "leave_one_stratum_out": influence["combined"][
                    "leave_one_length_language_stratum_out"
                ],
            },
            "inference": "Differences between overall and frozen strata quantify aggregation sensitivity.",
            "cannot_distinguish": "Outcome-aware strata cannot justify choosing a post-hoc aggregation rule; R2 must freeze one on new family-disjoint Dev.",
        },
    ]
    return {
        "schema_version": "robust-fusion-r2-similarity-diagnostic-results-v1",
        "research_id": RESEARCH_ID,
        "record_id": RECORD_ID,
        "diagnostic_id": DIAGNOSTIC_ID,
        "status": "EXPLORATORY_DIAGNOSTIC_COMPLETE_R2_DRAFT_NOT_AUTHORIZED",
        "outcome_awareness": "KNOWN_R1_TERMINAL_INCONCLUSIVE_EXPLORATORY_ONLY",
        "confirmatory_authority": "NONE",
        "sample_counts": {"v1": 24, "supplement": 48, "combined": 72},
        "cohort_summaries": cohort_summaries,
        "combined_summary": summarize_rows(rows),
        "stratified_summaries": strata,
        "distribution_shift": distribution_shift,
        "clustered_bootstrap": bootstrap,
        "influence_diagnostics": influence,
        "truncation_boundary": truncation_boundary(rows),
        "evidence_inference_cannot_distinguish": evidence_table,
        "fallacy_scan": fallacy_scan(),
        "r1_terminal_status_preserved": final_decision["status"],
        "r2_family_eligibility": "R1_ALL_FAMILIES_EXPLORATORY_ONLY_EXCLUDED_FROM_R2_DEV_GATE_A_BLIND",
    }


def _format_float(value: Any) -> str:
    return "undefined" if value is None else f"{float(value):.4f}"


def render_report(results: dict[str, Any]) -> str:
    v1 = results["cohort_summaries"]["v1"]
    supplement = results["cohort_summaries"]["supplement"]
    shift = results["distribution_shift"]
    truncation = results["truncation_boundary"]
    lines = [
        "# Robust Fusion R2 相似度失败只读诊断报告",
        "",
        "## Material Passport",
        "",
        "- Origin Skill: academic-research-suite / experiment-agent",
        "- Origin Mode: validate",
        "- Verification Status: ANALYZED",
        "- Version Label: robust-fusion-r2-diagnostic-v1",
        f"- Research ID: `{RESEARCH_ID}`",
        "- Status: `EXPLORATORY_DIAGNOSTIC_COMPLETE_R2_DRAFT_NOT_AUTHORIZED`",
        "",
        "本报告是已知 R1 终局后的 outcome-aware 探索性诊断，不是预注册确认性分析，不产生新 PASS 路径。R1/v29 与全部锁定制品保持不变；R1 family 不得进入 R2 Dev、Gate A 或 Blind。",
        "",
        "## 核心描述",
        "",
        "| 指标 | v1 | supplement |",
        "| --- | ---: | ---: |",
        f"| 人工样本 n | {v1['n']} | {supplement['n']} |",
        f"| 人工唯一分值数 | {v1['human']['unique_value_count']} | {supplement['human']['unique_value_count']} |",
        f"| 人工 pairwise tie | {_format_float(v1['human']['pairwise_tie_fraction'])} | {_format_float(supplement['human']['pairwise_tie_fraction'])} |",
        f"| 人工 ceiling(score=5) | {_format_float(v1['human']['ceiling_fraction_score_5'])} | {_format_float(supplement['human']['ceiling_fraction_score_5'])} |",
        f"| 人工归一化熵 | {_format_float(v1['human']['normalized_entropy'])} | {_format_float(supplement['human']['normalized_entropy'])} |",
        f"| E5 range | {_format_float(v1['main_encoder']['range'])} | {_format_float(supplement['main_encoder']['range'])} |",
        f"| DistilUSE range | {_format_float(v1['audit_encoder']['range'])} | {_format_float(supplement['audit_encoder']['range'])} |",
        f"| E5—人工 Spearman | {_format_float(v1['correlations']['main_human']['spearman'])} | {_format_float(supplement['correlations']['main_human']['spearman'])} |",
        f"| E5—人工 Kendall tau-b | {_format_float(v1['correlations']['main_human']['kendall_tau_b'])} | {_format_float(supplement['correlations']['main_human']['kendall_tau_b'])} |",
        f"| DistilUSE—人工 Spearman | {_format_float(v1['correlations']['audit_human']['spearman'])} | {_format_float(supplement['correlations']['audit_human']['spearman'])} |",
        f"| 单槽替换代理比例 | {_format_float(v1['surface']['single_slot_proxy_fraction'])} | {_format_float(supplement['surface']['single_slot_proxy_fraction'])} |",
        "",
        (
            "supplement/v1 的 E5 range 比为 "
            f"`{shift['main_range_ratio_supplement_over_v1']:.4f}`，方差比为 "
            f"`{shift['main_variance_ratio_supplement_over_v1']:.4f}`；这些是 "
            "range restriction 的描述性证据，不是因果归因。"
        ),
        "",
        "## 截断边界",
        "",
        f"- E5：72 条中截断 {results['combined_summary']['truncation']['main_truncated_count']} 条；long 截断组 n={truncation['main_e5']['long_truncated']['n']}。",
        f"- DistilUSE：72 条中截断 {results['combined_summary']['truncation']['audit_truncated_count']} 条；long 截断组 n={truncation['audit_distiluse']['long_truncated']['n']}，未截断 long n={truncation['audit_distiluse']['long_not_truncated']['n']}。",
        f"- DistilUSE long 截断组 Spearman={_format_float(truncation['audit_distiluse']['long_truncated']['spearman_human'])}；未截断 long={_format_float(truncation['audit_distiluse']['long_not_truncated']['spearman_human'])}。小组值仅界定影响边界，不能晋升 DistilUSE。",
        "",
        "## 证据—推断—尚不能区分",
        "",
        "| 层次 | 推断 | 尚不能区分 |",
        "| --- | --- | --- |",
    ]
    for item in results["evidence_inference_cannot_distinguish"]:
        lines.append(
            f"| {item['layer']} | {item['inference']} | {item['cannot_distinguish']} |"
        )
    lines.extend(
        [
            "",
            "## 方法学谬误扫描",
            "",
            "覆盖 `11/11`。本分析明确保留选择性样本、look-elsewhere 与 outcome-aware researcher degrees of freedom 的风险；所有 strata 和不确定性结果完整写入机器制品，不据此新增 PASS。未作个体推断、概率诊断、前后干预或因果方向声明。",
            "",
            "## 复算",
            "",
            "```bash",
            "PYTHONPATH=src:. .venv/bin/python scripts/run_robust_fusion_r2_similarity_diagnostic.py",
            "```",
            "",
            "正式目录为 append-only；命令重复执行会拒绝覆盖。",
            "",
        ]
    )
    return "\n".join(lines)


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in row.items()
        if key not in {"normalized_candidate_text"}
    }


def run(output_root: Path = OUTPUT_ROOT) -> dict[str, Any]:
    if output_root.resolve() != OUTPUT_ROOT.resolve():
        raise RuntimeError("R2 diagnostic output root is fixed")
    existing = [name for name in FINAL_OUTPUTS if (output_root / name).exists()]
    if existing:
        raise RuntimeError(f"refusing to overwrite append-only R2 diagnostic outputs: {existing}")
    lock = verify_pre_execution_lock(output_root)
    rows = build_v1_rows() + build_supplement_rows()
    results = build_results(rows)

    rows_path = output_root / "diagnostic_rows.jsonl"
    rows_path.write_text(
        "".join(canonical_json(_public_row(row)) + "\n" for row in rows),
        encoding="utf-8",
    )
    write_json(output_root / "diagnostic_results.json", results)
    (output_root / "diagnostic_report.md").write_text(
        render_report(results), encoding="utf-8"
    )
    manifest_files = [
        "diagnostic_plan.md",
        "diagnostic_plan.sha256",
        "input_manifest.json",
        "input_manifest.sha256",
        "input_manifest_addendum_v1.json",
        "input_manifest_addendum_v1.sha256",
        "input_manifest_addendum_v2.json",
        "input_manifest_addendum_v2.sha256",
        "schema_mapping_spec.json",
        "schema_mapping_spec.sha256",
        "plan_lock.json",
        "diagnostic_rows.jsonl",
        "diagnostic_results.json",
        "diagnostic_report.md",
    ]
    manifest = {
        "schema_version": "robust-fusion-r2-similarity-diagnostic-manifest-v1",
        "research_id": RESEARCH_ID,
        "record_id": RECORD_ID,
        "diagnostic_id": DIAGNOSTIC_ID,
        "created_at": now_iso(),
        "status": results["status"],
        "command": "PYTHONPATH=src:. .venv/bin/python scripts/run_robust_fusion_r2_similarity_diagnostic.py",
        "code": {
            "script": {
                "path": "scripts/run_robust_fusion_r2_similarity_diagnostic.py",
                "sha256": sha256_file(Path(__file__)),
            },
            "module": {
                "path": "src/linkrag_eval/robust_fusion/r2_similarity_diagnostic.py",
                "sha256": sha256_file(
                    REPO_ROOT
                    / "src/linkrag_eval/robust_fusion/r2_similarity_diagnostic.py"
                ),
            },
        },
        "input_manifest_records": lock["input_records"],
        "files": [
            {
                "path": name,
                "size_bytes": (output_root / name).stat().st_size,
                "sha256": sha256_file(output_root / name),
            }
            for name in manifest_files
        ],
        "forbidden_actions_executed": [],
        "r1_mutated": False,
        "blind_read": False,
        "readiness_or_gate_executed": False,
        "confirmatory_authority": "NONE",
    }
    write_json(output_root / "manifest.json", manifest)
    manifest_sha = sha256_file(output_root / "manifest.json")
    (output_root / "manifest.sha256").write_text(
        f"{manifest_sha}  manifest.json\n", encoding="utf-8"
    )
    receipt = {
        "schema_version": "robust-fusion-r2-similarity-diagnostic-receipt-v1",
        "research_id": RESEARCH_ID,
        "diagnostic_id": DIAGNOSTIC_ID,
        "status": results["status"],
        "manifest_sha256": manifest_sha,
        "terminal_authority": "NONE_R2_DRAFT_NOT_AUTHORIZED",
    }
    write_json(output_root / "receipt.json", receipt)
    receipt_sha = sha256_file(output_root / "receipt.json")
    (output_root / "receipt.sha256").write_text(
        f"{receipt_sha}  receipt.json\n", encoding="utf-8"
    )
    return {
        "status": results["status"],
        "manifest_sha256": manifest_sha,
        "receipt_sha256": receipt_sha,
        "sample_counts": results["sample_counts"],
    }


def main() -> int:
    print(canonical_json(run()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
