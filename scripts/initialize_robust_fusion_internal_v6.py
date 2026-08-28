#!/usr/bin/env python3
"""Initialize the governed, physically separated Internal Stress v6 package.

The initializer creates cohort identities, access locks, intake schemas, source
eligibility records, and deterministic checksums. It does not invent queries,
qrels, evidence, or labels. A freshly initialized package is therefore formally
established but intentionally not populated or eligible for Gate A/Gate B.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

PACKAGE_VERSION = "ROBUST-FUSION-INTERNAL-STRESS-2026-08-28-v6"
SCIENTIFIC_PROTOCOL = "ROBUST-FUSION-RESEARCH-2026-08-28-v19"
ENGINEERING_PROTOCOL = "ROBUST-FUSION-ENGINEERING-2026-08-29-v10"
PROGRESS_RECORD = "ROBUST-FUSION-PROGRESS-2026-08-29-v21"
DATA_AUDIT_RECORD = "ROBUST-FUSION-GATE-A-DATA-AUDIT-2026-08-28-v10"
ASSET_RECORD = "SQLITE-SHARE-ASSET-RECONCILIATION-2026-08-28-v4"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(canonical_json(value) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def write_tsv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    os.chmod(path, 0o600)


def ensure_new_root(root: Path) -> None:
    if root.exists() and any(root.iterdir()):
        raise RuntimeError(f"refusing to overwrite non-empty Internal v6 root: {root}")
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)


def create_directories(root: Path) -> None:
    for relative in ("control", "intake", "dev", "gatea", "blind"):
        path = root / relative
        path.mkdir(exist_ok=False)
        os.chmod(path, 0o700)


def source_eligibility_rows() -> list[dict[str, str]]:
    return [
        {
            "asset_scope": "linkrag-eval-sqlite-share-20260827 + old eval MySQL",
            "research_role": "hypothesis_origin; engineering_provenance; feasibility_and_budget_evidence",
            "text_status": "dataset_specific_validation_required",
            "query_qrel_status": "0 query; 0 qrel in both reconciled stores",
            "internal_v6_use": "IDs/provenance/index coverage and validated corpus substrate only",
            "confirmatory_eligibility": "not_query_truth",
            "required_action": "collect new real queries and independently verify target evidence",
        },
        {
            "asset_scope": "SQLite datasets 990123/990124",
            "research_role": "possible internal document substrate",
            "text_status": "not yet matched to a pinned authoritative source",
            "query_qrel_status": "none",
            "internal_v6_use": "none until content/provenance validation",
            "confirmatory_eligibility": "blocked",
            "required_action": "validate source, license/authorization, text hash, privacy and exposure",
        },
        {
            "asset_scope": "SQLite datasets 990126/990127",
            "research_role": "public-entity ID/exposure crosswalk",
            "text_status": "800/800 IDs match each pinned C-MTEB entity; 0/800 texts match; mojibake",
            "query_qrel_status": "none",
            "internal_v6_use": "ID/provenance only; never reuse stored text/vector/token",
            "confirmatory_eligibility": "text_ineligible",
            "required_action": "reload any needed public text from the pinned official files",
        },
        {
            "asset_scope": "SQLite datasets 990131/990901/990997/990998/990999",
            "research_role": "synthetic, pilot or smoke engineering history",
            "text_status": "historical development assets",
            "query_qrel_status": "none in shared SQLite",
            "internal_v6_use": "Dev diagnostics only after provenance review",
            "confirmatory_eligibility": "exposed_or_nonreal",
            "required_action": "do not place in Internal v6-GateA or v6-Blind",
        },
        {
            "asset_scope": "SQLite datasets 991001-991004 and 992000-992003",
            "research_role": "historical golden/background and scale-test substrate",
            "text_status": "used in prior engineering development",
            "query_qrel_status": "row-level query/qrel package absent",
            "internal_v6_use": (
                "validated fixed background corpus for new query families; historical query/label roles are Dev-only"
            ),
            "confirmatory_eligibility": "background_only_conditional",
            "required_action": (
                "validate content/provenance and exclude historical query, target, version and template families; "
                "collect new queries and review new target evidence"
            ),
        },
        {
            "asset_scope": "SQLite datasets 993100-993104 (Blind v4/v5)",
            "research_role": "research motivation and exposure register",
            "text_status": "historical Blind was opened and used",
            "query_qrel_status": "row-level package absent from share",
            "internal_v6_use": "motivation/Dev audit only; no renaming or recycling",
            "confirmatory_eligibility": "permanently_excluded",
            "required_action": "exclude every recovered query/document/template family from GateA/Blind",
        },
        {
            "asset_scope": "BM25/Alt Embedding/current and historical eval Qdrant",
            "research_role": "engineering cache and route-coverage evidence",
            "text_status": "BM25/Qdrant require exact manifest match; Alt is historical BGE-M3 only",
            "query_qrel_status": "none",
            "internal_v6_use": "BM25/Qdrant may accelerate after contract lock; Alt/BGE is never reused",
            "confirmatory_eligibility": "not_truth",
            "required_action": (
                "recompute the actual text-embedding-v4, Ark/Doubao and SQLite FTS5 routes when any "
                "text/model/tokenizer/hash contract differs; reject BGE-M3"
            ),
        },
        {
            "asset_scope": "ssh linkcv middleware host",
            "research_role": "service infrastructure only",
            "text_status": "no LinkRag-Eval deployment or row-level research package found",
            "query_qrel_status": "none found",
            "internal_v6_use": "no data role",
            "confirmatory_eligibility": "none",
            "required_action": "do not treat server filesystem as a truth source",
        },
    ]


def exposure_rows() -> list[dict[str, str]]:
    return [
        {
            "exposure_id": "historical-blind-v4-v5",
            "scope": "all recovered or reconstructable queries, documents, versions and templates",
            "allowed_role": "motivation_or_dev_audit_only",
            "forbidden_role": "internal-v6-gatea;internal-v6-blind",
            "closure_rule": "family-level exclusion; renaming or re-ID does not remove exposure",
        },
        {
            "exposure_id": "share-package-historical-runs",
            "scope": "51 runs and 2,884 aggregate metric rows",
            "allowed_role": "hypothesis provenance; engineering feasibility; budget planning",
            "forbidden_role": "GateA_or_GateB_confirmatory_evidence",
            "closure_rule": "no row-level reconstruction from aggregates",
        },
    ]


def cohort_manifest(cohort: str) -> dict[str, Any]:
    definitions = {
        "dev": {
            "cohort_id": "internal-v6-dev",
            "role": "construct_annotation_similarity_proxy_and_power_calibration",
            "runtime_access": "development_allowed_only_after_population_and_validation",
            "unlock_condition": "validated intake plus family assignment; remains exposed thereafter",
            "count_visibility": "visible",
        },
        "gatea": {
            "cohort_id": "internal-v6-gatea",
            "role": "independent_C1_C2_phenomenon_and_proxy_study",
            "runtime_access": "locked_to_method_development",
            "unlock_condition": "P2/P3/P4/P5 freeze and externally timestamped Gate A root hash",
            "count_visibility": "eligibility counts may be sealed; no outcome access before unlock",
        },
        "blind": {
            "cohort_id": "internal-v6-blind",
            "role": "one_shot_GateB_confirmation_after_M1_freeze",
            "runtime_access": "curator_hash_tool_only_before_unlock",
            "unlock_condition": "Gate A Go plus frozen M1/comparators/epsilon/analysis and Gate B root hash",
            "count_visibility": "withheld_after_population_until_unlock",
        },
    }
    return {
        "package_version": PACKAGE_VERSION,
        **definitions[cohort],
        "population_state": "EMPTY_AWAITING_NEW_REAL_QUERY_INTAKE",
        "record_count": 0 if cohort != "blind" else None,
        "query_family_count": 0 if cohort != "blind" else None,
        "content_files": [],
        "content_root_sha256": None,
        "sealed_at": None,
        "unlocked_at": None,
        "prohibitions": [
            "no historical Blind v4/v5 family",
            "no query, document-version, or counterfactual-template family overlap across cohorts",
            "no missing public qrel treated as a negative label",
            "no outcome-dependent replacement, resizing, or cohort switching",
        ],
    }


def access_lock(cohort: str) -> dict[str, Any]:
    if cohort == "gatea":
        message = "Gate A runtime access is denied until the preregistered Gate A seal is complete."
    else:
        message = "Blind runtime access is denied until Gate A=Go and M1/Gate B are fully frozen."
    return {
        "package_version": PACKAGE_VERSION,
        "cohort_id": f"internal-v6-{cohort}",
        "lock_state": "LOCKED_EMPTY",
        "message": message,
        "allowed_before_unlock": [
            "curator-only intake validation",
            "family overlap rejection",
            "read-only ID/hash manifest generation",
        ],
        "forbidden_before_unlock": [
            "method-development scan",
            "candidate scoring",
            "outcome computation",
            "text/count inspection by experiment runtime",
        ],
    }


def initialize(root: Path, repository_root: Path) -> dict[str, Any]:
    ensure_new_root(root)
    create_directories(root)

    source_path = root / "control" / "source_eligibility.tsv"
    source_fields = [
        "asset_scope",
        "research_role",
        "text_status",
        "query_qrel_status",
        "internal_v6_use",
        "confirmatory_eligibility",
        "required_action",
    ]
    write_tsv(source_path, source_fields, source_eligibility_rows())

    exposure_path = root / "control" / "exposure_exclusions.tsv"
    exposure_fields = ["exposure_id", "scope", "allowed_role", "forbidden_role", "closure_rule"]
    write_tsv(exposure_path, exposure_fields, exposure_rows())

    query_fields = [
        "intake_record_id",
        "source_system",
        "source_query_id",
        "query_text_local",
        "query_sha256",
        "query_origin",
        "collection_date",
        "privacy_review_status",
        "consent_or_authorization",
        "exposure_status",
        "query_family_id",
        "document_family_id",
        "version_family_id",
        "counterfactual_template_family_id",
        "proposed_cohort",
        "curator_id",
        "intake_status",
    ]
    write_tsv(root / "intake" / "query_intake_template.tsv", query_fields, [])

    document_fields = [
        "intake_record_id",
        "source_system",
        "source_document_id",
        "source_chunk_id",
        "document_text_local",
        "content_sha256",
        "source_locator_local",
        "license_or_authorization",
        "privacy_review_status",
        "document_family_id",
        "version_id",
        "version_family_id",
        "effective_date",
        "parser_id",
        "chunker_id",
        "chunker_parameters_sha256",
        "source_span_locator",
        "exposure_status",
        "intake_status",
    ]
    write_tsv(root / "intake" / "document_intake_template.tsv", document_fields, [])

    evidence_fields = [
        "source_query_id",
        "source_chunk_id",
        "source_relevance_label",
        "target_equivalence_group_id",
        "target_relation",
        "conflict_type",
        "adjudicability",
        "evidence_locator_local",
        "evidence_span_local",
        "reviewer_a",
        "reviewer_b",
        "adjudicator",
        "review_status",
        "handbook_version",
        "exposure_status",
    ]
    write_tsv(root / "intake" / "evidence_intake_template.tsv", evidence_fields, [])

    assignment_fields = [
        "group_id",
        "query_family_id",
        "document_family_id",
        "version_family_id",
        "counterfactual_template_family_id",
        "assignment_hash",
        "assigned_cohort",
        "assignment_seed_id",
        "overlap_check_status",
        "curator_approval",
    ]
    write_tsv(root / "intake" / "family_assignment_template.tsv", assignment_fields, [])

    for cohort in ("dev", "gatea", "blind"):
        write_json(root / cohort / "cohort_manifest.json", cohort_manifest(cohort))
    for cohort in ("gatea", "blind"):
        write_json(root / cohort / "METHOD_ACCESS_LOCK.json", access_lock(cohort))

    authoritative_docs = {
        "scientific_protocol": repository_root / "docs/plans/robust-fusion-research.md",
        "engineering_protocol": repository_root / "docs/plans/robust-fusion-engineering.md",
        "progress_record": repository_root / "docs/plans/robust-fusion-todo.md",
        "data_audit": repository_root
        / "docs/reports/robust_fusion_gate_a_data_coverage_audit_2026_08_28.md",
        "asset_reconciliation": repository_root
        / "docs/reports/sqlite_share_restore_and_asset_reconciliation_2026_08_28.md",
        "internal_v6_protocol": repository_root / "docs/plans/robust-fusion-internal-stress-v6.md",
    }
    missing_docs = [str(path) for path in authoritative_docs.values() if not path.is_file()]
    if missing_docs:
        raise FileNotFoundError(f"missing authoritative documents: {missing_docs}")

    root_manifest = {
        "package_version": PACKAGE_VERSION,
        "generated_on": "2026-08-29",
        "state": "FORMALLY_ESTABLISHED_AWAITING_NEW_REAL_QUERY_INTAKE",
        "gate_eligibility": "NOT_ELIGIBLE",
        "reason_not_eligible": (
            "The reconciled share package and server-side stores contain zero query/qrel rows; "
            "no new real internal query/evidence families have been ingested or adjudicated."
        ),
        "protocol_records": {
            "scientific_protocol": SCIENTIFIC_PROTOCOL,
            "engineering_protocol": ENGINEERING_PROTOCOL,
            "progress_record": PROGRESS_RECORD,
            "data_audit_record": DATA_AUDIT_RECORD,
            "asset_reconciliation_record": ASSET_RECORD,
        },
        "authoritative_document_sha256": {
            name: sha256_file(path) for name, path in authoritative_docs.items()
        },
        "cohorts": {
            "dev": "dev/cohort_manifest.json",
            "gatea": "gatea/cohort_manifest.json",
            "blind": "blind/cohort_manifest.json",
        },
        "grouping_unit": [
            "query_family_id",
            "document_family_id",
            "version_family_id",
            "counterfactual_template_family_id",
        ],
        "intake_templates": [
            "intake/query_intake_template.tsv",
            "intake/document_intake_template.tsv",
            "intake/evidence_intake_template.tsv",
            "intake/family_assignment_template.tsv",
        ],
        "required_before_population_freeze": [
            "new real internal queries with privacy and authorization review",
            "validated source documents and deterministic chunk provenance",
            "independently reviewed correct evidence and relation labels",
            "family-level exposure and cross-cohort overlap rejection",
            "construction-yield pilot and power-supported final denominator",
        ],
        "share_package_role": [
            "empirical origin of the research question",
            "engineering feasibility and route-asset provenance",
            "budget and candidate-reconstruction substrate",
        ],
        "share_package_non_role": [
            "confirmatory query/qrel source",
            "Gate A or Gate B outcome evidence",
            "permission to recycle exposed Blind v4/v5 families",
        ],
    }
    root_manifest_path = root / "control" / "root_manifest.json"
    write_json(root_manifest_path, root_manifest)

    readme = f"""# Internal Stress v6 local package

Record: `{PACKAGE_VERSION}`

State: `FORMALLY_ESTABLISHED_AWAITING_NEW_REAL_QUERY_INTAKE`.

The dataset identity, three cohort directories, access locks, intake schemas,
source-eligibility register, and checksums now exist. The package contains no
invented query, qrel, evidence, relation label, or outcome. It is therefore not
yet eligible for Gate A or Gate B.

The 2026-08-27 SQLite share is treated as the empirical/engineering origin of the
research: it proves the historical three-route evaluation lineage and supplies
verified provenance/cache substrate. Its reconciled SQLite and old eval MySQL
both contain zero query and qrel rows, so new real query/evidence families remain
mandatory.

Never scan `gatea/` from method-development code. Never scan or disclose
`blind/` from experiment code until Gate A=Go and M1/Gate B are fully frozen.
"""
    readme_path = root / "README.md"
    readme_path.write_text(readme, encoding="utf-8")
    os.chmod(readme_path, 0o600)

    targets = sorted(
        path for path in root.rglob("*") if path.is_file() and path.name != "manifest.sha256"
    )
    checksum_path = root / "manifest.sha256"
    checksum_path.write_text(
        "".join(f"{sha256_file(path)}  {path.relative_to(root)}\n" for path in targets),
        encoding="utf-8",
    )
    os.chmod(checksum_path, 0o600)
    return root_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/robust_fusion/internal_stress_v6"),
        help="New, empty local package root",
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path("."),
        help="Repository root used to hash authoritative documents",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = initialize(args.output, args.repository_root.resolve())
    except Exception as exc:  # noqa: BLE001 - CLI should emit one concise failure
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(canonical_json({"output": str(args.output), "state": manifest["state"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
