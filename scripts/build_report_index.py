#!/usr/bin/env python3
"""Build a durable Markdown index for all evaluation report artifacts."""

from __future__ import annotations

import argparse
import os
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs/reports/REPORT_INDEX.md"
REPORT_ROOTS = (ROOT / "runs/golden_v2", ROOT / "docs/reports")
REPORT_SUFFIXES = {".html", ".md", ".json", ".csv"}
EXCLUDED_NAMES = {"REPORT_INDEX.md"}


def _stage(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix().lower()
    if rel.startswith("docs/reports/"):
        return "00 历史实证与人工汇总"
    if (
        "ltr_fusion" in rel
        or "ltr_query_expansion" in rel
        or "learning_to_rank" in rel
    ):
        return "11 学习型融合实验"
    if "balanced_query_expansion" in rel:
        return "10 平衡 Query 扩展与标注质检"
    if "route_segment" in rel or "routing_analysis" in rel:
        return "09 Query 分桶与召回分流分析"
    if "rerank" in rel:
        return "08 Rerank 候选截断与效果评测"
    if "tune" in rel or "hybrid_weight" in rel or "sparse_threshold" in rel:
        return "07 召回参数与融合策略调优"
    if "acceptance" in rel:
        return "06 阶段验收与最终对比"
    if "hard" in rel:
        return "05 Hard Set 构建、质检与评测"
    if "realistic" in rel:
        return "04 Realistic Set 构建、质检与评测"
    if any(token in rel for token in ("eval_", "blind_run", "/results/", "/snapshots/")):
        return "03 检索运行、Blind 与规模对比"
    if any(
        token in rel
        for token in ("/corpus/", "corpus_missing", "synth_background", "export_report")
    ):
        return "01 语料生成、导出与规模扩展"
    if any(
        token in rel
        for token in (
            "candidate",
            "judgment",
            "build_report",
            "golden_draft",
            "golden_live",
            "golden_pilot",
            "/golden/",
        )
    ):
        return "02 黄金集候选、标注与构建"
    if any(token in rel for token in ("synth_", "scale_100k", "spark_corpus")):
        return "01 语料生成、导出与规模扩展"
    return "12 其他阶段产物"


def _purpose(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix().lower()
    name = path.name.lower()

    rules = (
        (
            ("ltr_cross_validation", "ltr_fusion", "ltr_query_expansion"),
            "学习型融合的数据扩展、候选缓存、交叉验证结果与固定 Hybrid 对比。",
        ),
        (("routing_analysis", "route_segment"), "按 Query 类型/长度比较单路与 Hybrid，支撑分流规则设计。"),
        (("rerank",), "记录 Rerank 候选截断、参数搜索或重排效果，用于判断是否启用重排。"),
        (("recall_tuning", "weighted", "hybrid_weight", "sparse_threshold"), "记录召回阈值、TopK、权重或融合参数搜索结果。"),
        (("acceptance_report", "acceptance_summary"), "汇总阶段验收指标、结论、风险与待办。"),
        (("candidate_pool_report",), "统计候选池覆盖率、候选来源及未覆盖 Query，供后续标注使用。"),
        (("review_queue",), "记录需要复核的标注冲突或未解决样本。"),
        (("adjudication",), "记录争议样本裁决结果及裁决后的标注状态。"),
        (("judgment",), "记录模型/人工标注批次的完成率、失败项或标注质量。"),
        (("qc",), "黄金集或标注质量门禁，检查未解决率、随机负例误判率及结构完整性。"),
        (("build_report",), "记录黄金集构建输入、有效样本数、拆分结果及丢弃原因。"),
        (("diff_report",), "比较预期语料与实际语料差异，定位缺失或重复数据。"),
        (("export_report", "corpus_export_report"), "记录语料导出的数量、范围和异常，供规模扩展验收。"),
        (("synth_report",), "记录合成干扰语料的生成规模、分布和质量统计。"),
        (("synth_manifest", "manifest"), "固定该阶段语料清单与来源，支持复现和审计。"),
        (("preflight",), "运行前置检查结果，确认数据、配置和依赖是否满足评测条件。"),
        (("pilot_plan",), "试运行计划及数据分批方案，用于控制正式评测前的范围。"),
        (("coverage",), "记录正确 Chunk 在各召回通道和候选深度中的覆盖情况。"),
    )
    for tokens, purpose in rules:
        if any(token in rel for token in tokens):
            return purpose

    if "/snapshots/" in rel:
        return "冻结本次评测快照，保留逐题结果和运行上下文以便复现。"
    if "/results/" in rel or name.endswith(".csv"):
        return "机器可读评测结果，供指标复算、差异分析和后续报告生成。"
    if path.suffix.lower() == ".html":
        return "人读版测试报告，展示聚合指标、逐题诊断和阶段结论。"
    if path.suffix.lower() == ".md":
        return "阶段说明或人读版结果摘要，保留口径、结论和决策依据。"
    return "机器可读阶段产物，保留测试参数、统计结果和复现依据。"


def discover_reports() -> list[Path]:
    reports: set[Path] = set()
    for base in REPORT_ROOTS:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if (
                path.is_file()
                and path.suffix.lower() in REPORT_SUFFIXES
                and path.name not in EXCLUDED_NAMES
            ):
                reports.add(path.resolve())
    return sorted(reports, key=lambda path: path.relative_to(ROOT).as_posix())


def _link(from_path: Path, target: Path) -> str:
    return Path(os.path.relpath(target, start=from_path.parent)).as_posix()


def render_index(reports: list[Path], output: Path = DEFAULT_OUTPUT) -> str:
    grouped: dict[str, list[Path]] = defaultdict(list)
    for report in reports:
        grouped[_stage(report)].append(report)

    suffix_counts = Counter(path.suffix.lower().lstrip(".") for path in reports)
    summary = "，".join(
        f"{suffix.upper()} {suffix_counts.get(suffix, 0)}"
        for suffix in ("html", "md", "json", "csv")
    )
    lines = [
        "# LinkRag-Eval 测试报告索引",
        "",
        "> 本索引覆盖 `runs/golden_v2/` 与 `docs/reports/` 下的阶段报告。",
        "> 历史报告必须保留原路径；新一轮测试使用新的 run/batch 目录或带时间戳文件名，禁止覆盖旧报告。",
        "",
        f"当前共收录 **{len(reports)}** 个报告及机器可读配套产物：{summary}。",
        "",
        "更新索引：`python3 scripts/build_report_index.py`",
        "校验索引：`python3 scripts/build_report_index.py --check`",
        "",
        "## 阶段导航",
        "",
    ]
    for stage in sorted(grouped):
        anchor = stage.lower().replace(" ", "-")
        lines.append(f"- [{stage}](#{anchor})：{len(grouped[stage])} 个产物")

    for stage in sorted(grouped):
        lines.extend(("", f"## {stage}", "", "| 报告 | 格式 | 作用 |", "| --- | --- | --- |"))
        for report in grouped[stage]:
            rel = report.relative_to(ROOT).as_posix()
            link = _link(output, report)
            label = rel.replace("|", "\\|")
            purpose = _purpose(report).replace("|", "\\|")
            lines.append(
                f"| [{label}](<{link}>) | `{report.suffix.lower().lstrip('.')}` | {purpose} |"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail when the index is stale")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    output = args.output.resolve()
    content = render_index(discover_reports(), output)
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != content:
            print(f"report index is stale: {output}")
            return 1
        print(f"report index is current: {output}")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
