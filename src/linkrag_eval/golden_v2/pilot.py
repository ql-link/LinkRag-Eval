"""Golden V2 pilot 编排与本地预检。

这里不直接连接 MySQL/Qdrant/LLM,只做本地文件、配置和命令计划生成。实际执行仍由
各子命令负责,以便每一步都能单独复验和回滚。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    status: str
    message: str


@dataclass(frozen=True)
class PilotPreflightReport:
    status: str
    checks: list[PreflightCheck]
    next_actions: list[str]
    report_path: str | None = None
    markdown_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["checks"] = [asdict(check) for check in self.checks]
        return data

    def summary(self) -> str:
        counts = {status: sum(1 for c in self.checks if c.status == status) for status in ("pass", "warn", "fail")}
        return (
            f"Golden V2 pilot preflight: status={self.status} checks={counts} "
            f"next_actions={len(self.next_actions)}"
        )


@dataclass(frozen=True)
class PilotPlanReport:
    stage: str
    dataset_ids: list[int]
    out_dir: str
    commands: list[str]
    plan_path: str
    script_path: str
    markdown_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        return f"Golden V2 pilot plan: stage={self.stage} dataset_ids={self.dataset_ids} commands={len(self.commands)}"


def run_pilot_preflight(
    *,
    settings: Any,
    seeds_path: str | Path,
    dataset_ids: Sequence[int],
    reviewer_model: str | None,
    require_alt_embedding: bool = True,
    min_seed_count: int = 200,
    report_out: str | Path | None = None,
    markdown_out: str | Path | None = None,
) -> PilotPreflightReport:
    checks: list[PreflightCheck] = []
    seed_count = _count_jsonl(Path(seeds_path)) if Path(seeds_path).exists() else 0
    _add(
        checks,
        "query_seeds",
        seed_count >= min_seed_count,
        f"{seeds_path} rows={seed_count}, min={min_seed_count}",
    )
    _add(checks, "dataset_ids", bool(dataset_ids), f"dataset_ids={list(dataset_ids)}")
    _add(
        checks,
        "eval_mysql_db",
        getattr(settings, "db_name", "") != "tolink_rag_db",
        f"db_name={getattr(settings, 'db_name', '')}",
    )
    _add(
        checks,
        "qdrant_eval_prefix",
        "eval" in str(getattr(settings, "qdrant_prefix", "")),
        f"qdrant_prefix={getattr(settings, 'qdrant_prefix', '')}",
    )
    _add(
        checks,
        "judge_config",
        all(
            str(getattr(settings, field, "")).strip()
            for field in ("judge_base_url", "judge_api_key", "judge_model")
        ),
        f"judge_model={getattr(settings, 'judge_model', '') or '(空)'}",
    )
    if reviewer_model:
        _add(
            checks,
            "reviewer_model",
            reviewer_model != getattr(settings, "judge_model", ""),
            f"reviewer_model={reviewer_model}, judge_model={getattr(settings, 'judge_model', '')}",
            warn_on_false=True,
        )
    else:
        checks.append(PreflightCheck("reviewer_model", "fail", "必须指定第二判官 reviewer_model"))
    alt_required_missing = False
    if require_alt_embedding:
        alt_provider = str(getattr(settings, "alt_embed_provider", "openai") or "openai")
        required_fields = ["alt_embed_base_url", "alt_embed_model"]
        if alt_provider == "openai":
            required_fields.append("alt_embed_api_key")
        alt_ready = all(str(getattr(settings, field, "")).strip() for field in required_fields)
        different_model = getattr(settings, "alt_embed_model", "") != getattr(settings, "embed_model", "")
        alt_required_missing = not (alt_ready and different_model)
        _add(
            checks,
            "alt_embedding_config",
            alt_ready and different_model,
            (
                f"alt_embed_provider={alt_provider}, "
                f"alt_embed_model={getattr(settings, 'alt_embed_model', '') or '(空)'}, "
                f"embed_model={getattr(settings, 'embed_model', '') or '(空)'}"
            ),
        )
    if getattr(settings, "bm25_mode", "") != "sqlite_fts5":
        checks.append(
            PreflightCheck(
                "bm25_mode",
                "warn",
                f"建议 EVAL_BM25_MODE=sqlite_fts5, 当前={getattr(settings, 'bm25_mode', '')}",
            )
        )
    else:
        checks.append(PreflightCheck("bm25_mode", "pass", "sqlite_fts5"))

    status = "fail" if any(c.status == "fail" for c in checks) else ("warn" if any(c.status == "warn" for c in checks) else "pass")
    next_actions = _next_actions(
        status=status,
        seeds_path=seeds_path,
        dataset_ids=dataset_ids,
        reviewer_model=reviewer_model,
        alt_required_missing=alt_required_missing,
        seed_count=seed_count,
        min_seed_count=min_seed_count,
    )
    report = PilotPreflightReport(
        status=status,
        checks=checks,
        next_actions=next_actions,
        report_path=str(report_out) if report_out else None,
        markdown_path=str(markdown_out) if markdown_out else None,
    )
    if report_out:
        path = Path(report_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if markdown_out:
        path = Path(markdown_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_preflight_markdown(report), encoding="utf-8")
    return report


def build_pilot_plan(
    *,
    out_dir: str | Path,
    dataset_ids: Sequence[int],
    reviewer_model: str,
    raw_query_input: str | Path | None = None,
    seeds_path: str | Path | None = None,
    source: str = "log",
    query_field: str = "query",
    id_field: str | None = None,
    stage: str = "pilot",
    route_top_n: int = 50,
    random_n: int = 20,
    max_candidates_per_query: int = 80,
    limit_queries: int | None = None,
    top_k: int = 10,
    medium_dataset_id_start: int = 992000,
    medium_target_chunks: int = 20_000,
    write_markdown: bool = True,
) -> PilotPlanReport:
    if not dataset_ids:
        raise ValueError("dataset_ids 不能为空")
    if not reviewer_model.strip():
        raise ValueError("reviewer_model 不能为空")
    if raw_query_input is None and seeds_path is None:
        raise ValueError("raw_query_input 和 seeds_path 至少提供一个")

    out = Path(out_dir)
    seeds_dir = out / "seeds"
    candidates_dir = out / "candidates"
    judgments_dir = out / "judgments"
    golden_dir = out / "golden"
    reports_dir = out / "reports"
    scale_dir = out / "medium_20k_plan"
    query_seeds = Path(seeds_path) if seeds_path else seeds_dir / "query_seeds.jsonl"
    dataset_arg = ",".join(str(i) for i in dataset_ids)
    limit_arg = f" --limit-queries {int(limit_queries)}" if limit_queries else ""

    commands: list[str] = []
    if raw_query_input is not None:
        id_arg = f" --id-field {id_field}" if id_field else ""
        commands.append(
            "linkrag-eval golden-v2 seed-import "
            f"--input {raw_query_input} --source {source} --query-field {query_field}{id_arg} "
            f"--out {query_seeds} --report-out {seeds_dir / 'seed_import_report.json'}"
        )
    commands.extend(
        [
            (
                "linkrag-eval golden-v2 pilot-preflight "
                f"--seeds {query_seeds} --dataset-ids {dataset_arg} "
                f"--reviewer-model {reviewer_model} "
                f"--report-out {reports_dir / 'pilot_preflight.json'} "
                f"--markdown-out {reports_dir / 'pilot_preflight.md'}"
            ),
            f"linkrag-eval bm25-backfill --dataset-ids {dataset_arg} --batch 1000",
            f"linkrag-eval golden-v2 alt-embed-backfill --dataset-ids {dataset_arg} --batch 100",
            (
                "linkrag-eval golden-v2 candidate-pool-live "
                f"--seeds {query_seeds} --dataset-ids {dataset_arg} "
                "--sources bm25,dense,sparse,alt_embedding "
                "--dense-score-threshold 0.0 --sparse-score-threshold 0.0 "
                "--alt-score-threshold -1.0 "
                f"--route-top-n {route_top_n} --random-n {random_n}{limit_arg} "
                f"--out {candidates_dir / 'candidate_pool.jsonl'} "
                f"--report-out {candidates_dir / 'candidate_pool_report.json'}"
            ),
            (
                "linkrag-eval golden-v2 label "
                f"--candidates {candidates_dir / 'candidate_pool.jsonl'} "
                f"--max-candidates-per-query {max_candidates_per_query}{limit_arg} "
                f"--out {judgments_dir / 'deepseek_judgments.jsonl'} "
                f"--report-out {judgments_dir / 'deepseek_judgments_report.json'}"
            ),
            (
                "linkrag-eval golden-v2 qc "
                f"--judgments {judgments_dir / 'deepseek_judgments.jsonl'} "
                f"--report-out {judgments_dir / 'deepseek_judgments_qc.json'} "
                f"--markdown-out {judgments_dir / 'deepseek_judgments_qc.md'}"
            ),
            (
                "linkrag-eval golden-v2 review-queue "
                f"--judgments {judgments_dir / 'deepseek_judgments.jsonl'} "
                f"--out {judgments_dir / 'review_queue.jsonl'} "
                f"--report-out {judgments_dir / 'review_queue_report.json'}"
            ),
            (
                "linkrag-eval golden-v2 review-label "
                f"--review-queue {judgments_dir / 'review_queue.jsonl'} "
                f"--candidate-pool {candidates_dir / 'candidate_pool.jsonl'} "
                f"--reviewer-model {reviewer_model} "
                f"--out {judgments_dir / 'review_judgments.jsonl'} "
                f"--report-out {judgments_dir / 'review_judgments_report.json'}"
            ),
            (
                "linkrag-eval golden-v2 adjudicate "
                f"--judgments {judgments_dir / 'deepseek_judgments.jsonl'} "
                f"--reviews {judgments_dir / 'review_judgments.jsonl'} "
                "--policy manual_on_conflict "
                f"--out {judgments_dir / 'adjudicated_judgments.jsonl'} "
                f"--conflict-out {judgments_dir / 'manual_conflicts.jsonl'} "
                f"--report-out {judgments_dir / 'adjudication_report.json'}"
            ),
            (
                "linkrag-eval golden-v2 build "
                f"--judgments {judgments_dir / 'adjudicated_judgments.jsonl'} "
                f"--out-dir {golden_dir} --tune-ratio 0.70"
            ),
            (
                "linkrag-eval run "
                f"--golden {golden_dir / 'realistic_blind.jsonl'} "
                f"--run-label {stage}-realistic-blind --dataset golden_v2_{stage} "
                f"--top-k {top_k} --precheck --require-chunk-references "
                "--sparse-score-threshold 0.0"
            ),
            (
                "linkrag-eval golden-v2 scale-plan "
                f"--stage medium_20k --target-chunks {medium_target_chunks} "
                f"--dataset-id-start {medium_dataset_id_start} --batch-chunks 5000 "
                f"--query-seed-target 1000 --out-dir {scale_dir}"
            ),
        ]
    )
    out.mkdir(parents=True, exist_ok=True)
    report = PilotPlanReport(
        stage=stage,
        dataset_ids=list(dataset_ids),
        out_dir=str(out),
        commands=commands,
        plan_path=str(out / "pilot_plan.json"),
        script_path=str(out / "pilot_commands.sh"),
        markdown_path=str(out / "pilot_plan.md") if write_markdown else None,
    )
    Path(report.plan_path).write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(report.script_path).write_text(_script(commands), encoding="utf-8")
    if report.markdown_path:
        Path(report.markdown_path).write_text(_plan_markdown(report), encoding="utf-8")
    return report


def _add(
    checks: list[PreflightCheck],
    name: str,
    ok: bool,
    message: str,
    *,
    warn_on_false: bool = False,
) -> None:
    checks.append(PreflightCheck(name, "pass" if ok else ("warn" if warn_on_false else "fail"), message))


def _next_actions(
    *,
    status: str,
    seeds_path: str | Path,
    dataset_ids: Sequence[int],
    reviewer_model: str | None,
    alt_required_missing: bool,
    seed_count: int,
    min_seed_count: int,
) -> list[str]:
    actions: list[str] = []
    if seed_count < min_seed_count:
        actions.append(
            f"补足真实 query seeds: 当前 {seed_count}, 目标至少 {min_seed_count};"
            "用 golden-v2 seed-import 从日志/客服/开源 query 导入。"
        )
    if alt_required_missing:
        actions.append(
            "补齐 .env.eval 中 EVAL_ALT_EMBED_PROVIDER / EVAL_ALT_EMBED_BASE_URL / "
            "EVAL_ALT_EMBED_MODEL / EVAL_ALT_EMBED_DIM;openai provider 还需要 "
            "EVAL_ALT_EMBED_API_KEY。模型必须与 EVAL_EMBED_MODEL 不同。"
        )
    if not reviewer_model:
        actions.append("指定 --reviewer-model,且正式运行应与 EVAL_JUDGE_MODEL 不同。")
    if status == "pass":
        dataset_arg = ",".join(str(i) for i in dataset_ids)
        actions.extend(
            [
                f"运行: linkrag-eval bm25-backfill --dataset-ids {dataset_arg} --batch 1000",
                f"运行: linkrag-eval golden-v2 alt-embed-backfill --dataset-ids {dataset_arg} --batch 100",
                (
                    "运行: linkrag-eval golden-v2 candidate-pool-live "
                    f"--seeds {seeds_path} --dataset-ids {dataset_arg} "
                    "--sources bm25,dense,sparse,alt_embedding "
                    "--dense-score-threshold 0.0 --sparse-score-threshold 0.0 "
                    "--alt-score-threshold -1.0"
                ),
            ]
        )
    return actions


def _count_jsonl(path: Path) -> int:
    try:
        with path.open(encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())
    except FileNotFoundError:
        return 0


def _preflight_markdown(report: PilotPreflightReport) -> str:
    lines = ["# Golden V2 Pilot Preflight", "", f"- status: `{report.status}`", "", "## Checks", ""]
    lines.extend(f"- `{c.status}` {c.name}: {c.message}" for c in report.checks)
    lines.extend(["", "## Next Actions", ""])
    lines.extend(f"- {item}" for item in report.next_actions)
    lines.append("")
    return "\n".join(lines)


def _plan_markdown(report: PilotPlanReport) -> str:
    lines = [
        "# Golden V2 Pilot Plan",
        "",
        f"- stage: `{report.stage}`",
        f"- dataset_ids: `{','.join(str(i) for i in report.dataset_ids)}`",
        "",
        "## Commands",
        "",
        "```bash",
        *report.commands,
        "```",
        "",
    ]
    return "\n".join(lines)


def _script(commands: list[str]) -> str:
    return "#!/usr/bin/env bash\nset -euo pipefail\n\n" + "\n\n".join(commands) + "\n"
