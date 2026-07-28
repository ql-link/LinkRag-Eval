#!/usr/bin/env python3
"""Render the Codex 5.3 query-expansion progress and interim LTR comparison."""

from __future__ import annotations

import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = (
    ROOT
    / "runs/golden_v2/scale_100k_991004/scale_20k_overnight/ltr_query_expansion_2000"
)
OLD = (
    ROOT
    / "runs/golden_v2/scale_100k_991004/scale_20k_overnight/"
    "balanced_query_expansion/balanced_final_600/ltr_fusion_v1"
)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def main() -> int:
    generation = _read(RUN / "generation_report.json")
    build = _read(RUN / "final/build_report_partial.json")
    cv420 = _read(OLD / "cv_v1/ltr_cross_validation.json")
    external420 = _read(
        OLD / "external_realistic_blind_116/evaluation/ltr_external_evaluation.json"
    )
    cv1050 = _read(RUN / "ltr_partial_1050/cv/ltr_cross_validation.json")
    external1050 = _read(
        RUN / "ltr_partial_1050/external_realistic_blind_116/ltr_external_evaluation.json"
    )
    summary = {
        "target_total": 2000,
        "base_samples": 420,
        "generated_reserve_queries": generation["generated"],
        "generator_model": generation["model"],
        "blind_validated_queries": build["validated_query_coverage"],
        "accepted_unique_new_queries": build["new_samples"],
        "interim_training_samples": build["total_samples"],
        "spark_quota_resume_at": "2026-07-23 23:25 Asia/Shanghai",
        "cv_420": cv420["overall"],
        "cv_1050": cv1050["overall"],
        "external_420": external420["overall"],
        "external_1050": external1050["overall"],
        "external_420_strict": external420["strict_no_evidence_overlap"],
        "external_1050_strict": external1050["strict_no_evidence_overlap"],
        "external_1050_scenarios": external1050["scenario_overall"],
        "status": "blocked_by_gpt_5_3_codex_spark_quota",
    }
    (RUN / "ltr_query_expansion_progress.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    scenario_rows = "".join(
        "<tr>"
        f"<td>{html.escape(name)}</td><td>{values['n']}</td>"
        f"<td>{_pct(values['baseline_hit_at_10'])}</td>"
        f"<td>{_pct(values['ltr_hit_at_10'])}</td>"
        f"<td>{_pct(values['delta_hit_at_10'])}</td></tr>"
        for name, values in external1050["scenario_overall"].items()
    )
    html_report = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LambdaMART Query扩展到2000进度报告</title>
<style>body{{font:15px/1.65 system-ui;margin:0;background:#f6f8fa;color:#17212b}}
main{{max-width:1100px;margin:24px auto;background:#fff;padding:30px;border:1px solid #d0d7de}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}
.card{{border:1px solid #d0d7de;padding:12px}}strong{{display:block;font-size:23px}}
table{{width:100%;border-collapse:collapse;margin:14px 0}}
th,td{{border:1px solid #d0d7de;padding:8px;text-align:left}}th{{background:#eef3f7}}
.warn{{border-left:4px solid #b54708;padding:10px 14px;background:#fff7ed}}
@media(max-width:760px){{main{{margin:0;border:0}}.grid{{grid-template-columns:1fr 1fr}}}}</style>
</head><body><main><h1>LambdaMART Query扩展到2000进度报告</h1>
<div class="grid">
<div class="card">5.3生成储备<strong>{generation["generated"]}</strong></div>
<div class="card">已完成盲审<strong>{build["validated_query_coverage"]}</strong></div>
<div class="card">新增长期可用<strong>{build["new_samples"]}</strong></div>
<div class="card">中间训练集<strong>{build["total_samples"]}</strong></div>
</div>
<p class="warn"><b>当前阻塞：</b>GPT-5.3-Codex-Spark 配额耗尽，CLI提示
2026-07-23 23:25 后恢复。未切换其他模型，剩余盲审与拒绝项重写保持可续跑。</p>
<h2>5折交叉验证</h2>
<table><thead><tr><th>训练集</th><th>Hybrid Recall@10</th><th>LTR Recall@10</th>
<th>提升</th><th>LTR MRR@10</th></tr></thead><tbody>
<tr><td>原420条</td><td>{_pct(cv420["overall"]["baseline_hit_at_10"])}</td>
<td>{_pct(cv420["overall"]["ltr_hit_at_10"])}</td>
<td>{_pct(cv420["overall"]["delta_hit_at_10"])}</td>
<td>{_pct(cv420["overall"]["ltr_mrr"])}</td></tr>
<tr><td>严格验证1050条</td><td>{_pct(cv1050["overall"]["baseline_hit_at_10"])}</td>
<td>{_pct(cv1050["overall"]["ltr_hit_at_10"])}</td>
<td>{_pct(cv1050["overall"]["delta_hit_at_10"])}</td>
<td>{_pct(cv1050["overall"]["ltr_mrr"])}</td></tr>
</tbody></table>
<p>1050条集合加入了更多Hard Negative，绝对分数下降，不应与420条集合直接比较难度；
两套集合都显示LTR优于同口径固定Hybrid。</p>
<h2>旧116条未扩写Query泛化测试</h2>
<table><thead><tr><th>训练集</th><th>Hybrid</th><th>LTR Recall@10</th><th>变化</th>
<th>LTR MRR@10</th><th>排除证据重叠后Recall</th></tr></thead><tbody>
<tr><td>420条</td><td>{_pct(external420["overall"]["baseline_hit_at_10"])}</td>
<td>{_pct(external420["overall"]["ltr_hit_at_10"])}</td>
<td>{_pct(external420["overall"]["delta_hit_at_10"])}</td>
<td>{_pct(external420["overall"]["ltr_mrr"])}</td>
<td>{_pct(external420["strict_no_evidence_overlap"]["ltr_hit_at_10"])}</td></tr>
<tr><td>1050条</td><td>{_pct(external1050["overall"]["baseline_hit_at_10"])}</td>
<td>{_pct(external1050["overall"]["ltr_hit_at_10"])}</td>
<td>{_pct(external1050["overall"]["delta_hit_at_10"])}</td>
<td>{_pct(external1050["overall"]["ltr_mrr"])}</td>
<td>{_pct(external1050["strict_no_evidence_overlap"]["ltr_hit_at_10"])}</td></tr>
</tbody></table>
<h2>1050条模型分场景</h2>
<table><thead><tr><th>场景</th><th>n</th><th>Hybrid</th><th>LTR</th><th>变化</th>
</tr></thead><tbody>{scenario_rows}</tbody></table>
<h2>结论</h2>
<p>增加高难数据后，模型在多条件、关键词和数字时间场景继续提升，但相似文档与别名
仍有退化。当前证据表明数据量不是唯一瓶颈，下一阶段必须优先重写宽泛Query、
补充可区分的相似文档负例，并增加原排名保护。</p>
<h2>恢复步骤</h2>
<ol><li>5.3配额恢复后继续剩余77个盲审批次。</li>
<li>对judge_null样本使用5.3按拒绝原因收缩Query，再做第二轮盲审。</li>
<li>达到七类正式配额后构建完整2000条训练集，重新缓存候选、5折训练和旧Query复测。</li>
</ol></main></body></html>"""
    (RUN / "ltr_query_expansion_progress.html").write_text(
        html_report,
        encoding="utf-8",
    )
    print(RUN / "ltr_query_expansion_progress.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
