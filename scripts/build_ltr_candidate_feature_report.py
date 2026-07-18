#!/usr/bin/env python3
"""Build the v1/v2/v2.1 LambdaMART candidate-feature comparison report."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _pct(value: float) -> str:
    return f"{value:.2%}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v1", type=Path, required=True)
    parser.add_argument("--v2", type=Path, required=True)
    parser.add_argument("--v21", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    reports = [("v1 分数/排名", _load(args.v1)), ("v2 候选差异", _load(args.v2)), ("v2.1 对比词实验", _load(args.v21))]
    rows = []
    machine_rows = []
    for label, report in reports:
        tune = report["tune_best"]
        external = report["external_overall"]
        scenarios = report["external_scenarios"]
        row = {
            "version": label,
            "tune_hit_at_10": tune["hit_at_10"],
            "tune_mrr": tune["mrr"],
            "external_hit_at_10": external["ltr_hit_at_10"],
            "external_mrr": external["ltr_mrr"],
            "alias_hit_at_10": scenarios["alias"]["ltr_hit_at_10"],
            "similar_docs_hit_at_10": scenarios["similar_docs"]["ltr_hit_at_10"],
            "protect_baseline_top_k": tune["protect_baseline_top_k"],
        }
        machine_rows.append(row)
        rows.append(
            "<tr>"
            f"<td>{html.escape(label)}</td><td>{_pct(row['tune_hit_at_10'])}</td>"
            f"<td>{_pct(row['tune_mrr'])}</td><td>{_pct(row['external_hit_at_10'])}</td>"
            f"<td>{_pct(row['external_mrr'])}</td><td>{_pct(row['alias_hit_at_10'])}</td>"
            f"<td>{_pct(row['similar_docs_hit_at_10'])}</td>"
            f"<td>{row['protect_baseline_top_k']}</td></tr>"
        )
    payload = {
        "evaluation_note": "116-query external set is reused regression data, not an untouched blind set",
        "selected_version": "v2 candidate_difference_v2",
        "conclusion": "partially effective: alias regression removed; overall Hit@10 and similar_docs unchanged",
        "versions": machine_rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.with_suffix(".json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.out.write_text(
        f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>LambdaMART 候选差异特征实验</title>
<style>body{{font:15px/1.65 system-ui;margin:0;background:#f6f8fa;color:#17212b}}main{{max-width:1080px;margin:24px auto;background:#fff;padding:30px;border:1px solid #d0d7de}}table{{width:100%;border-collapse:collapse}}th,td{{border:1px solid #d0d7de;padding:9px;text-align:left}}th{{background:#eef3f7}}code{{background:#eef3f7;padding:2px 5px}}.good{{color:#087443;font-weight:700}}.bad{{color:#b42318;font-weight:700}}</style></head>
<body><main><h1>LambdaMART 候选差异特征实验</h1>
<p>训练集为 1050 条 Tune，采用 5 折 OOF 选择 Hybrid 保护参数；116 条外部集已经被多轮实验复用，因此本报告只将它作为回归集，不再称为未触碰 Blind。</p>
<table><tr><th>版本</th><th>Tune Hit@10</th><th>Tune MRR</th><th>外部 Hit@10</th><th>外部 MRR</th><th>Alias Hit@10</th><th>Similar docs Hit@10</th><th>保护 TopK</th></tr>{''.join(rows)}</table>
<h2>结论</h2><ul><li class="good">v2 将 Alias 从 41.38% 提升到 44.83%，消除相对 Hybrid 的 3.45pp 下降。</li><li>v2 外部总体 Hit@10 仍为 50.00%，MRR 从 18.80% 小幅升至 18.90%，没有证明总体召回显著提升。</li><li class="bad">Similar docs 仍为 50.00%，相对 Hybrid 56.25% 仍低 6.25pp。</li><li>v2.1 在 Tune 升到 50.86%，外部却降到 48.28%，属于过拟合，已拒绝进入实现。</li></ul>
<h2>特征判断</h2><p><code>query_bigram_coverage</code> 成为第二重要特征，是 Alias 恢复的主要新增信号。编号、数字、否定及同文档差异特征在本批数据中的重要性很低；尤其 20k 语料是一文档一 Chunk，同文档候选特征恒为零。</p>
<h2>采用方案</h2><p>保留 v2：编号/日期/版本号、数字覆盖、否定一致、多条件覆盖、三路排名差、Top1/Top2 间隔、多路共同召回、Query 二/三元词覆盖及候选差异词。冻结参数为 <code>blend_alpha=1.0</code>、<code>protect_baseline_top_k=2</code>。Similar docs 后续应补充真实同主题分组或文档元数据，并建立新的未触碰 Blind 再验证。</p>
</main></body></html>""",
        encoding="utf-8",
    )
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
