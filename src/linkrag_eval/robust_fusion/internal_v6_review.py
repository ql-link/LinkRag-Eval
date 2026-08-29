"""合并 Internal v6 Dev 提案并生成两份隔离的人工盲审包。"""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from decimal import Decimal
from itertools import combinations
from pathlib import Path
from typing import Any

from linkrag_eval.robust_fusion.internal_v6_pilot import (
    CONFLICT_QUOTA,
    HANDBOOK_VERSION,
    FamilySpec,
    build_family_specs,
    canonical_json,
    isoformat,
    sha256_file,
    sha256_text,
    utc_now,
    validate_proposal,
)

REVIEW_PACKAGE_VERSION = "ROBUST-FUSION-INTERNAL-V6-HUMAN-REVIEW-2026-08-29-v1"
VIEW_CONTRACT_VERSION = "ROBUST-FUSION-INTERNAL-V6-REVIEW-VIEW-2026-08-29-v1"

CASE_FIELDS = [
    "case_id",
    "reviewer_id",
    "target_reference_status",
    "target_group_status",
    "evidence_locator",
    "rationale",
    "confidence",
    "adjudication_status",
    "handbook_version",
]
CANDIDATE_FIELDS = [
    "case_id",
    "candidate_id",
    "reviewer_id",
    "relevance_status",
    "target_relation",
    "conflict_type",
    "adjudicability",
    "evidence_locator",
    "rationale",
    "confidence",
    "adjudication_status",
    "handbook_version",
]
PAIR_FIELDS = [
    "case_id",
    "candidate_id_a",
    "candidate_id_b",
    "reviewer_id",
    "candidate_pair_relation",
    "evidence_locator",
    "rationale",
    "confidence",
    "adjudication_status",
    "handbook_version",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


def write_json(path: Path, value: Any) -> None:
    _write_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    _write_text(path, "".join(canonical_json(row) + "\n" for row in rows))


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    path.chmod(0o600)


def verify_run_manifest(root: Path) -> str:
    manifest_path = root / "manifest.json"
    digest = sha256_file(manifest_path)
    recorded = (root / "manifest.sha256").read_text(encoding="utf-8").strip()
    if digest != recorded:
        raise RuntimeError(f"运行根 hash 不匹配：{root}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for row in manifest["files"]:
        path = root / row["path"]
        if not path.is_file() or path.stat().st_size != row["size_bytes"]:
            raise RuntimeError(f"运行文件缺失或大小变化：{root}/{row['path']}")
        if sha256_file(path) != row["sha256"]:
            raise RuntimeError(f"运行文件 hash 变化：{root}/{row['path']}")
    return digest


def load_valid_chain(run_roots: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """按批次顺序为每个 ID 选择最早通过结构门禁的提案。"""
    if not run_roots:
        raise RuntimeError("至少需要一个运行目录")
    specs = build_family_specs()
    spec_by_id = {spec.generation_id: spec for spec in specs}
    selected: dict[str, dict[str, Any]] = {}
    run_audit: list[dict[str, Any]] = []
    previous_manifest_sha256: str | None = None
    for index, root in enumerate(run_roots):
        manifest_sha256 = verify_run_manifest(root)
        report = json.loads((root / "preliminary_report.json").read_text(encoding="utf-8"))
        if index == 0:
            if report.get("recovery_of") is not None:
                raise RuntimeError("合并链首项不得是恢复批次")
        else:
            recovery = report.get("recovery_of") or {}
            if recovery.get("source_manifest_sha256") != previous_manifest_sha256:
                raise RuntimeError(f"恢复链断裂：{root}")
            if Path(recovery.get("source_run", "")) != run_roots[index - 1]:
                raise RuntimeError(f"恢复链 source_run 不指向前一批次：{root}")
        valid_rows = read_jsonl(root / "structurally_valid_proposals.jsonl")
        rejected_rows = read_jsonl(root / "rejected_families.jsonl")
        if len(valid_rows) != report["structurally_valid_proposal_count"]:
            raise RuntimeError(f"结构通过计数不一致：{root}")
        if len(rejected_rows) != report["rejected_proposal_count"]:
            raise RuntimeError(f"结构拒绝计数不一致：{root}")
        for row in valid_rows:
            generation_id = row["generation_id"]
            if generation_id not in spec_by_id:
                raise RuntimeError(f"未知 generation_id：{generation_id}")
            proposal = row["proposal"]
            errors = validate_proposal(
                proposal,
                spec_by_id[generation_id],
                batch_id=proposal.get("batch_id", ""),
            )
            if errors:
                raise RuntimeError(f"{generation_id} 合并复核失败：{errors}")
            if generation_id not in selected:
                selected[generation_id] = {
                    "generation_id": generation_id,
                    "source_run": str(root),
                    "source_record_id": report["record_id"],
                    "source_batch_id": report["batch_id"],
                    "source_manifest_sha256": manifest_sha256,
                    "proposal_sha256": sha256_text(canonical_json(proposal)),
                    "proposal": proposal,
                }
        run_audit.append(
            {
                "run": str(root),
                "record_id": report["record_id"],
                "batch_id": report["batch_id"],
                "manifest_sha256": manifest_sha256,
                "requested_family_count": report["requested_family_count"],
                "structurally_valid_proposal_count": report["structurally_valid_proposal_count"],
                "rejected_proposal_count": report["rejected_proposal_count"],
                "usage": report["usage"],
            }
        )
        previous_manifest_sha256 = manifest_sha256

    expected_ids = set(spec_by_id)
    if set(selected) != expected_ids:
        missing = sorted(expected_ids - set(selected))
        extra = sorted(set(selected) - expected_ids)
        raise RuntimeError(f"合并后 family 不完整，missing={missing}, extra={extra}")
    ordered = [selected[spec.generation_id] for spec in specs]
    quota = Counter(row["proposal"]["primary_conflict_type"] for row in ordered)
    if quota != Counter(CONFLICT_QUOTA):
        raise RuntimeError(f"合并后冲突配额漂移：{dict(quota)}")
    _validate_cross_family_uniqueness(ordered)
    return ordered, run_audit


def _validate_cross_family_uniqueness(selected: list[dict[str, Any]]) -> None:
    text_hashes: dict[str, str] = {}
    family_fields = {
        "query_family_id": set(),
        "document_family_id": set(),
        "version_family_id": set(),
        "counterfactual_template_family_id": set(),
    }
    for row in selected:
        proposal = row["proposal"]
        locations = {
            "query": proposal["query"]["text"],
            "target": proposal["target_evidence"]["text"],
            "equivalent": proposal["equivalent_candidate"]["text"],
            "conflict": proposal["conflict_candidate"]["text"],
            "surface": proposal["surface_control_candidate"]["text"],
        }
        for name, text in locations.items():
            digest = sha256_text(text.strip())
            location = f"{row['generation_id']}:{name}"
            if digest in text_hashes:
                raise RuntimeError(f"跨 family 正文重复：{text_hashes[digest]} == {location}")
            text_hashes[digest] = location
        for field, seen in family_fields.items():
            value = proposal["family_ids"][field]
            if value in seen:
                raise RuntimeError(f"跨 family ID 重复：{field}={value}")
            seen.add(value)


def _iter_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def exact_historical_overlap_audit(
    selected: list[dict[str, Any]], history_root: Path
) -> dict[str, Any]:
    generated: dict[str, list[str]] = {}
    for row in selected:
        proposal = row["proposal"]
        fields = {
            "query": proposal["query"]["text"],
            "target": proposal["target_evidence"]["text"],
            "equivalent": proposal["equivalent_candidate"]["text"],
            "conflict": proposal["conflict_candidate"]["text"],
            "surface": proposal["surface_control_candidate"]["text"],
        }
        for field, text in fields.items():
            generated.setdefault(sha256_text(text.strip()), []).append(
                f"{row['generation_id']}:{field}"
            )

    historical_hashes: set[str] = set()
    scanned_files: list[dict[str, Any]] = []
    scanned_string_count = 0
    for path in sorted(history_root.rglob("*")):
        if not path.is_file() or path.suffix not in {".json", ".jsonl"}:
            continue
        objects: list[Any]
        if path.suffix == ".jsonl":
            objects = read_jsonl(path)
        else:
            objects = [json.loads(path.read_text(encoding="utf-8"))]
        for obj in objects:
            for text in _iter_strings(obj):
                normalized = text.strip()
                if len(normalized) >= 20:
                    historical_hashes.add(sha256_text(normalized))
                    scanned_string_count += 1
        scanned_files.append(
            {
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    overlaps = [
        {"content_sha256": digest, "generated_locations": locations}
        for digest, locations in sorted(generated.items())
        if digest in historical_hashes
    ]
    return {
        "audit_type": "exact stripped full-text SHA-256 overlap",
        "history_root": str(history_root),
        "generated_text_count": sum(len(value) for value in generated.values()),
        "historical_file_count": len(scanned_files),
        "historical_string_values_scanned": scanned_string_count,
        "overlap_count": len(overlaps),
        "overlaps": overlaps,
        "scanned_files": scanned_files,
        "semantic_or_near_duplicate_claimed": False,
    }


def _case_id(generation_id: str) -> str:
    digest = sha256_text(f"{REVIEW_PACKAGE_VERSION}|{generation_id}")[:10].upper()
    return f"RF-V6HR-{digest}"


def build_blind_case(
    proposal: Mapping[str, Any], spec: FamilySpec
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    case_id = _case_id(spec.generation_id)
    source_candidates = [
        ("equivalent", proposal["equivalent_candidate"]),
        ("conflict", proposal["conflict_candidate"]),
        ("surface_control", proposal["surface_control_candidate"]),
    ]
    source_candidates.sort(
        key=lambda item: sha256_text(
            f"{REVIEW_PACKAGE_VERSION}|{case_id}|{item[1]['candidate_id']}"
        )
    )
    candidates = []
    mapping = []
    for index, (role, source) in enumerate(source_candidates, start=1):
        alias = f"C{index}"
        candidates.append(
            {
                "candidate_id": alias,
                "display_text": source["text"],
                "method_view_metadata": {},
                "view": "method_view",
            }
        )
        mapping.append(
            {
                "case_id": case_id,
                "candidate_id": alias,
                "generation_id": spec.generation_id,
                "source_candidate_id": source["candidate_id"],
                "construction_role": role,
            }
        )
    case = {
        "case_id": case_id,
        "package_version": REVIEW_PACKAGE_VERSION,
        "query_text": proposal["query"]["text"],
        "target_references": [
            {
                "reference_id": "T1",
                "display_text": proposal["target_evidence"]["text"],
                "view": "evaluation_only",
            }
        ],
        "candidates": candidates,
        "view_contract": {
            "version": VIEW_CONTRACT_VERSION,
            "query_text": "method_view",
            "candidates[].display_text": "method_view",
            "candidates[].method_view_metadata": "method_view；本包固定为空对象",
            "target_references": ("evaluation_view；可用于资格与事实关系，不得用于 adjudicability"),
            "external_verification": "禁止",
        },
    }
    return case, mapping


def _empty_rows(
    cases: list[dict[str, Any]], reviewer_id: str
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    case_rows = []
    candidate_rows = []
    pair_rows = []
    for case in cases:
        case_id = case["case_id"]
        case_rows.append(
            {
                "case_id": case_id,
                "reviewer_id": reviewer_id,
                "target_reference_status": "",
                "target_group_status": "",
                "evidence_locator": "",
                "rationale": "",
                "confidence": "",
                "adjudication_status": "single",
                "handbook_version": HANDBOOK_VERSION,
            }
        )
        candidate_ids = sorted(candidate["candidate_id"] for candidate in case["candidates"])
        for candidate_id in candidate_ids:
            candidate_rows.append(
                {
                    "case_id": case_id,
                    "candidate_id": candidate_id,
                    "reviewer_id": reviewer_id,
                    "relevance_status": "",
                    "target_relation": "",
                    "conflict_type": "",
                    "adjudicability": "",
                    "evidence_locator": "",
                    "rationale": "",
                    "confidence": "",
                    "adjudication_status": "single",
                    "handbook_version": HANDBOOK_VERSION,
                }
            )
        for candidate_a, candidate_b in combinations(candidate_ids, 2):
            pair_rows.append(
                {
                    "case_id": case_id,
                    "candidate_id_a": candidate_a,
                    "candidate_id_b": candidate_b,
                    "reviewer_id": reviewer_id,
                    "candidate_pair_relation": "",
                    "evidence_locator": "",
                    "rationale": "",
                    "confidence": "",
                    "adjudication_status": "single",
                    "handbook_version": HANDBOOK_VERSION,
                }
            )
    return case_rows, candidate_rows, pair_rows


def _reviewer_instructions(reviewer_id: str) -> str:
    return f"""# Internal Stress v6 Dev 人工盲审说明（标注员 {reviewer_id}）

本目录是标注员 {reviewer_id} 的独立工作目录。请勿读取另一标注员目录、`facilitator/`、模型原始响应或历史答案。权威规则为 `docs/plans/robust-fusion-annotation-handbook.md` 的 `{HANDBOOK_VERSION}`；全量字段说明见 `docs/plans/robust-fusion-annotation-full-guide.md`。

## 本轮口径

- `annotation_cases.jsonl` 内的 Query 与候选正文属于 method view；`target_references` 属于 evaluation view。
- 本轮是完全虚构、自包含的微型事实世界。包内 T1 是待复核的目标参照，不联网核实，也不把现实常识带入真值判断。
- T1 可以用于判断案例资格与候选相对 T1 的事实关系；判 `adjudicability` 时不得读取 T1，只能看 Query、候选正文和包内 method-view 元数据。
- 所有候选元数据固定为空；不得根据候选编号、行序或措辞风格猜构造角色。
- `evidence_locator` 直接引用 `annotation_cases.jsonl` 中 T1/C1/C2/C3 的具体逐字片段即可，不回退外部原文位置。

## 填写顺序与数量

1. 先完成 `case_qualification.csv`：30 行。只有 `valid + unique` 才继续该案例。
2. 再完成 `candidate_annotation.csv`：90 行，严格按 relevance → target_relation → conflict_type → adjudicability 顺序。
3. 最后完成 `pair_annotation.csv`：90 行；每个案例的 C1/C2/C3 三个无序对都要独立判断。

请只填写本目录现有三张 CSV，不改变 ID、表头、行数、`reviewer_id`、`adjudication_status=single` 或 handbook 版本。完成后通知主持人锁定提交；不要自行比较或合并两位标注员答案。
"""


def materialize_review_package(
    *,
    output_dir: Path,
    run_roots: list[Path],
    history_root: Path,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"拒绝覆盖已有人工包：{output_dir}")
    selected, run_audit = load_valid_chain(run_roots)
    exposure_audit = exact_historical_overlap_audit(selected, history_root)
    if exposure_audit["overlap_count"]:
        raise RuntimeError("生成正文与历史 v5 发生精确全文重叠，拒绝发包")

    output_dir.mkdir(parents=True, mode=0o700)
    output_dir.chmod(0o700)
    facilitator_dir = output_dir / "facilitator"
    facilitator_dir.mkdir(mode=0o700)
    reviewer_dirs = {
        reviewer: output_dir / f"annotator_{reviewer.lower()}" for reviewer in ("A", "B")
    }
    for path in reviewer_dirs.values():
        path.mkdir(mode=0o700)

    specs = build_family_specs()
    mapping_rows: list[dict[str, Any]] = []
    base_cases: list[dict[str, Any]] = []
    selection_by_id = {row["generation_id"]: row for row in selected}
    for spec in specs:
        source = selection_by_id[spec.generation_id]
        case, mappings = build_blind_case(source["proposal"], spec)
        base_cases.append(case)
        for mapping in mappings:
            mapping_rows.append(
                {
                    **mapping,
                    "source_run": source["source_run"],
                    "source_batch_id": source["source_batch_id"],
                    "proposal_sha256": source["proposal_sha256"],
                    "primary_conflict_type_proposal": source["proposal"]["primary_conflict_type"],
                    "human_truth_status": "PENDING_DOUBLE_REVIEW",
                }
            )

    case_ids = [case["case_id"] for case in base_cases]
    if len(case_ids) != len(set(case_ids)):
        raise RuntimeError("盲化 case_id 碰撞")
    for reviewer, reviewer_dir in reviewer_dirs.items():
        ordered_cases = sorted(
            base_cases,
            key=lambda case: sha256_text(
                f"{REVIEW_PACKAGE_VERSION}|reviewer-{reviewer}|{case['case_id']}"
            ),
        )
        reviewer_cases = []
        for case in ordered_cases:
            copied = json.loads(json.dumps(case, ensure_ascii=False))
            copied["candidates"].sort(
                key=lambda candidate: sha256_text(
                    f"{REVIEW_PACKAGE_VERSION}|reviewer-{reviewer}|"
                    f"{case['case_id']}|{candidate['candidate_id']}"
                )
            )
            reviewer_cases.append(copied)
        write_jsonl(reviewer_dir / "annotation_cases.jsonl", reviewer_cases)
        case_rows, candidate_rows, pair_rows = _empty_rows(reviewer_cases, reviewer)
        write_csv(reviewer_dir / "case_qualification.csv", CASE_FIELDS, case_rows)
        write_csv(reviewer_dir / "candidate_annotation.csv", CANDIDATE_FIELDS, candidate_rows)
        write_csv(reviewer_dir / "pair_annotation.csv", PAIR_FIELDS, pair_rows)
        _write_text(reviewer_dir / "标注说明.md", _reviewer_instructions(reviewer))

    write_jsonl(facilitator_dir / "selected_proposals.jsonl", selected)
    write_jsonl(facilitator_dir / "blind_mapping.jsonl", mapping_rows)
    write_json(facilitator_dir / "exposure_audit.json", exposure_audit)
    write_json(facilitator_dir / "run_chain_audit.json", run_audit)

    first = run_audit[0]
    total_calls = sum(int(row["requested_family_count"]) for row in run_audit)
    total_cost = sum(Decimal(row["usage"]["estimated_cost_rmb"]) for row in run_audit)
    total_input = sum(int(row["usage"]["input_tokens"]) for row in run_audit)
    total_output = sum(int(row["usage"]["output_tokens"]) for row in run_audit)
    selected_source_counts = Counter(row["source_batch_id"] for row in selected)
    report = {
        "package_version": REVIEW_PACKAGE_VERSION,
        "generated_at": isoformat(utc_now()),
        "split_role": "internal-v6-dev controlled synthetic construction-yield pilot only",
        "family_count": len(selected),
        "candidate_count": len(selected) * 3,
        "pair_count": len(selected) * 3,
        "conflict_quota": dict(
            Counter(row["proposal"]["primary_conflict_type"] for row in selected)
        ),
        "first_pass_structurally_valid": first["structurally_valid_proposal_count"],
        "first_pass_structural_yield": first["structurally_valid_proposal_count"] / 30,
        "recovery_call_count": total_calls - 30,
        "total_model_call_count": total_calls,
        "selected_source_batch_counts": dict(selected_source_counts),
        "usage_all_attempts": {
            "input_tokens": total_input,
            "output_tokens": total_output,
            "estimated_cost_rmb": format(total_cost.quantize(Decimal("0.000001")), "f"),
        },
        "historical_exact_overlap_count": exposure_audit["overlap_count"],
        "human_review_status": "NOT_STARTED",
        "human_truth_status": "PENDING_DOUBLE_REVIEW_AND_ADJUDICATION",
        "accepted_family_count": None,
        "gate_eligibility": "NOT_ELIGIBLE",
        "gate_a_executed": False,
        "gate_b_executed": False,
        "model_output_is_truth": False,
    }
    write_json(output_dir / "package_report.json", report)
    _write_text(
        output_dir / "README.md",
        "# Internal Stress v6 Dev 双人盲审包\n\n"
        "本包包含 30 个结构合格但尚未成为人工真值的受控合成 family。"
        "标注员 A/B 只能进入各自目录；`facilitator/` 仅供主持人合并、锁定与仲裁。\n\n"
        f"- 首批结构产率：{report['first_pass_structural_yield']:.1%}（24/30）\n"
        f"- 恢复调用：{report['recovery_call_count']} 次\n"
        f"- 全部调用估算费用：人民币 {report['usage_all_attempts']['estimated_cost_rmb']} 元\n"
        "- 当前状态：等待两名人工独立复核；不得写入 GateA/Blind。\n",
    )

    manifest_rows = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name not in {
            "delivery_manifest.json",
            "delivery_manifest.sha256",
        }:
            manifest_rows.append(
                {
                    "path": path.relative_to(output_dir).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    manifest = {
        "package_version": REVIEW_PACKAGE_VERSION,
        "generated_at": isoformat(utc_now()),
        "source_run_manifests": [
            {"run": row["run"], "manifest_sha256": row["manifest_sha256"]} for row in run_audit
        ],
        "files": manifest_rows,
    }
    write_json(output_dir / "delivery_manifest.json", manifest)
    _write_text(
        output_dir / "delivery_manifest.sha256",
        sha256_file(output_dir / "delivery_manifest.json") + "\n",
    )
    return report
