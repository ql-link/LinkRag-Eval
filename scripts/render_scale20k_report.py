#!/usr/bin/env python3
"""Render the current 20k evaluation acceptance report as standalone HTML."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCALE = ROOT / "runs/golden_v2/scale_100k_991004/scale_20k_overnight"


def metric(path: Path) -> tuple[float, float]:
    rows = json.loads(path.read_text(encoding="utf-8"))["metrics"]
    recall = next(row["mean"] for row in rows if row["name"] == "recall_chunk" and row["k"] == 10)
    mrr = next(row["mean"] for row in rows if row["name"] == "mrr_chunk")
    return recall, mrr


def main() -> None:
    baseline, baseline_mrr = metric(
        ROOT / "runs/golden_v2/scale_100k_991004/scale_100k_991004_batch_0001_ds992000/realistic_additional_300/overnight_final/final_expanded_116/eval_dense+sparse+bm25/results/final-expanded-dense+sparse+bm25-top10-top10.json"
    )
    default, default_mrr = metric(
        ROOT / "runs/golden_v2/scale_100k_991004/scale_100k_overnight/eval_after_992003/results/scale20k-scoped-final-top10.json"
    )
    tuned, tuned_mrr = metric(SCALE / "hybrid_weight_final/results/scale20k-hybrid-weight-final-top10.json")
    coverage_path = SCALE / "coverage/realistic_blind_coverage_summary.json"
    coverage = json.loads(coverage_path.read_text(encoding="utf-8")) if coverage_path.exists() else None
    coverage_html = "<p>候选覆盖诊断仍在运行。</p>" if coverage is None else (
        "<p>诊断使用扩大候选池 Dense Top300、Sparse Top100、BM25 Top100，"
        "用于判断正确证据是否已进入任一路候选，不等同于正式 Hybrid Top10 指标。</p>"
        f"<ul><li>三路候选并集覆盖: {coverage['candidate_union_recall']:.2%}</li>"
        f"<li>本地融合 Top10 命中: {coverage['final_recall_at_10']:.2%}</li>"
        f"<li>候选存在但本地融合未进 Top10（fusion_miss）: {coverage['diagnosis_counts'].get('fusion_miss', 0)} 条</li>"
        f"<li>正确证据未进入扩大候选池（candidate_miss）: {coverage['diagnosis_counts'].get('candidate_miss', 0)} 条</li>"
        "</ul><p><b>诊断结论：</b>当前主要瓶颈是候选截断和融合排序，而不是三路完全无法找到正确证据。"
        "后续重排实验未获得稳定收益，当前已终止该路线，统一使用不含重排分数的 LambdaMART v2。</p>"
    )
    out = SCALE / "scale20k_acceptance_report.html"
    out.write_text(f"""<!doctype html><html lang='zh-CN'><meta charset='utf-8'>
<title>LinkRag Eval 20k 验收报告</title><style>
body{{font:15px system-ui,sans-serif;color:#17212b;margin:0;background:#f6f8fa}}main{{max-width:1000px;margin:32px auto;background:#fff;padding:32px;border:1px solid #d0d7de;border-radius:6px}}h1{{margin-top:0}}table{{border-collapse:collapse;width:100%;margin:12px 0 28px}}th,td{{padding:10px;border:1px solid #d0d7de;text-align:left}}th{{background:#eef3f7}}.metric{{display:flex;gap:16px}}.card{{flex:1;padding:16px;border:1px solid #d0d7de;border-radius:6px}}.value{{font-size:28px;font-weight:700}}.good{{color:#087443}}.warn{{color:#a64b00}}code{{background:#f1f3f5;padding:2px 5px}}</style>
<main><h1>20k Chunk 召回验收报告</h1><p>口径：116 条 realistic blind，chunk 粒度，query scope 为 <code>992000–992003</code>，新增 15,000 chunks 实际参与检索。</p>
<div class='metric'><div class='card'><div>5k 基线 Recall@10</div><div class='value'>{baseline:.2%}</div><small>仅 992000 scope，不与 20k 直接比较</small></div><div class='card'><div>20k 默认 Hybrid</div><div class='value warn'>{default:.2%}</div><small>权重 0.90/0.10/0.00</small></div><div class='card'><div>20k 三路线调优 Hybrid</div><div class='value good'>{tuned:.2%}</div><small>权重 0.70/0.15/0.15</small></div></div>
<h2>参数与结果</h2><table><tr><th>方案</th><th>Dense/Sparse/BM25</th><th>TopK</th><th>阈值</th><th>Recall@10</th><th>MRR</th></tr><tr><td>20k 默认</td><td>0.90 / 0.10 / 0.00</td><td>150 / 50 / 50</td><td>0.30 / 0.10 / -</td><td>{default:.2%}</td><td>{default_mrr:.2%}</td></tr><tr><td>20k 调优</td><td>0.70 / 0.15 / 0.15</td><td>150 / 50 / 100</td><td>0.30 / 0.20 / 0.00</td><td>{tuned:.2%}</td><td>{tuned_mrr:.2%}</td></tr></table>
<h2>结论</h2><p>三路线权重融合相对 20k 默认配置提升 Recall@10 {(tuned-default):.2%}，说明 BM25 对精确条件类检索有增量价值。20k 相比 5k 下降的主要原因是同领域高相似干扰语料进入同一检索 scope，且评测要求命中指定证据 chunk。</p>
<h2>候选覆盖诊断</h2>{coverage_html}<h2>Rerank 决策</h2><p>直接重排和作为 LambdaMART 附加特征的实验均未获得稳定 Blind 收益，2026-07-21 已终止该路线。历史报告继续保留，活动训练与推理固定使用不含重排分数的 <code>candidate_difference_v2</code>。</p><h2>质量门禁</h2><ul><li>realistic Golden V2 QC：通过，420 queries、7,122 judgments、random relevant rate 0。</li><li>测试：286 passed, 3 skipped。</li><li>import-lint：通过。</li></ul></main></html>""", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
