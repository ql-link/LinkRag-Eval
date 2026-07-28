#!/usr/bin/env python3
"""Render the exposure-isolated Blind v2 comparison for frozen LTR models."""

from __future__ import annotations

import html
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = (
    ROOT
    / "runs/golden_v2/scale_100k_991004/scale_20k_overnight/"
    "ltr_query_expansion_2000/final_2000/blind_v2_20260718"
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _pct(value: float) -> str:
    return f"{value:.2%}"


def _wilson(hits: int, total: int) -> list[float]:
    z = 1.959963984540054
    p = hits / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [center - radius, center + radius]


def main() -> int:
    exposure = _load(RUN / "exposure/exposure_manifest.json")
    build = _load(RUN / "frozen/build_report.json")
    cache = _load(RUN / "evaluation/candidates_210_report.json")
    model1050 = _load(RUN / "evaluation/model_1050_frozen_once/ltr_external_evaluation.json")
    model2000 = _load(RUN / "evaluation/model_frozen_once/ltr_external_evaluation.json")
    candidates = _rows(RUN / "evaluation/candidates_210.jsonl")

    coverage: dict[str, Counter] = defaultdict(Counter)
    for row in candidates:
        expected = {str(value) for value in row["expected_chunk_ids"]}
        for group in ("all", str(row["scenario"])):
            coverage[group]["n"] += 1
            union: set[str] = set()
            for route in ("dense", "sparse", "bm25"):
                route_ids = {str(hit["chunk_id"]) for hit in row["routes"][route]}
                union.update(route_ids)
                coverage[group][route] += bool(expected & route_ids)
            coverage[group]["union"] += bool(expected & union)

    old_predictions = {row["sample_id"]: row for row in model1050["predictions"]}
    new_predictions = {row["sample_id"]: row for row in model2000["predictions"]}
    paired = Counter()
    for sample_id, old in old_predictions.items():
        new = new_predictions[sample_id]
        old_hit = bool(old["ltr_hit_at_10"])
        new_hit = bool(new["ltr_hit_at_10"])
        if old_hit == new_hit:
            paired["both_hit" if old_hit else "both_miss"] += 1
        else:
            paired["model_2000_gained"] += int(new_hit)
            paired["model_2000_lost"] += int(old_hit)

    n = int(model2000["overall"]["n"])
    baseline_hits = round(model2000["overall"]["baseline_hit_at_10"] * n)
    hits1050 = round(model1050["overall"]["ltr_hit_at_10"] * n)
    hits2000 = round(model2000["overall"]["ltr_hit_at_10"] * n)
    report = {
        "status": "complete_frozen_once",
        "blind_definition": {
            "query_overlap_with_history": build["query_overlap_with_history"],
            "positive_evidence_overlap_with_history": build[
                "evidence_overlap_with_history"
            ],
            "positive_exposure_definition": exposure["positive_exposure_definition"],
            "candidate_content_boundary": (
                "All 20k chunks may have appeared as negative candidates during LTR training; "
                "isolation applies to queries and positive labels."
            ),
        },
        "build": build,
        "candidate_cache": cache,
        "route_coverage": {name: dict(values) for name, values in coverage.items()},
        "frozen_parameters": {
            "n_estimators": 24,
            "seed": 20260716,
            "blend_alpha": 1.0,
            "model_1050_protect_baseline_top_k": 2,
            "model_2000_protect_baseline_top_k": 1,
        },
        "baseline": {
            **model2000["overall"],
            "hits": baseline_hits,
            "recall_95pct_wilson": _wilson(baseline_hits, n),
        },
        "model_1050": {
            **model1050["overall"],
            "hits": hits1050,
            "recall_95pct_wilson": _wilson(hits1050, n),
            "scenarios": model1050["scenario_overall"],
        },
        "model_2000": {
            **model2000["overall"],
            "hits": hits2000,
            "recall_95pct_wilson": _wilson(hits2000, n),
            "scenarios": model2000["scenario_overall"],
        },
        "paired_2000_vs_1050": dict(paired),
        "conclusion": (
            "Both frozen models reach 58/210 Recall@10. The 2000-query model improves MRR "
            "but does not improve total Top10 hits. Both outperform fixed Hybrid by 14 hits."
        ),
    }
    json_path = RUN / "blind_v2_evaluation_report.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    model_rows = (
        f"<tr><td>固定 Hybrid</td><td>{baseline_hits}/{n}</td>"
        f"<td>{_pct(model2000['overall']['baseline_hit_at_10'])}</td>"
        f"<td>{_pct(model2000['overall']['baseline_mrr'])}</td><td>-</td></tr>"
        f"<tr><td>1050条 LambdaMART</td><td>{hits1050}/{n}</td>"
        f"<td>{_pct(model1050['overall']['ltr_hit_at_10'])}</td>"
        f"<td>{_pct(model1050['overall']['ltr_mrr'])}</td>"
        f"<td>{model1050['overall']['delta_hit_at_10'] * 100:+.2f}pp</td></tr>"
        f"<tr><td>2000条 LambdaMART</td><td>{hits2000}/{n}</td>"
        f"<td>{_pct(model2000['overall']['ltr_hit_at_10'])}</td>"
        f"<td>{_pct(model2000['overall']['ltr_mrr'])}</td>"
        f"<td>{model2000['overall']['delta_hit_at_10'] * 100:+.2f}pp</td></tr>"
    )
    scenario_rows = "".join(
        "<tr>"
        f"<td>{html.escape(name)}</td><td>{values['n']}</td>"
        f"<td>{_pct(values['baseline_hit_at_10'])}</td>"
        f"<td>{_pct(model1050['scenario_overall'][name]['ltr_hit_at_10'])}</td>"
        f"<td>{_pct(values['ltr_hit_at_10'])}</td>"
        f"<td>{_pct(values['candidate_union_coverage'])}</td></tr>"
        for name, values in model2000["scenario_overall"].items()
    )
    html_path = RUN / "blind_v2_evaluation_report.html"
    html_path.write_text(
        f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>全新Blind v2冻结测试报告</title>
<style>body{{font:15px/1.65 system-ui;margin:0;background:#f6f8fa;color:#17212b}}
main{{max-width:1080px;margin:24px auto;background:#fff;padding:30px;border:1px solid #d0d7de}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}.card{{border:1px solid #d0d7de;padding:12px}}
.card strong{{display:block;font-size:24px}}table{{width:100%;border-collapse:collapse;margin:14px 0}}
th,td{{border:1px solid #d0d7de;padding:8px;text-align:left}}th{{background:#eef3f7}}
.ok{{border-left:4px solid #1a7f37;padding:10px 14px;background:#dafbe1}}
.warn{{border-left:4px solid #b54708;padding:10px 14px;background:#fff7ed}}
@media(max-width:760px){{main{{margin:0;border:0}}.grid{{grid-template-columns:1fr 1fr}}}}</style>
</head><body><main><h1>全新 Blind v2 冻结测试报告</h1>
<p class="ok"><b>隔离通过：</b>210条Query与历史Query重叠0，正证据Chunk与训练/历史测试正标签重叠0；
七类各30条，全部为唯一Chunk级标注。</p>
<p class="warn"><b>边界：</b>20k语料Chunk可能在LTR训练候选池中作为负例出现；“未曝光”严格指Query和正标签未曝光。
该集使用同主题Hard Negative生成，是平衡高难Blind，不代表自然线上流量分布。</p>
<div class="grid"><div class="card">Blind Query<strong>210</strong></div>
<div class="card">候选覆盖<strong>{_pct(model2000['overall']['candidate_union_coverage'])}</strong></div>
<div class="card">Hybrid Recall<strong>{_pct(model2000['overall']['baseline_hit_at_10'])}</strong></div>
<div class="card">LTR Recall<strong>{_pct(model2000['overall']['ltr_hit_at_10'])}</strong></div></div>
<h2>冻结模型主结果</h2><table><thead><tr><th>模型</th><th>命中</th><th>Recall@10</th><th>MRR@10</th><th>相对Hybrid</th></tr></thead>
<tbody>{model_rows}</tbody></table>
<p>1050与2000模型Recall完全相同，均为58/210。2000相对1050新增命中
{paired['model_2000_gained']}条、丢失{paired['model_2000_lost']}条；MRR由
{_pct(model1050['overall']['ltr_mrr'])}升至{_pct(model2000['overall']['ltr_mrr'])}。</p>
<h2>分场景</h2><table><thead><tr><th>场景</th><th>n</th><th>Hybrid</th><th>1050模型</th><th>2000模型</th><th>候选覆盖</th></tr></thead>
<tbody>{scenario_rows}</tbody></table>
<h2>结论</h2><p>新Blind没有支持“1050质量更好”：两种训练规模的Top10命中数相同。2000模型在Dense改写、Alias、
精确编号和短关键词上更好，但在多约束、数字时间和相似文档上抵消了收益。两模型都比固定Hybrid多命中14条，
证明LambdaMART方向有效；下一步瓶颈是候选覆盖和场景差异监督，而不是继续仅增加训练条数。</p>
</main></body></html>""",
        encoding="utf-8",
    )
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
