#!/usr/bin/env python3
"""Render the 5k/20k retrieval and query-routing acceptance report."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCALE = ROOT / "runs/golden_v2/scale_100k_991004/scale_20k_overnight"


def strict_metrics(path: Path) -> tuple[float, float]:
    rows = json.loads(path.read_text(encoding="utf-8"))["metrics"]
    recall = next(row["mean"] for row in rows if row["name"] == "recall_chunk" and row["k"] == 10)
    mrr = next(row["mean"] for row in rows if row["name"] == "mrr_chunk")
    return recall, mrr


def pct(value: float) -> str:
    return f"{value:.2%}"


def main() -> None:
    baseline_path = ROOT / "runs/golden_v2/scale_100k_991004/scale_100k_991004_batch_0001_ds992000/realistic_additional_300/overnight_final/final_expanded_116/eval_dense+sparse+bm25/results/final-expanded-dense+sparse+bm25-top10-top10.json"
    default_path = ROOT / "runs/golden_v2/scale_100k_991004/scale_100k_overnight/eval_after_992003/results/scale20k-scoped-final-top10.json"
    hybrid_path = SCALE / "hybrid_weight_final/results/scale20k-hybrid-weight-final-top10.json"
    segments = json.loads((SCALE / "route_segment_analysis/tune_route_segments.json").read_text(encoding="utf-8"))["summary"]
    rerank = json.loads((SCALE / "rerank_qwen3/blind_top20_final.json").read_text(encoding="utf-8"))["best"]
    base_recall, base_mrr = strict_metrics(baseline_path)
    default_recall, default_mrr = strict_metrics(default_path)
    hybrid_recall, hybrid_mrr = strict_metrics(hybrid_path)

    order = ["all", "short_le_15", "medium_16_35", "long_gt_35", "exact_number_or_identifier", "constraint_or_fact", "natural_language_semantic"]
    labels = {
        "all": "全部 tune query", "short_le_15": "短 query (<=15 字)", "medium_16_35": "中等 query (16-35 字)",
        "long_gt_35": "长 query (>35 字)", "exact_number_or_identifier": "数字/编号", "constraint_or_fact": "条件/事实", "natural_language_semantic": "自然语言语义",
    }
    segment_rows = "".join(
        f"<tr><td>{labels[key]}</td><td>{int(row['n'])}</td><td>{pct(row['dense_only'])}</td><td>{pct(row['sparse_only'])}</td><td>{pct(row['bm25_only'])}</td><td><b>{pct(row['hybrid_070_015_015'])}</b></td></tr>"
        for key in order if key in segments for row in [segments[key]]
    )
    out = SCALE / "retrieval_routing_analysis_report.html"
    out.write_text(f"""<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>LinkRag Eval 检索分流分析报告</title>
<style>body{{margin:0;background:#f6f8fa;color:#17212b;font:15px system-ui,-apple-system,sans-serif}}main{{max-width:1120px;margin:28px auto;padding:32px;background:#fff;border:1px solid #d0d7de;border-radius:6px}}h1,h2{{margin:0 0 12px}}h2{{margin-top:34px}}p,li{{line-height:1.65}}table{{border-collapse:collapse;width:100%;margin:12px 0}}th,td{{border:1px solid #d0d7de;padding:9px;text-align:left}}th{{background:#eef3f7}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}.card{{border:1px solid #d0d7de;padding:14px;border-radius:6px}}.value{{font-size:25px;font-weight:700;margin:5px 0}}.warn{{color:#9a4d00}}.good{{color:#087443}}code{{background:#f1f3f5;padding:2px 5px}}.note{{border-left:3px solid #b7791f;padding:8px 12px;background:#fffbeb}}</style>
<main><h1>20k 检索分流分析与 5k 基线报告</h1><p>报告日期：2026-07-15。主指标为严格 <code>expected_chunk_ids</code> 的 chunk Recall@10；分桶表使用 Hit@10（至少命中一个正确 chunk），两者不混报。</p>
<h2>规模结果</h2><div class='grid'><div class='card'><div>5k 基线严格 Recall@10</div><div class='value'>{pct(base_recall)}</div><small>116 条 realistic blind，仅 dataset 992000</small></div><div class='card'><div>20k 默认 Hybrid</div><div class='value warn'>{pct(default_recall)}</div><small>权重 0.90 / 0.10 / 0.00</small></div><div class='card'><div>20k 最优 Hybrid</div><div class='value good'>{pct(hybrid_recall)}</div><small>权重 0.70 / 0.15 / 0.15</small></div></div>
<table><tr><th>方案</th><th>语料 scope</th><th>参数</th><th>严格 Recall@10</th><th>MRR</th></tr><tr><td>5k 基线</td><td>992000</td><td>历史基线</td><td>{pct(base_recall)}</td><td>{pct(base_mrr)}</td></tr><tr><td>20k 默认</td><td>992000-992003</td><td>150/50/50, 0.90/0.10/0.00</td><td>{pct(default_recall)}</td><td>{pct(default_mrr)}</td></tr><tr><td>20k 最优 Hybrid</td><td>992000-992003</td><td>dense 150/.30/.70; sparse 50/.20/.15; BM25 100/.00/.15</td><td><b>{pct(hybrid_recall)}</b></td><td><b>{pct(hybrid_mrr)}</b></td></tr></table>
<h2>分场景单路与融合</h2><p>272 条 tune query。Hybrid 使用当前最优加权融合。该表用于决定 query 分流，不用于替代严格 Recall 主指标。</p><table><tr><th>场景</th><th>n</th><th>Dense-only</th><th>Sparse-only</th><th>BM25-only</th><th>Hybrid</th></tr>{segment_rows}</table>
<div class='note'><b>短 query 结论需谨慎：</b>短 query 仅 14 条，Sparse-only 为 {pct(segments['short_le_15']['sparse_only'])}，高于 Hybrid {pct(segments['short_le_15']['hybrid_070_015_015'])}；这是明确的分流候选信号，但样本量不足，不能直接固化为线上规则。长 query 仅 1 条、数字/编号仅 4 条，必须补齐平衡黄金集。</div>
<h2>为什么短 query Sparse 更好</h2><ul><li>短 query 上下文不足，dense 更容易把主题相近但条件不符的 chunk 排高。</li><li>Sparse 保留原始关键词、专名和词法特征，对短关键词命中更直接。</li><li>当前 Hybrid 以 dense 权重 .70 为主；dense 的高分干扰可能将 Sparse 的精确命中挤出 Top10。</li></ul>
<h2>Rerank 对照</h2><p>qwen3-rerank 仅在融合 Top20 内重排。116 条 blind 的严格 Recall@10 为 <b>{pct(rerank['recall_at_10'])}</b>，MRR 为 {pct(rerank['mrr'])}，低于未重排的 20k Hybrid。结论：当前不应默认启用 rerank。</p>
<h2>建议的分流方案</h2><ol><li>默认使用当前最优 Hybrid。</li><li>仅对 <code>长度<=15 且 Sparse 置信度足够高</code> 的 query，在 tune 扩容后测试 Sparse-only 分流。</li><li>数字/编号、长 query、条件事实类暂不直接切 BM25：当前数据中 Hybrid 仍明显更优。</li><li>补齐每类至少 80-100 条、且带 chunk 级证据标注的 balanced tune/blind；固定规则后只运行一次 blind。</li></ol></main></html>""", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
