#!/usr/bin/env python3
"""Tune LambdaMART/Hybrid postprocessing on OOF Tune predictions, then freeze externally."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from linkrag_eval.retrieval.learning_to_rank.experiment import (
    run_ltr_cross_validation,
    run_ltr_external_evaluation,
    tune_hybrid_protection,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-cache", type=Path, required=True)
    parser.add_argument("--test-cache", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--candidate-contents", type=Path, required=True)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--n-estimators", type=int, default=24)
    args = parser.parse_args()

    cv_dir = args.out_dir / "cv"
    cv = run_ltr_cross_validation(
        args.train_cache,
        out_dir=cv_dir,
        folds=args.folds,
        candidate_contents_path=args.candidate_contents,
    )
    tuning = tune_hybrid_protection(cv["predictions"])
    args.out_dir.mkdir(parents=True, exist_ok=True)
    tuning_path = args.out_dir / "hybrid_protection_tuning.json"
    tuning_path.write_text(
        json.dumps(tuning, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    best = tuning["best"]
    external = run_ltr_external_evaluation(
        args.train_cache,
        args.test_cache,
        out_dir=args.out_dir / "external_frozen",
        candidate_contents_path=args.candidate_contents,
        n_estimators=args.n_estimators,
        historical_baseline_hit_at_10=0.39655172413793105,
        blend_alpha=float(best["blend_alpha"]),
        protect_baseline_top_k=int(best["protect_baseline_top_k"]),
    )
    summary = {
        "train_samples": external["train_samples"],
        "test_samples": external["test_samples"],
        "tune_best": best,
        "external_overall": external["overall"],
        "external_strict": external["strict_no_evidence_overlap"],
        "external_transitions": external["transitions"],
        "external_scenarios": external["scenario_overall"],
    }
    (args.out_dir / "optimization_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    tune = summary["tune_best"]
    overall = summary["external_overall"]
    strict = summary["external_strict"]
    (args.out_dir / "optimization_summary.html").write_text(
        f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LambdaMART Hybrid 保护优化</title>
<style>body{{font:15px/1.65 system-ui;margin:0;background:#f6f8fa;color:#17212b}}
main{{max-width:980px;margin:24px auto;background:#fff;padding:30px;border:1px solid #d0d7de}}
table{{width:100%;border-collapse:collapse}}th,td{{border:1px solid #d0d7de;padding:9px}}
th{{background:#eef3f7;text-align:left}}.good{{color:#087443;font-weight:700}}</style></head>
<body><main><h1>LambdaMART Hybrid TopK 保护优化</h1>
<p>只在 {summary['train_samples']} 条 Tune 的 OOF 预测上搜索参数，再冻结到
{summary['test_samples']} 条外部回归 Query。</p>
<h2>冻结配置</h2><p><code>blend_alpha={tune['blend_alpha']}</code>，
<code>protect_baseline_top_k={tune['protect_baseline_top_k']}</code>。</p>
<table><tr><th>指标</th><th>Hybrid</th><th>优化后 LambdaMART</th><th>变化</th></tr>
<tr><td>外部 Hit@10</td><td>{overall['baseline_hit_at_10']:.2%}</td>
<td>{overall['ltr_hit_at_10']:.2%}</td><td class="good">{overall['delta_hit_at_10']:+.2%}</td></tr>
<tr><td>外部 MRR</td><td>{overall['baseline_mrr']:.2%}</td>
<td>{overall['ltr_mrr']:.2%}</td><td class="good">{overall['delta_mrr']:+.2%}</td></tr>
<tr><td>严格无证据重叠 Hit@10</td><td>{strict['baseline_hit_at_10']:.2%}</td>
<td>{strict['ltr_hit_at_10']:.2%}</td><td class="good">{strict['delta_hit_at_10']:+.2%}</td></tr>
<tr><td>严格无证据重叠 MRR</td><td>{strict['baseline_mrr']:.2%}</td>
<td>{strict['ltr_mrr']:.2%}</td><td class="good">{strict['delta_mrr']:+.2%}</td></tr></table>
<p>外部迁移：新增 {summary['external_transitions'].get('gained', 0)} 条，丢失
{summary['external_transitions'].get('lost', 0)} 条。相似文档与别名仍需继续优化。</p>
</main></body></html>""",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
