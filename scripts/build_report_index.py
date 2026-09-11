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

# 只维护已读报告的选读信息；不复制指标或动态进度。
# 同 stem 的 MD/HTML 是同一题目的格式入口，原文件均保留。
REPORT_GUIDES = {
    "llm_judge_pilot_2026_09_10": (
        "英文研究与 NevIR", "读文本的判断器能否补上 38 维缺失的条件信号？",
        "L1 单段判断、固定融合前 K 重排、判断列进 LTR；区分原确认、失败重试与后补复验。",
    ),
    "nevir_subject_binding_pilot_2026_09_08": (
        "英文研究与 NevIR", "同一自动事实上的主体聚合是否提供增量？",
        "五组开发探索、人审敏感性及 v2/v3 工程修复与固定基础匹配对照；不属于独立确认。",
    ),
    "nevir_offline_diagnostic_2026_09_07": (
        "英文研究与 NevIR", "开发快照中，基线评分与特征响应是什么？",
        "§1–6 为历史 A/B，§7 为中文／英文基线；机械诊断，不是语义归因结论。",
    ),
    "nevir_english_features_2026_09_07": (
        "英文研究与 NevIR", "基础英文适配相比同条件 legacy 重训如何？",
        "同监督、同配置的开发对照；不属于独立验证。",
    ),
    "nevir_same38_retraining_2026_09_07": (
        "英文研究与 NevIR", "保持 38 维规则，只重训权重的结果如何？",
        "历史 A/B 确认；不是中文／英文基线对照，确认材料已使用。",
    ),
    "nevir_controlled_retrieval_2026_09_07": (
        "英文研究与 NevIR", "英文链路和 NevIR 错排最初如何复现？",
        "普通英文能力检查＋20 对 NevIR；不能外推自然错误率。",
    ),
    "nevir_suitability_2026_09_07": (
        "英文研究与 NevIR", "NevIR 的划分、来源重叠和标签边界是什么？",
        "数据与固定样例审计，不是模型效果实验。",
    ),
    "blind_v4_final_acceptance_2026_07_24": (
        "历史排序与召回比较", "旧 Blind v4 如何比较 Hybrid 与 LambdaMART？",
        "旧数据和旧模型的工程门禁、效果及区间。",
    ),
    "corpus_scale_800_vs_2000": (
        "历史排序与召回比较", "增加语料干扰规模会怎样影响召回？",
        "同一 394 查询，800／2000 chunk 每域的历史比较。",
    ),
    "doubao_retrieval_eval_500": (
        "历史排序与召回比较", "豆包稀疏检索在旧基准上表现怎样？",
        "旧 500 题、四领域；单一稀疏模型的评测。",
    ),
    "fusion_strategy_comparison_2026_07_02": (
        "历史排序与召回比较", "RRF 与 weighted_score 怎样比较？",
        "同候选、同参数，无 rerank；旧四域基准。",
    ),
    "multi_route_recall_comparison_2026_07_05": (
        "历史排序与召回比较", "Dense、Dense＋BM25、三路召回怎样比较？",
        "旧 394 条 doc 粒度查询；保留当时召回与存储配置。",
    ),
    "recall_parameter_tuning_2026_07_02": (
        "历史排序与召回比较", "召回阈值与 TopK 当时如何调参？",
        "旧四域 394 查询、720 组网格；历史参数不直接沿用。",
    ),
    "recall_routes_2way_vs_3way": (
        "历史排序与召回比较", "BM25＋Sparse 增加 Dense 后有什么变化？",
        "旧 500 题的两路／三路比较，区别于 394 题实验。",
    ),
    "sparse_model_comparison_bge_vs_doubao": (
        "历史排序与召回比较", "BGE-M3 与豆包稀疏模型怎样比较？",
        "稀疏编码器对照；其他检索逻辑固定。",
    ),
    "weighted_score_parameter_tuning_2026_07_02": (
        "历史排序与召回比较", "分数融合的权重与候选参数如何选过？",
        "旧 394 题、Dense／Sparse 权重搜索；不是当前三路新结论。",
    ),
    "golden_v2_realistic_991004_run_2026_07_10": (
        "历史数据与标签检查", "旧 Realistic 标注集如何形成？",
        "50 查询的池化标注与 Tune／Blind 划分记录。",
    ),
    "internal_v6_dev_route_evidence_v5_verification_2026_08_29": (
        "历史数据与标签检查", "Internal v6-Dev 的三路证据核验了什么？",
        "仅供旧 Dev 测量与流程校准，不是 Gate A/B 验收。",
    ),
    "label_reliability_pooled_relabel": (
        "历史数据与标签检查", "旧公开数据的漏标如何检查？",
        "模型辅助池化重标；不能当成人工金标。",
    ),
    "robust_fusion_candidate_snapshot_field_gap_audit_2026_08_28": (
        "历史数据与标签检查", "原候选快照缺哪些字段？",
        "当时的契约与字段责任审计，不是当前源码清单。",
    ),
    "robust_fusion_gate_a_data_coverage_audit_2026_08_28": (
        "历史数据与标签检查", "旧 Gate A 材料与标签覆盖缺什么？",
        "历史数据审计，不是 Gate A 封存或运行结果。",
    ),
    "blind_v5_production_contract_acceptance_2026_07_28": (
        "历史工程交付与恢复", "中文基线的原生产契约如何验收？",
        "原 v3 的 38 维、无 Alias 与工程交付；不是英文模型验收。",
    ),
    "live_smoke_2026_07_02": (
        "历史工程交付与恢复", "旧活栈链路当时是否跑通？",
        "2026-07 的旧 MySQL 环境；当前存储看工程架构。",
    ),
    "sqlite_share_restore_and_asset_reconciliation_2026_08_28": (
        "历史工程交付与恢复", "旧 SQLite 与检索资产如何恢复和核对？",
        "当时的资产盘点；当前备份位置查恢复说明。",
    ),
}
GUIDE_STAGES = tuple(dict.fromkeys(guide[0] for guide in REPORT_GUIDES.values()))
GUIDE_ORDER = {stem: i for i, stem in enumerate(REPORT_GUIDES)}


def _stage(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix().lower()
    if rel.startswith("docs/reports/"):
        return REPORT_GUIDES[path.stem][0] if path.stem in REPORT_GUIDES else "待补选读说明"
    if "acceptance" in rel:
        return "06 阶段验收与最终对比"
    if "ltr_fusion" in rel or "ltr_query_expansion" in rel or "learning_to_rank" in rel:
        return "11 学习型融合实验"
    if "balanced_query_expansion" in rel:
        return "10 平衡 Query 扩展与标注质检"
    if "route_segment" in rel or "routing_analysis" in rel:
        return "09 Query 分桶与召回分流分析"
    if "rerank" in rel:
        return "08 Rerank 候选截断与效果评测"
    if "tune" in rel or "hybrid_weight" in rel or "sparse_threshold" in rel:
        return "07 召回参数与融合策略调优"
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

    if rel.startswith("docs/reports/"):
        guide = REPORT_GUIDES.get(path.stem)
        return guide[2] if guide else "仅自动发现，尚未填写实验范围与证据用途；先核对正文。"

    if name == "robust_fusion_r2_human_review_pre_adjudication_2026_08_29.md":
        return "历史 R2：四份提交先锁后验、机械预审和 relation 7 / similarity 96 待仲裁；退役不等于仲裁完成。"
    if name == "robust_fusion_r2_similarity_failure_diagnostic_2026_08_29.md":
        return "历史 R1 相似度失败诊断；文件名含 R2 表示后续重设计背景，不是 R2 最终测量结果。"

    rules = (
        (("acceptance_report", "acceptance_summary"), "汇总阶段验收指标、结论、风险与待办。"),
        (
            ("ltr_cross_validation", "ltr_fusion", "ltr_query_expansion"),
            "学习型融合的数据扩展、候选缓存、交叉验证结果与固定 Hybrid 对比。",
        ),
        (
            ("routing_analysis", "route_segment"),
            "按 Query 类型/长度比较单路与 Hybrid，支撑分流规则设计。",
        ),
        (("rerank",), "记录 Rerank 候选截断、参数搜索或重排效果，用于判断是否启用重排。"),
        (
            ("recall_tuning", "weighted", "hybrid_weight", "sparse_threshold"),
            "记录召回阈值、TopK、权重或融合参数搜索结果。",
        ),
        (("candidate_pool_report",), "统计候选池覆盖率、候选来源及未覆盖 Query，供后续标注使用。"),
        (("review_queue",), "记录需要复核的标注冲突或未解决样本。"),
        (("adjudication",), "记录争议样本裁决结果及裁决后的标注状态。"),
        (("judgment",), "记录模型/人工标注批次的完成率、失败项或标注质量。"),
        (("qc",), "黄金集或标注质量门禁，检查未解决率、随机负例误判率及结构完整性。"),
        (("build_report",), "记录黄金集构建输入、有效样本数、拆分结果及丢弃原因。"),
        (("diff_report",), "比较预期语料与实际语料差异，定位缺失或重复数据。"),
        (
            ("export_report", "corpus_export_report"),
            "记录语料导出的数量、范围和异常，供规模扩展验收。",
        ),
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
    grouped: dict[str, dict[Path, list[Path]]] = defaultdict(dict)
    for report in sorted(set(reports)):
        # 只合并已核对的正式报告格式；机器产物的同名文件不推定为一份报告。
        known = (
            report.parent == ROOT / "docs/reports"
            and report.stem in REPORT_GUIDES
            and report.suffix.lower() in {".md", ".html"}
        )
        family = report.with_suffix("") if known else report
        grouped[_stage(report)].setdefault(family, []).append(report)

    suffix_counts = Counter(path.suffix.lower().lstrip(".") for path in reports)
    summary = "，".join(
        f"{suffix.upper()} {suffix_counts.get(suffix, 0)}"
        for suffix in ("html", "md", "json", "csv")
    )
    topic_count = sum(len(families) for families in grouped.values())
    status = _link(output, ROOT / "docs/CURRENT_STATUS.md")
    catalog = _link(output, ROOT / "docs/DOCUMENT_CATALOG.md")
    experiment_log = _link(output, ROOT / "docs/experiments/EXPERIMENT_LOG.md")
    runs = _link(output, ROOT / "runs/post_recall/README.md")
    stages = sorted(grouped, key=lambda stage: (
        GUIDE_STAGES.index(stage) if stage in GUIDE_STAGES else len(GUIDE_STAGES), stage,
    ))
    lines = [
        "# 实验报告选读",
        "",
        f"先按要核对的问题选择。当前工作安排见[当前状态]({status})，其他文档见[文档目录]({catalog})。",
        f"按次回顾实验（含长报告中的多轮对照、失败与中止）或登记新实验，见[实验台账]({experiment_log})。",
        "下表说明报告所属实验的口径；历史报告中的下一步不自动成为当前任务。",
        "",
        f"当前共收录 **{len(reports)}** 个产物，按 **{topic_count}** 个题目展示：{summary}。",
        "同名 MD／HTML 并列，优先读 MD，需要版式展示时选 HTML。",
        f"扫描范围仍为 `docs/reports/`、`runs/golden_v2/`；NevIR 运行产物从[实验目录]({runs})查找，不在这里重复逐文件列举。",
        "",
        "更新：`python3 scripts/build_report_index.py`；校验：`python3 scripts/build_report_index.py --check`。",
        "选读说明维护在生成脚本的 `REPORT_GUIDES`；新增报告自动收录，未填写说明的列入“待补选读说明”。",
        "",
        "## 按问题选择",
        "",
    ]
    for stage in stages:
        anchor = stage.lower().replace(" ", "-")
        lines.append(f"- [{stage}](#{anchor})：{len(grouped[stage])} 个题目")

    for stage in stages:
        lines.extend(("", f"## {stage}", "", "| 要核对的问题 | 阅读入口 | 口径与边界 |",
                      "| --- | --- | --- |"))
        families = sorted(grouped[stage].items(), key=lambda item: (
            GUIDE_ORDER.get(item[0].stem, len(GUIDE_ORDER)), item[0].as_posix(),
        ))
        for _, variants in families:
            first = variants[0]
            guide = REPORT_GUIDES.get(first.stem) if first.parent == ROOT / "docs/reports" else None
            question = guide[1] if guide else first.relative_to(ROOT).as_posix()
            question = question.replace("|", "\\|")
            scope = _purpose(first).replace("|", "\\|")
            formats = sorted(variants, key=lambda path: (path.suffix != ".md", path.suffix))
            links = " · ".join(
                f"[{path.suffix[1:].upper()}](<{_link(output, path)}>)" for path in formats
            )
            lines.append(f"| {question} | {links} | {scope} |")
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
