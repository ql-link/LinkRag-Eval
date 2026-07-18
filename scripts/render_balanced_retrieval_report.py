#!/usr/bin/env python3
"""Render the final balanced-query retrieval comparison report."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCALE = ROOT / "runs/golden_v2/scale_100k_991004/scale_20k_overnight"
FINAL = SCALE / "balanced_query_expansion/balanced_final_600"


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _metric(path: Path, name: str, k: int | None = None) -> tuple[float, int]:
    metrics = _json(path)["metrics"]
    row = next(item for item in metrics if item["name"] == name and item["k"] == k)
    return float(row["mean"]), int(row["n"])


def _pct(value: float) -> str:
    return f"{value:.2%}"


def main() -> int:
    analysis = _json(FINAL / "balanced_route_analysis.json")
    tune = _json(FINAL / "balanced_tune_scenario_analysis.json")["scenarios"]
    joint_tuning = _json(FINAL / "balanced_weight_joint_tune.json")
    validation_paths = {
        "short_keyword": SCALE / "balanced_query_expansion/grounded_supplements/short_keyword/validation/validation_report.json",
        "exact_primary": SCALE / "balanced_query_expansion/grounded_exact_replacement/validation/validation_report.json",
        "exact_reserve": SCALE / "balanced_query_expansion/grounded_exact_extension/validation/validation_report.json",
        "long_sparse": SCALE / "balanced_query_expansion/grounded_supplements/long_sparse/validation/validation_report.json",
        "dense_paraphrase": SCALE / "balanced_query_expansion/grounded_supplements/dense_paraphrase/validation/validation_report.json",
    }
    validations = {name: _json(path) for name, path in validation_paths.items()}
    historical = {
        "5k": ROOT / "runs/golden_v2/scale_100k_991004/scale_100k_991004_batch_0001_ds992000/realistic_additional_300/overnight_final/final_expanded_116/eval_dense+sparse+bm25/results/final-expanded-dense+sparse+bm25-top10-top10.json",
        "20k_old": SCALE / "hybrid_weight_final/results/scale20k-hybrid-weight-final-top10.json",
    }
    old_report = SCALE / "retrieval_routing_analysis_report.html"

    route_labels = {"dense": "Dense-only", "sparse": "Sparse-only", "bm25": "BM25-only", "hybrid": "Hybrid"}
    scenario_labels = {
        "short_keyword": "短 query",
        "exact_identifier": "数字 / 日期 / 版本",
        "long_sparse": "长多约束 query",
        "dense_paraphrase": "自然语言语义改写",
    }
    overall_rows = "".join(
        f"<tr><td>{route_labels[route]}</td><td>{values['n']}</td>"
        f"<td><b>{_pct(values['recall_at_10'])}</b></td><td>{_pct(values['mrr'])}</td></tr>"
        for route, values in analysis["overall"].items()
    )
    scenario_rows = "".join(
        "<tr>"
        f"<td>{scenario_labels[scenario]}</td><td>{values['n']}</td>"
        f"<td>{_pct(values['dense'])}</td><td>{_pct(values['sparse'])}</td>"
        f"<td>{_pct(values['bm25'])}</td><td><b>{_pct(values['hybrid'])}</b></td>"
        f"<td>{_pct(values['single_route_oracle'])}</td>"
        f"<td>{values['hybrid_missed_but_single_hit']}</td></tr>"
        for scenario, values in analysis["scenarios"].items()
    )
    tune_rows = "".join(
        "<tr>"
        f"<td>{scenario_labels[scenario]}</td><td>{values['n']}</td>"
        f"<td>{_pct(values['dense'])}</td><td>{_pct(values['sparse'])}</td>"
        f"<td>{_pct(values['bm25'])}</td><td><b>{_pct(values['hybrid'])}</b></td>"
        f"<td>{_pct(values['oracle'])}</td></tr>"
        for scenario, values in tune.items()
    )
    validation_rows = "".join(
        f"<tr><td>{html.escape(name)}</td><td>{row['queries']}</td><td>{row['accepted']}</td>"
        f"<td>{row['unresolved']}</td><td>{_pct(row['acceptance_rate'])}</td>"
        f"<td>{row['generation_target_matches']}</td><td>{row['alternate_canonical_chunks']}</td></tr>"
        for name, row in validations.items()
    )
    historical_rows = []
    for name, path in historical.items():
        recall, n = _metric(path, "recall_chunk", 10)
        hit, _ = _metric(path, "hit_rate_chunk", 10)
        historical_rows.append(
            f"<tr><td>{name}</td><td>{n}</td><td>{_pct(recall)}</td><td>{_pct(hit)}</td></tr>"
        )
    historical_rows.append(
        f"<tr><td>20k balanced blind</td><td>180</td><td>{_pct(analysis['overall']['hybrid']['recall_at_10'])}</td>"
        f"<td>{_pct(analysis['overall']['hybrid']['recall_at_10'])}</td></tr>"
    )

    out = FINAL / "balanced_retrieval_routing_report.html"
    old_link = Path("../../retrieval_routing_analysis_report.html")
    out.write_text(
        f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>20k Balanced Query 检索报告</title>
<style>
:root{{--ink:#17212b;--muted:#57606a;--line:#d0d7de;--band:#eef3f7;--good:#087443;--warn:#9a4d00;--bg:#f6f8fa}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 system-ui,-apple-system,"PingFang SC",sans-serif}}main{{max-width:1180px;margin:24px auto;padding:32px;background:#fff;border:1px solid var(--line)}}h1{{font-size:28px;margin:0 0 8px}}h2{{font-size:20px;margin:32px 0 10px}}p{{margin:8px 0}}.lead{{color:var(--muted)}}.metrics{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:18px 0}}.metric{{border:1px solid var(--line);border-radius:6px;padding:14px}}.metric strong{{display:block;font-size:24px;color:var(--good)}}table{{width:100%;border-collapse:collapse;margin:12px 0;display:block;overflow-x:auto}}th,td{{border:1px solid var(--line);padding:9px 10px;text-align:left;white-space:nowrap}}th{{background:var(--band)}}code{{background:#f1f3f5;padding:2px 5px}}.note{{border-left:3px solid #b7791f;background:#fffbeb;padding:10px 13px;margin:14px 0}}.good{{color:var(--good)}}.warn{{color:var(--warn)}}a{{color:#0969da}}@media(max-width:760px){{main{{margin:0;padding:20px;border:0}}.metrics{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
</style></head><body><main>
<h1>20k Balanced Query 检索与分流报告</h1><p class="lead">生成时间：2026-07-15。主指标为 chunk 粒度 Recall@10；新 blind 每个场景固定 45 条，共 180 条。</p>
<div class="metrics"><div class="metric">Hybrid Recall@10<strong>{_pct(analysis['overall']['hybrid']['recall_at_10'])}</strong>n=180</div><div class="metric">Sparse-only<strong>{_pct(analysis['overall']['sparse']['recall_at_10'])}</strong>n=180</div><div class="metric">Dense-only<strong>{_pct(analysis['overall']['dense']['recall_at_10'])}</strong>n=180</div><div class="metric">BM25-only<strong>{_pct(analysis['overall']['bm25']['recall_at_10'])}</strong>n=180</div></div>
<h2>结论</h2><ol><li><b>默认继续使用当前最优 Hybrid。</b>它在 420 条 tune 的四个场景都优于任一固定单路，并在 180 条 blind 的总体、短 query、长 query、语义改写三类领先。</li><li>旧报告“短 query 走 Sparse”来自 n=14 的小样本；新 tune 的 n=105 与 blind 的 n=45 都显示 Hybrid 最优，该规则不成立。</li><li>exact 的 blind 上 Sparse 比 Hybrid 多 1 条，但 tune 上 Hybrid 73.33%、Sparse 72.38%。这是抽样波动，不新增静态分流规则。</li><li>单路 oracle 明显高于 Hybrid，说明动态置信度门控仍有潜力；但 oracle 使用了答案，不能直接作为上线指标。</li></ol>
<h2>冻结参数</h2><p><code>weighted_score</code>；权重 dense/sparse/BM25 = <code>0.70/0.15/0.15</code>；分路 TopK = <code>150/50/100</code>；阈值 = <code>0.30/0.20/0</code>；最终 TopK = <code>10</code>。这些参数来自此前 tune，当前 blind 只运行一次，没有按本报告结果回调。</p>
<p>新 balanced tune 先搜索了 108 组 TopK/阈值，再执行 6 组权重 × 144 组结构的联合搜索，共 {joint_tuning['configs']} 组，0 个分路失败。联合最优精确等于当前默认：<code>0.70/0.15/0.15</code>、<code>150/50/100</code>、<code>0.30/0.20/0</code>，Recall/MRR 为 {_pct(joint_tuning['best']['recall_at_10'])}/{_pct(joint_tuning['best']['mrr'])}。在固定权重搜索中 dense <code>0.30</code> 与 <code>0.40</code> 指标相同，联合搜索最终选择 <code>0.30</code>。</p>
<h2>总体结果</h2><table><thead><tr><th>方案</th><th>n</th><th>Recall@10</th><th>MRR</th></tr></thead><tbody>{overall_rows}</tbody></table>
<h2>四场景对比</h2><table><thead><tr><th>场景</th><th>n</th><th>Dense</th><th>Sparse</th><th>BM25</th><th>Hybrid</th><th>单路 Oracle</th><th>单路命中但 Hybrid 未命中</th></tr></thead><tbody>{scenario_rows}</tbody></table>
<div class="note"><b>为什么 Hybrid 仍有丢失：</b>四类分别有 6、10、2、12 条出现“至少一条单路命中但 Hybrid Top10 未命中”。加权融合会让其他路的高分干扰挤压正确 chunk；后续优化重点应是 tune 上的置信度门控或候选保底，不是继续在 blind 上试权重。</div>
<h2>Tune 稳定性验证</h2><p>以下 420 条只用于分析与下一版参数候选，不改变已经冻结并只运行一次的 blind 结果。</p><table><thead><tr><th>场景</th><th>n</th><th>Dense</th><th>Sparse</th><th>BM25</th><th>Hybrid</th><th>单路 Oracle</th></tr></thead><tbody>{tune_rows}</tbody></table>
<h2>Query 软分流候选方案</h2><p>以下参数是下一阶段在 tune 集验证的实验起点，不是已经验证的最优参数，也不替代当前默认 Hybrid。</p>
<table><thead><tr><th>Query 特征</th><th>Dense</th><th>Sparse</th><th>BM25</th><th>额外处理</th></tr></thead><tbody>
<tr><td>短关键词</td><td>0.45</td><td>0.40</td><td>0.15</td><td>保护 Sparse Top3</td></tr>
<tr><td>明确编号/日期/版本号</td><td>0.30</td><td>0.35</td><td>0.35</td><td>精确词命中加分</td></tr>
<tr><td>长描述/多条件</td><td>0.45</td><td>0.40</td><td>0.15</td><td>去停用词并提取关键条件</td></tr>
<tr><td>自然语言改写</td><td>0.70</td><td>0.20</td><td>0.10</td><td>保护 Dense Top4</td></tr>
<tr><td>无明显特征</td><td>0.70</td><td>0.15</td><td>0.15</td><td>使用当前默认 Hybrid</td></tr>
</tbody></table>
<div class="note"><b>验证边界：</b>只允许在 balanced tune 420 条上调整分类规则、权重和候选保护名额；当前 balanced blind 180 条已经揭盲，不再用于选参。规则冻结后应使用新的 blind v2 或下一批真实 Query 做一次独立验收。</div>
<h2>黄金集质量</h2><p>最终 600 条：四类各 150；每类 tune 105 / blind 45；按证据文档分组，文档不跨 split；每条均为唯一 canonical <code>expected_chunk_ids</code>，检索 scope 固定为 992000–992003 的 20k chunks。</p>
<table><thead><tr><th>新增批次</th><th>生成</th><th>接受</th><th>未解决</th><th>接受率</th><th>生成目标命中</th><th>替代 canonical</th></tr></thead><tbody>{validation_rows}</tbody></table>
<p>判官看不到生成目标 ID、注入来源或候选原排序。生成目标缺失时只作为隐藏候选注入；模型可选择更直接的替代 chunk，也可返回 unresolved。最终 exact 使用 150 条独立接受样本；short/long/dense 只补足原集合缺口。</p>
<h2>历史上下文</h2><table><thead><tr><th>阶段</th><th>n</th><th>chunk Recall@10</th><th>chunk Hit@10</th></tr></thead><tbody>{''.join(historical_rows)}</tbody></table>
<div class="note"><b>不可直接同比：</b>5k 与旧 20k 集含多 reference query，Recall 会计算找回参考 chunk 的比例；新 balanced 每条只有一个 canonical chunk，因此 Recall 与 Hit 相等。历史值用于解释规模与数据口径变化，不代表从旧 35.69% 直接优化到新 66.11%。</div>
<p>上一阶段报告保留在 <a href="{old_link.as_posix()}">retrieval_routing_analysis_report.html</a>；本阶段没有覆盖旧文件。</p>
<h2>下一步</h2><ol><li>只在 420 条 tune 上测试单路候选保底与可观测置信度特征，不按场景直接切单路。</li><li>权重、阈值、TopK 联合搜索已完成，当前默认保持不变；后续优化应转向融合候选保底或学习型门控。</li><li>路由规则冻结后创建新的 blind 版本或等待下一批真实 query；当前 180 条 blind 不再用于参数选择。</li></ol>
</main></body></html>""",
        encoding="utf-8",
    )
    if not old_report.exists():
        raise SystemExit(f"historical report missing: {old_report}")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
