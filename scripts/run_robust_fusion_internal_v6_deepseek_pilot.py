#!/usr/bin/env python3
"""运行或预检 Internal Stress v6 的 30-family DeepSeek Dev 先导。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from linkrag_eval.config import get_settings
from linkrag_eval.robust_fusion.internal_v6_pilot import (
    BATCH_ID,
    FROZEN_CONCURRENCY,
    FROZEN_FAMILY_COUNT,
    FROZEN_MAX_RETRIES,
    FROZEN_MAX_TOKENS,
    FROZEN_TEMPERATURE,
    FROZEN_TIMEOUT_SECONDS,
    build_execution_plan,
    build_family_specs,
    run_pilot,
    sha256_file,
    validate_frozen_run_config,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("dry-run", "run", "recover"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("runs/robust_fusion/internal_v6_deepseek_pilot_v2"),
    )
    parser.add_argument("--families", type=int, default=FROZEN_FAMILY_COUNT)
    parser.add_argument("--temperature", type=float, default=FROZEN_TEMPERATURE)
    parser.add_argument("--max-tokens", type=int, default=FROZEN_MAX_TOKENS)
    parser.add_argument("--timeout-seconds", type=float, default=FROZEN_TIMEOUT_SECONDS)
    parser.add_argument("--concurrency", type=int, default=FROZEN_CONCURRENCY)
    parser.add_argument("--max-retries", type=int, default=FROZEN_MAX_RETRIES)
    parser.add_argument(
        "--recover-from",
        type=Path,
        default=Path("runs/robust_fusion/internal_v6_deepseek_pilot_v2"),
    )
    return parser


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def verify_manifest(root: Path) -> str:
    manifest_path = root / "manifest.json"
    digest = sha256_file(manifest_path)
    if digest != (root / "manifest.sha256").read_text(encoding="utf-8").strip():
        raise RuntimeError(f"源批次 manifest 根 hash 不匹配：{root}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for row in manifest["files"]:
        path = root / row["path"]
        if not path.is_file() or path.stat().st_size != row["size_bytes"]:
            raise RuntimeError(f"源批次文件缺失或大小变化：{row['path']}")
        if sha256_file(path) != row["sha256"]:
            raise RuntimeError(f"源批次文件 hash 变化：{row['path']}")
    return digest


def _next_recovery_sequence(source_batch_id: str) -> int:
    if source_batch_id == BATCH_ID:
        return 1
    prefix = f"{BATCH_ID}-RECOVERY-"
    if source_batch_id.startswith(prefix):
        try:
            return int(source_batch_id.removeprefix(prefix)) + 1
        except ValueError as exc:
            raise RuntimeError(f"无法解析恢复批次序号：{source_batch_id}") from exc
    raise RuntimeError(f"源批次不属于冻结的 v2 恢复链：{source_batch_id}")


def recovery_selection(
    root: Path,
) -> tuple[list, dict[str, Any], dict[str, str], str, str]:
    manifest_sha256 = verify_manifest(root)
    report = json.loads((root / "preliminary_report.json").read_text(encoding="utf-8"))
    if report.get("status") != "INCOMPLETE_REQUIRES_RECORDED_NEW_BATCH":
        raise RuntimeError("源批次并非需要恢复的未完成状态")
    rejected = read_jsonl(root / "rejected_families.jsonl")
    rejected_ids = sorted(row["generation_id"] for row in rejected)
    if not rejected_ids:
        raise RuntimeError("源批次没有待恢复 family")
    if len(rejected_ids) != report.get("rejected_proposal_count"):
        raise RuntimeError("源批次拒绝计数与台账不一致")
    sequence = _next_recovery_sequence(report["batch_id"])
    prompt_suffixes: dict[str, str] = {}
    if sequence == 1:
        expected_error = ["response_content:无法解析为 JSON 对象"]
        if any(row.get("validation_errors") != expected_error for row in rejected):
            raise RuntimeError("首次恢复只允许补跑正文被截断、无法解析的 family")
        raw_by_id = {row["generation_id"]: row for row in read_jsonl(root / "raw_calls.jsonl")}
        for generation_id in rejected_ids:
            raw = raw_by_id[generation_id]
            choice = (raw.get("provider_response", {}).get("choices") or [{}])[0]
            if choice.get("finish_reason") != "length":
                raise RuntimeError(f"{generation_id} 不是 finish_reason=length，拒绝纳入首次恢复")
        selection_rule = "仅补跑源批次中 finish_reason=length 且正文无法解析的 family"
        technical_change = {
            "thinking": "default_enabled -> explicitly_disabled",
            "response_format": "unspecified -> json_object",
            "scientific_labels_or_estimand_changed": False,
            "prompt_semantics_changed": False,
        }
    else:
        selection_rule = "仅补跑上一恢复批次中完整响应未通过确定性结构门禁的 family"
        technical_change = {
            "thinking": "explicitly_disabled (unchanged)",
            "response_format": "json_object (unchanged)",
            "validator_error_restatement_appended": True,
            "prior_model_output_text_reused": False,
            "scientific_labels_or_estimand_changed": False,
            "constraint_or_threshold_relaxed": False,
        }
        by_id = {row["generation_id"]: row for row in rejected}
        for generation_id in rejected_ids:
            errors = by_id[generation_id].get("validation_errors") or []
            if not errors:
                raise RuntimeError(f"{generation_id} 缺确定性校验错误，拒绝结构恢复")
            bullets = "\n".join(f"- {error}" for error in errors)
            prompt_suffixes[generation_id] = (
                "修复说明：上一次完整 JSON 未通过确定性机械门禁。本次不得引用或改写"
                "上一次的正文，请从头构造同一固定 family；类别、ID、schema 和阈值均不变。\n"
                "必须消除以下格式错误：\n"
                f"{bullets}\n"
                "尤其注意：equivalent_candidate.text 必须逐字包含 target_answer；"
                "atomic_edit.after 必须与 before 互不相同且不得包含 before；"
                "冲突正文只能由一次精确替换得到，四份正文必须互不相同。"
                + (
                    "请先确定 target_answer，再把它按字符原样复制粘贴到"
                    " equivalent_candidate.text 中；不得改写、加减或替换其中任何字符。"
                    if sequence >= 3
                    else ""
                )
                + (
                    "若为否定或方向反转，禁止用‘不’加 before 的形式；请使用字符上互不包含"
                    "的反义对，例如‘开启/关闭’或‘向东/向西’。same_topic_terms 中的每个词"
                    "也必须先从 surface_control_candidate.text 逐字复制。"
                    if sequence >= 4
                    else ""
                )
            )

    specs_by_id = {spec.generation_id: spec for spec in build_family_specs()}
    try:
        specs = [specs_by_id[generation_id] for generation_id in rejected_ids]
    except KeyError as exc:
        raise RuntimeError(f"源批次含未知 generation_id：{exc}") from exc
    recovery_of = {
        "source_run": str(root),
        "source_record_id": report["record_id"],
        "source_batch_id": report["batch_id"],
        "source_manifest_sha256": manifest_sha256,
        "selection_rule": selection_rule,
        "selected_generation_ids": rejected_ids,
        "technical_change": technical_change,
        "source_manifest_bytes_sha256": hashlib.sha256(
            (root / "manifest.json").read_bytes()
        ).hexdigest(),
    }
    run_record = f"ROBUST-FUSION-INTERNAL-V6-DEEPSEEK-PILOT-2026-08-29-v2-RECOVERY-v{sequence}"
    batch_id = f"{BATCH_ID}-RECOVERY-{sequence:02d}"
    return specs, recovery_of, prompt_suffixes, run_record, batch_id


def main() -> int:
    args = build_parser().parse_args()
    settings = get_settings()
    if args.action == "dry-run":
        validate_frozen_run_config(
            endpoint=settings.judge_base_url,
            api_key=settings.judge_api_key,
            model=settings.judge_model,
            families=args.families,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout_seconds=args.timeout_seconds,
            concurrency=args.concurrency,
            max_retries=args.max_retries,
        )
        plan = build_execution_plan(endpoint=settings.judge_base_url, model=settings.judge_model)
        print(
            json.dumps(
                {
                    "status": "DRY_RUN_PASS",
                    "output": str(args.output),
                    "output_exists": args.output.exists(),
                    "family_count": len(build_family_specs()),
                    "conflict_quota": plan["conflict_quota"],
                    "model": plan["model"],
                    "endpoint_host": plan["endpoint_host"],
                    "credential_configured": bool(settings.judge_api_key),
                    "gate_a_authorized": False,
                    "gate_b_authorized": False,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.action == "recover":
        specs, recovery_of, prompt_suffixes, run_record, batch_id = recovery_selection(
            args.recover_from
        )
        validate_frozen_run_config(
            endpoint=settings.judge_base_url,
            api_key=settings.judge_api_key,
            model=settings.judge_model,
            families=args.families,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout_seconds=args.timeout_seconds,
            concurrency=args.concurrency,
            max_retries=args.max_retries,
            expected_families=len(specs),
        )
        summary = asyncio.run(
            run_pilot(
                output_dir=args.output,
                endpoint=settings.judge_base_url,
                api_key=settings.judge_api_key,
                model=settings.judge_model,
                families=args.families,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                timeout_seconds=args.timeout_seconds,
                concurrency=args.concurrency,
                max_retries=args.max_retries,
                specs=specs,
                run_record=run_record,
                batch_id=batch_id,
                recovery_of=recovery_of,
                prompt_suffix_by_generation=prompt_suffixes,
            )
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if summary["status"] == "COMPLETED_AWAITING_HUMAN_REVIEW" else 2

    validate_frozen_run_config(
        endpoint=settings.judge_base_url,
        api_key=settings.judge_api_key,
        model=settings.judge_model,
        families=args.families,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        timeout_seconds=args.timeout_seconds,
        concurrency=args.concurrency,
        max_retries=args.max_retries,
    )
    summary = asyncio.run(
        run_pilot(
            output_dir=args.output,
            endpoint=settings.judge_base_url,
            api_key=settings.judge_api_key,
            model=settings.judge_model,
            families=args.families,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout_seconds=args.timeout_seconds,
            concurrency=args.concurrency,
            max_retries=args.max_retries,
        )
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["status"] == "COMPLETED_AWAITING_HUMAN_REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())
