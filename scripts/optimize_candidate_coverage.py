#!/usr/bin/env python3
"""Audit candidate misses and freeze Tune-only candidate-depth routing."""

from __future__ import annotations

import argparse
import html
import itertools
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from linkrag_eval.retrieval.candidate_routing import (
    BASELINE_DEPTHS,
    BASELINE_THRESHOLDS,
    FROZEN_ROUTING_DEPTHS,
    GLOBAL_FALLBACK_DEPTHS,
    ROUTES,
    CandidateDepths,
    candidate_union_hit,
    classify_candidate_query,
    first_expected_hit,
)


GRID_DENSE = tuple(range(100, 301, 25))
GRID_SPARSE = tuple(range(25, 151, 25))
GRID_BM25 = tuple(range(75, 301, 25))
AUDIT_24H_IDS = {
    "blind-v2-20260718-number-time-0033",
    "blind-v2-20260718-number-time-0031",
    "blind-v2-20260718-number-time-0042",
    "blind-v2-20260718-number-time-0011",
}
AUDIT_INVALID_EXACT_IDS = {"blind-v2-20260718-exact-identifier-0066"}
_TEXT_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+", re.IGNORECASE)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _row_id(row: dict[str, Any]) -> str:
    return str(row.get("sample_id") or row.get("id"))


def _merge_rows(base_path: Path, deep_path: Path) -> list[dict[str, Any]]:
    rows = {_row_id(row): row for row in _read_jsonl(base_path)}
    rows.update({_row_id(row): row for row in _read_jsonl(deep_path)})
    return list(rows.values())


def _coverage(rows: Iterable[dict[str, Any]], depths: CandidateDepths) -> tuple[int, int]:
    values = list(rows)
    hits = sum(candidate_union_hit(row, depths) for row in values)
    return hits, len(values)


def _routed_coverage(
    rows: Iterable[dict[str, Any]],
    *,
    thresholds: dict[str, float] = BASELINE_THRESHOLDS,
) -> tuple[int, int, float]:
    values = list(rows)
    hits = 0
    budget = 0
    for row in values:
        depths = FROZEN_ROUTING_DEPTHS[classify_candidate_query(str(row["query"]))]
        hits += candidate_union_hit(row, depths, thresholds=thresholds)
        budget += depths.budget
    return hits, len(values), budget / len(values) if values else 0.0


def _grid(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for dense, sparse, bm25 in itertools.product(GRID_DENSE, GRID_SPARSE, GRID_BM25):
        depths = CandidateDepths(dense, sparse, bm25)
        hits, count = _coverage(rows, depths)
        results.append(
            {
                **depths.as_dict(),
                "budget": depths.budget,
                "hits": hits,
                "count": count,
                "coverage": hits / count if count else 0.0,
            }
        )
    return sorted(results, key=lambda row: (-row["coverage"], row["budget"], row["dense"]))


def _pareto(grid: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best = -1.0
    out = []
    for budget in sorted({int(row["budget"]) for row in grid}):
        row = max(
            (item for item in grid if item["budget"] == budget), key=lambda item: item["coverage"]
        )
        if row["coverage"] > best:
            out.append(row)
            best = float(row["coverage"])
    return out


def _select_bucket_depths(
    rows: list[dict[str, Any]],
    *,
    target: float,
) -> CandidateDepths:
    choices = []
    for dense, sparse, bm25 in itertools.product(GRID_DENSE, GRID_SPARSE, GRID_BM25):
        depths = CandidateDepths(dense, sparse, bm25)
        hits, count = _coverage(rows, depths)
        if count and hits / count >= target:
            choices.append((depths.budget, -hits, dense, sparse, bm25))
    if not choices:
        raise RuntimeError(f"no candidate depth reaches target={target:.6f}")
    _budget, _negative_hits, dense, sparse, bm25 = min(choices)
    return CandidateDepths(dense, sparse, bm25)


def _normalized_ngrams(text: str, size: int) -> set[str]:
    compact = _TEXT_RE.sub("", text.lower())
    return {compact[index : index + size] for index in range(max(0, len(compact) - size + 1))}


def _blind_audit(
    rows: list[dict[str, Any]],
    contents: dict[str, str],
) -> list[dict[str, Any]]:
    content_trigrams = {
        chunk_id: _normalized_ngrams(value, 3) for chunk_id, value in contents.items()
    }
    audit = []
    for row in rows:
        sample_id = _row_id(row)
        expected = [str(value) for value in row.get("expected_chunk_ids", [])]
        target_content = "\n".join(contents.get(chunk_id, "") for chunk_id in expected)
        target_grams = set().union(
            *(content_trigrams.get(chunk_id, set()) for chunk_id in expected)
        )
        near_duplicates = 0
        best_duplicate_similarity = 0.0
        for chunk_id, grams in content_trigrams.items():
            if chunk_id in expected or not target_grams or not grams:
                continue
            similarity = len(target_grams & grams) / len(target_grams | grams)
            if similarity >= 0.45:
                near_duplicates += 1
            best_duplicate_similarity = max(best_duplicate_similarity, similarity)

        route_ranks = {}
        route_scores = {}
        for route in ROUTES:
            rank, score = first_expected_hit(row, route)
            route_ranks[route] = rank
            route_scores[route] = score

        flags = ["single_qrel_near_duplicate_risk"] if near_duplicates else []
        if sample_id in AUDIT_24H_IDS and "24" not in target_content:
            flags.append("unsupported_24h_condition")
        if sample_id in AUDIT_INVALID_EXACT_IDS:
            flags.append("invalid_exact_identifier_gate")
        deep_hit = any(rank is not None for rank in route_ranks.values())
        diagnosis = "recovered_by_deeper_topk" if deep_hit else "not_recovered_at_300_150_300"
        if "unsupported_24h_condition" in flags or "invalid_exact_identifier_gate" in flags:
            decision = "needs_relabel"
        elif not deep_hit:
            decision = "retriever_gap"
        else:
            decision = "keep_for_regression"
        selected_depths = FROZEN_ROUTING_DEPTHS[classify_candidate_query(str(row["query"]))]
        audit.append(
            {
                "sample_id": sample_id,
                "query": row["query"],
                "scenario": row.get("scenario"),
                "routing_bucket": classify_candidate_query(str(row["query"])),
                "expected_chunk_ids": expected,
                "route_first_rank": route_ranks,
                "route_score": route_scores,
                "deep_candidate_hit": deep_hit,
                "frozen_routing_hit": candidate_union_hit(row, selected_depths),
                "flags": flags,
                "decision": decision,
                "diagnosis": diagnosis,
                "near_duplicate_count_at_jaccard_045": near_duplicates,
                "best_near_duplicate_similarity": best_duplicate_similarity,
                "target_content": target_content,
            }
        )
    return audit


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _render_html(report: dict[str, Any], audit: list[dict[str, Any]]) -> str:
    tune = report["tune"]
    blind = report["blind_v2_regression"]
    routing_rows = "".join(
        "<tr>"
        f"<td>{html.escape(bucket)}</td><td>{values['count']}</td>"
        f"<td>{_pct(values['baseline_coverage'])}</td><td>{values['dense']}</td>"
        f"<td>{values['sparse']}</td><td>{values['bm25']}</td>"
        f"<td><strong>{_pct(values['frozen_coverage'])}</strong></td></tr>"
        for bucket, values in report["routing_buckets"].items()
    )
    audit_rows = "".join(
        "<tr>"
        f"<td>{html.escape(row['sample_id'])}</td><td>{html.escape(str(row['scenario']))}</td>"
        f"<td>{html.escape(str(row['query']))}</td>"
        f"<td>{html.escape(json.dumps(row['route_first_rank'], ensure_ascii=False))}</td>"
        f"<td>{html.escape(', '.join(row['flags']) or '-')}</td>"
        f"<td>{html.escape(row['decision'])}</td></tr>"
        for row in audit
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>候选覆盖优化与 Blind v2 漏召回审计</title>
<style>
body{{margin:0;background:#f5f7f9;color:#18212b;font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
main{{max-width:1180px;margin:auto;padding:28px}} h1,h2{{letter-spacing:0}} h1{{font-size:28px;margin:0 0 6px}} h2{{font-size:19px;margin-top:30px}}
.muted{{color:#5c6875}} .cards{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:18px 0}}
.card{{background:#fff;border:1px solid #dfe5eb;border-radius:6px;padding:14px}} .card b{{display:block;font-size:24px;color:#0d6b4f}}
table{{width:100%;border-collapse:collapse;background:#fff}} th,td{{border:1px solid #dfe5eb;padding:8px;text-align:left;vertical-align:top}} th{{background:#edf2f6}}
.warn{{border-left:4px solid #b86b00;background:#fff8e8;padding:12px 14px}} code{{background:#edf2f6;padding:2px 5px;border-radius:3px}}
@media(max-width:760px){{main{{padding:16px}}.cards{{grid-template-columns:1fr 1fr}}table{{display:block;overflow:auto}}}}
</style></head><body><main>
<h1>候选覆盖优化与 Blind v2 漏召回审计</h1>
<p class="muted">参数只使用 2,000 条 Tune 选择；Blind v2 仅用于冻结后的回归观察，不参与调参。</p>
<div class="cards">
<div class="card">Tune 基线覆盖<b>{_pct(tune["baseline"]["coverage"])}</b>{tune["baseline"]["hits"]}/{tune["count"]}</div>
<div class="card">Tune 分流覆盖<b>{_pct(tune["routed"]["coverage"])}</b>{tune["routed"]["hits"]}/{tune["count"]}</div>
<div class="card">Blind v2 基线覆盖<b>{_pct(blind["baseline"]["coverage"])}</b>{blind["baseline"]["hits"]}/{blind["count"]}</div>
<div class="card">Blind v2 冻结分流<b>{_pct(blind["routed"]["coverage"])}</b>{blind["routed"]["hits"]}/{blind["count"]}</div>
</div>
<h2>冻结方案</h2>
<p>无路由时使用 <code>Dense 200 / Sparse 50 / BM25 200</code>。启用确定性 Query 分流后，Tune 覆盖提升
{(tune["routed"]["coverage"] - tune["baseline"]["coverage"]) * 100:.2f}pp，平均理论候选预算从 450 降为 {tune["routed"]["average_budget"]:.2f}。</p>
<table><thead><tr><th>Query 桶</th><th>n</th><th>基线</th><th>Dense</th><th>Sparse</th><th>BM25</th><th>冻结覆盖</th></tr></thead><tbody>{routing_rows}</tbody></table>
<p>阈值维持 <code>0.30 / 0.20 / 0</code>；本轮零阈值与当前阈值的覆盖相同。保护位无法补回候选池外 Chunk，故不新增保护规则；
编号精确覆盖继续由 LambdaMART 的 <code>identifier_exact_coverage</code> 特征处理，不在缺少有效 exact Tune 样本时手工设加分系数。</p>
<h2>Blind v2 审计结论</h2>
<div class="warn">23 条原始候选缺失中，22 条可在 300/150/300 深度内找回；1 条三路仍未找回。
另有 4 条 Query 引入“24 小时”但目标 Chunk 不支持该条件，1 条标为 exact identifier 但 Query 无编号/日期/版本号，均应重标后再进入正式指标。</div>
<p>冻结分流把 Blind v2 候选覆盖从 {_pct(blind["baseline"]["coverage"])} 提升到 {_pct(blind["routed"]["coverage"])}。
排除 5 条待重标样本后的敏感性覆盖为 {_pct(blind["audited_valid_routed_coverage"])}。该结果仅是回归证据，不是新 Blind 验收。</p>
<table><thead><tr><th>ID</th><th>场景</th><th>Query</th><th>三路目标排名</th><th>质量标记</th><th>处理</th></tr></thead><tbody>{audit_rows}</tbody></table>
<h2>边界</h2><p>本报告优化的是正确 Chunk 是否进入候选并集，不等同于 Recall@10。最终 Top10 仍需由冻结 LambdaMART/Hybrid 排序后单独评测。</p>
</main></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tune-base", type=Path, required=True)
    parser.add_argument("--tune-deep", type=Path, required=True)
    parser.add_argument("--blind-base", type=Path, required=True)
    parser.add_argument("--blind-deep", type=Path, required=True)
    parser.add_argument("--candidate-contents", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    tune_rows = _merge_rows(args.tune_base, args.tune_deep)
    blind_rows = _merge_rows(args.blind_base, args.blind_deep)
    contents_payload = json.loads(args.candidate_contents.read_text(encoding="utf-8"))
    contents = contents_payload.get("contents", contents_payload)
    audit = _blind_audit(_read_jsonl(args.blind_deep), contents)

    tune_grid = _grid(tune_rows)
    tune_baseline_hits, tune_count = _coverage(tune_rows, BASELINE_DEPTHS)
    tune_global_hits, _ = _coverage(tune_rows, GLOBAL_FALLBACK_DEPTHS)
    tune_routed_hits, _, average_budget = _routed_coverage(tune_rows)
    tune_zero_threshold_hits, _, _ = _routed_coverage(
        tune_rows,
        thresholds={route: 0.0 for route in ROUTES},
    )
    blind_baseline_hits, blind_count = _coverage(blind_rows, BASELINE_DEPTHS)
    blind_global_hits, _ = _coverage(blind_rows, GLOBAL_FALLBACK_DEPTHS)
    blind_routed_hits, _, _ = _routed_coverage(blind_rows)

    relabel_ids = {row["sample_id"] for row in audit if row["decision"] == "needs_relabel"}
    valid_blind = [row for row in blind_rows if _row_id(row) not in relabel_ids]
    valid_routed_hits, valid_count, _ = _routed_coverage(valid_blind)

    by_bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in tune_rows:
        by_bucket[classify_candidate_query(str(row["query"]))].append(row)
    routing_buckets = {}
    for bucket, depths in FROZEN_ROUTING_DEPTHS.items():
        rows = by_bucket[bucket]
        baseline_hits, count = _coverage(rows, BASELINE_DEPTHS)
        frozen_hits, _ = _coverage(rows, depths)
        target = max(0.98, baseline_hits / count) if count else 0.0
        grid_selected = _select_bucket_depths(rows, target=target)
        valid_exact_count = sum(str(row.get("scenario")) == "exact_identifier" for row in rows)
        if bucket != "exact_identifier" and grid_selected != depths:
            raise RuntimeError(
                f"frozen routing drift for {bucket}: expected={grid_selected}, actual={depths}"
            )
        routing_buckets[bucket] = {
            "count": count,
            **depths.as_dict(),
            "budget": depths.budget,
            "target_coverage": target,
            "baseline_coverage": baseline_hits / count if count else 0.0,
            "frozen_coverage": frozen_hits / count if count else 0.0,
            "grid_selected_depths": grid_selected.as_dict(),
            "valid_exact_scenario_count": valid_exact_count,
            "selection_note": (
                "safe baseline fallback because no representative valid exact_identifier Tune sample"
                if bucket == "exact_identifier" and valid_exact_count == 0
                else "minimum candidate budget meeting target without baseline regression"
            ),
        }

    report = {
        "schema_version": "candidate-coverage-optimization-v1",
        "selection_policy": "Tune-only; Blind v2 is regression-only",
        "thresholds": BASELINE_THRESHOLDS,
        "tune": {
            "count": tune_count,
            "baseline": {
                "depths": BASELINE_DEPTHS.as_dict(),
                "hits": tune_baseline_hits,
                "coverage": tune_baseline_hits / tune_count,
            },
            "global_fallback": {
                "depths": GLOBAL_FALLBACK_DEPTHS.as_dict(),
                "hits": tune_global_hits,
                "coverage": tune_global_hits / tune_count,
            },
            "routed": {
                "hits": tune_routed_hits,
                "coverage": tune_routed_hits / tune_count,
                "average_budget": average_budget,
            },
            "zero_threshold_routed": {
                "hits": tune_zero_threshold_hits,
                "coverage": tune_zero_threshold_hits / tune_count,
            },
            "pareto_frontier": _pareto(tune_grid),
        },
        "routing_buckets": routing_buckets,
        "blind_v2_regression": {
            "count": blind_count,
            "baseline": {
                "hits": blind_baseline_hits,
                "coverage": blind_baseline_hits / blind_count,
            },
            "global_fallback": {
                "hits": blind_global_hits,
                "coverage": blind_global_hits / blind_count,
            },
            "routed": {"hits": blind_routed_hits, "coverage": blind_routed_hits / blind_count},
            "needs_relabel": len(relabel_ids),
            "audited_valid_count": valid_count,
            "audited_valid_routed_hits": valid_routed_hits,
            "audited_valid_routed_coverage": valid_routed_hits / valid_count,
        },
        "audit_summary": {
            "original_misses": len(audit),
            "deep_recovered": sum(row["deep_candidate_hit"] for row in audit),
            "deep_unrecovered": sum(not row["deep_candidate_hit"] for row in audit),
            "decisions": dict(Counter(row["decision"] for row in audit)),
            "flags": dict(Counter(flag for row in audit for flag in row["flags"])),
        },
        "ranking_decisions": {
            "route_protection": "unchanged; protection cannot recover a chunk absent from the candidate union",
            "exact_match_boost": "no manual coefficient; retain LambdaMART identifier_exact_coverage feature",
            "hybrid_top1_protection": "unchanged",
        },
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "candidate_coverage_optimization_report.json"
    html_path = args.out_dir / "candidate_coverage_optimization_report.html"
    audit_path = args.out_dir / "blind_v2_missing_audit_23.jsonl"
    frozen_path = args.out_dir / "frozen_candidate_routing.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(_render_html(report, audit), encoding="utf-8")
    audit_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in audit), encoding="utf-8"
    )
    frozen_path.write_text(
        json.dumps(
            {
                "classifier": "deterministic-runtime-query-features-v1",
                "thresholds": BASELINE_THRESHOLDS,
                "global_fallback": GLOBAL_FALLBACK_DEPTHS.as_dict(),
                "routing_depths": {
                    key: asdict(value) for key, value in FROZEN_ROUTING_DEPTHS.items()
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "json": str(json_path),
                "html": str(html_path),
                "audit": str(audit_path),
                "frozen": str(frozen_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
