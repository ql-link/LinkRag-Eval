#!/usr/bin/env python3
"""Render the 2000-query LambdaMART evaluation and historical comparison."""

from __future__ import annotations

import html
import json
import math
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = (
    ROOT
    / "runs/golden_v2/scale_100k_991004/scale_20k_overnight/"
    "ltr_query_expansion_2000/final_2000/ltr_evaluation_v1"
)
BASE = ROOT / "runs/golden_v2/scale_100k_991004/scale_20k_overnight"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _pct(value: float) -> str:
    return f"{value:.2%}"


def _two_sided_sign_test(gained: int, lost: int) -> float:
    discordant = gained + lost
    if not discordant:
        return 1.0
    tail = min(gained, lost)
    probability = sum(math.comb(discordant, index) for index in range(tail + 1)) / 2**discordant
    return min(1.0, 2 * probability)


def main() -> int:
    cache = _load(RUN / "candidates_2000_report.json")
    cv = _load(RUN / "model_v2/cv/ltr_cross_validation.json")
    current = _load(RUN / "model_v2/optimization_summary.json")
    previous = _load(
        BASE
        / "ltr_query_expansion_2000/ltr_partial_1050/candidate_features_v2_final/"
        "optimization_summary.json"
    )
    model420 = _load(
        BASE
        / "balanced_query_expansion/balanced_final_600/ltr_fusion_v1/"
        "external_realistic_blind_116/evaluation/ltr_external_evaluation.json"
    )
    current_predictions = {
        row["sample_id"]: row
        for row in _load(
            RUN / "model_v2/external_frozen/ltr_external_evaluation.json"
        )["predictions"]
    }
    previous_predictions = {
        row["sample_id"]: row
        for row in _load(
            BASE
            / "ltr_query_expansion_2000/ltr_partial_1050/candidate_features_v2_final/"
            "external_frozen/ltr_external_evaluation.json"
        )["predictions"]
    }
    changes = Counter()
    changed_rows = []
    for sample_id, old in previous_predictions.items():
        new = current_predictions[sample_id]
        old_hit = bool(old["ltr_hit_at_10"])
        new_hit = bool(new["ltr_hit_at_10"])
        if old_hit == new_hit:
            continue
        transition = "gained" if new_hit else "lost"
        changes[transition] += 1
        changed_rows.append(
            {
                "sample_id": sample_id,
                "scenario": new["scenario"],
                "transition": transition,
            }
        )
    sign_test_p = _two_sided_sign_test(changes["gained"], changes["lost"])

    comparison = [
        {
            "model": "420-v1 historical",
            "recall_at_10": model420["overall"]["ltr_hit_at_10"],
            "mrr_at_10": model420["overall"]["ltr_mrr"],
            "protection_top_k": None,
        },
        {
            "model": "1050-v2",
            "recall_at_10": previous["external_overall"]["ltr_hit_at_10"],
            "mrr_at_10": previous["external_overall"]["ltr_mrr"],
            "protection_top_k": previous["tune_best"]["protect_baseline_top_k"],
        },
        {
            "model": "2000-v2",
            "recall_at_10": current["external_overall"]["ltr_hit_at_10"],
            "mrr_at_10": current["external_overall"]["ltr_mrr"],
            "protection_top_k": current["tune_best"]["protect_baseline_top_k"],
        },
    ]
    report = {
        "status": "complete",
        "evaluation_boundary": (
            "The 116-query external set is reused regression data, not an untouched blind set."
        ),
        "candidate_cache": cache,
        "tune_oof": cv["overall"],
        "tune_frozen_postprocessing": current["tune_best"],
        "external_overall": current["external_overall"],
        "external_strict_no_evidence_overlap": current["external_strict"],
        "external_scenarios": current["external_scenarios"],
        "historical_comparison": comparison,
        "paired_1050_to_2000": {
            "gained": changes["gained"],
            "lost": changes["lost"],
            "discordant": changes["gained"] + changes["lost"],
            "two_sided_exact_p": sign_test_p,
            "changed_samples": changed_rows,
        },
        "conclusion": (
            "The 2000-query model improves over fixed Hybrid, but does not outperform the "
            "1050-query v2 model on the reused 116-query regression set. The net two-query "
            "difference is not statistically established. Similar-doc ranking remains the main risk."
        ),
    }
    json_path = RUN / "ltr_2000_evaluation_report.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    comparison_rows = "".join(
        "<tr>"
        f"<td>{html.escape(row['model'])}</td><td>{_pct(row['recall_at_10'])}</td>"
        f"<td>{_pct(row['mrr_at_10'])}</td>"
        f"<td>{'-' if row['protection_top_k'] is None else row['protection_top_k']}</td></tr>"
        for row in comparison
    )
    scenario_rows = "".join(
        "<tr>"
        f"<td>{html.escape(name)}</td><td>{values['n']}</td>"
        f"<td>{_pct(values['baseline_hit_at_10'])}</td>"
        f"<td>{_pct(values['ltr_hit_at_10'])}</td>"
        f"<td>{values['delta_hit_at_10'] * 100:+.2f}pp</td>"
        f"<td>{_pct(values['candidate_union_coverage'])}</td></tr>"
        for name, values in current["external_scenarios"].items()
    )
    html_path = RUN / "ltr_2000_evaluation_report.html"
    html_path.write_text(
        f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LambdaMART 2000条训练集测试报告</title>
<style>body{{font:15px/1.65 system-ui;margin:0;background:#f6f8fa;color:#17212b}}
main{{max-width:1080px;margin:24px auto;background:#fff;padding:30px;border:1px solid #d0d7de}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}.card{{border:1px solid #d0d7de;padding:12px}}
.card strong{{display:block;font-size:24px}}table{{width:100%;border-collapse:collapse;margin:14px 0}}
th,td{{border:1px solid #d0d7de;padding:8px;text-align:left}}th{{background:#eef3f7}}
.warn{{border-left:4px solid #b54708;padding:10px 14px;background:#fff7ed}}
.ok{{border-left:4px solid #1a7f37;padding:10px 14px;background:#dafbe1}}
@media(max-width:760px){{main{{margin:0;border:0}}.grid{{grid-template-columns:1fr 1fr}}}}</style>
</head><body><main><h1>LambdaMART 2000条训练集测试报告</h1>
<p class="warn"><b>口径：</b>116条外部Query已被历史实验多次使用，本报告将其视为回归集，不视为未触碰Blind。</p>
<div class="grid"><div class="card">训练Query<strong>2000</strong></div>
<div class="card">候选覆盖率<strong>{_pct(cv['overall']['candidate_union_coverage'])}</strong></div>
<div class="card">Tune OOF Recall<strong>{_pct(current['tune_best']['hit_at_10'])}</strong></div>
<div class="card">外部 Recall<strong>{_pct(current['external_overall']['ltr_hit_at_10'])}</strong></div></div>
<h2>冻结参数与主结果</h2><p><code>blend_alpha={current['tune_best']['blend_alpha']}</code>，
<code>protect_baseline_top_k={current['tune_best']['protect_baseline_top_k']}</code>，只由Tune OOF选择。</p>
<p class="ok">Tune OOF：Hybrid {_pct(cv['overall']['baseline_hit_at_10'])} → LambdaMART保护后
{_pct(current['tune_best']['hit_at_10'])}（{current['tune_best']['delta_hit_at_10'] * 100:+.2f}pp）。<br>
外部回归：Hybrid {_pct(current['external_overall']['baseline_hit_at_10'])} → LambdaMART
{_pct(current['external_overall']['ltr_hit_at_10'])}（{current['external_overall']['delta_hit_at_10'] * 100:+.2f}pp）。</p>
<h2>历史模型对比</h2><table><thead><tr><th>模型</th><th>外部 Recall@10</th><th>外部 MRR@10</th><th>保护TopK</th></tr></thead>
<tbody>{comparison_rows}</tbody></table>
<p>1050→2000逐题变化：新增命中 {changes['gained']} 条、丢失 {changes['lost']} 条，净少
{changes['lost'] - changes['gained']} 条；双侧精确检验 p={sign_test_p:.3f}，不足以证明真实退化。</p>
<h2>2000模型分场景外部结果</h2><table><thead><tr><th>场景</th><th>n</th><th>Hybrid</th><th>LTR</th><th>变化</th><th>候选覆盖</th></tr></thead>
<tbody>{scenario_rows}</tbody></table>
<h2>结论</h2><p>2000条模型仍明确优于固定Hybrid，但没有超过1050条v2模型。主要风险仍是相似文档：
16条中由56.25%降至43.75%，实际对应净少2条中的1条。下一步应保留当前2000条数据，针对相似文档增加
成组差异监督或场景保护，并建立新的未触碰Blind后再决定生产替换。</p>
</main></body></html>""",
        encoding="utf-8",
    )
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
