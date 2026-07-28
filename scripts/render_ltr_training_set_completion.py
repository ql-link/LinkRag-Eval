#!/usr/bin/env python3
"""Validate and render the completed 2000-query LTR training-set report."""

from __future__ import annotations

import hashlib
import html
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FINAL = (
    ROOT
    / "runs/golden_v2/scale_100k_991004/scale_20k_overnight/"
    "ltr_query_expansion_2000/final_2000"
)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    build_path = FINAL / "build_report.json"
    expanded_path = FINAL / "expanded_tune_2000.jsonl"
    new_path = FINAL / "validated_new_1580.jsonl"
    build = json.loads(build_path.read_text(encoding="utf-8"))
    expanded = _read_jsonl(expanded_path)
    new = _read_jsonl(new_path)

    ids = [str(row["id"]) for row in expanded]
    queries = [str(row["query"]).strip() for row in expanded]
    chunk_ids = [
        str(row["expected_chunk_ids"][0])
        for row in expanded
        if len(row.get("expected_chunk_ids", [])) == 1
    ]
    base_chunk_ids = chunk_ids[: build["base_samples"]]
    new_chunk_ids = chunk_ids[build["base_samples"] :]
    new_types = Counter(
        str(row.get("note", "")).split("type_hint=", 1)[1].split(";", 1)[0]
        for row in new
    )
    checks = {
        "total_is_2000": len(expanded) == 2000,
        "new_is_1580": len(new) == 1580,
        "all_ids_unique": len(ids) == len(set(ids)),
        "all_queries_unique": len(queries) == len(set(queries)),
        "all_chunk_level": len(chunk_ids) == len(expanded),
        "new_positive_chunks_unique": len(new_chunk_ids) == len(set(new_chunk_ids)),
        "new_positive_chunks_disjoint_from_base": not (
            set(new_chunk_ids) & set(base_chunk_ids)
        ),
        "new_scenario_quotas_exact": dict(new_types) == build["requested_new_quotas"],
        "build_not_partial": build["partial"] is False,
    }
    if not all(checks.values()):
        raise SystemExit(f"training-set completion checks failed: {checks}")

    report = {
        "status": "complete",
        "build": build,
        "new_scenario_counts": dict(new_types),
        "quality_checks": checks,
        "full_set_chunk_reference_stats": {
            "references": len(chunk_ids),
            "unique_chunks": len(set(chunk_ids)),
            "duplicate_chunk_ids": len(
                [chunk_id for chunk_id, count in Counter(chunk_ids).items() if count > 1]
            ),
            "note": "Repeated evidence chunks exist only in the original 420-query base set.",
        },
        "artifacts": {
            "expanded_tune_2000.jsonl": {
                "rows": len(expanded),
                "sha256": _sha256(expanded_path),
            },
            "validated_new_1580.jsonl": {
                "rows": len(new),
                "sha256": _sha256(new_path),
            },
            "build_report.json": {"sha256": _sha256(build_path)},
        },
    }
    report_path = FINAL / "training_set_2000_completion_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    quota_rows = "".join(
        "<tr>"
        f"<td>{html.escape(scenario)}</td>"
        f"<td>{quota}</td><td>{build['validated_available'][scenario]}</td>"
        "<td>通过</td></tr>"
        for scenario, quota in build["requested_new_quotas"].items()
    )
    check_rows = "".join(
        f"<tr><td>{html.escape(name)}</td><td>{'通过' if passed else '失败'}</td></tr>"
        for name, passed in checks.items()
    )
    generator_rows = "".join(
        f"<tr><td>{html.escape(model)}</td><td>{count}</td></tr>"
        for model, count in build["generator_models"].items()
    )
    judge_rows = "".join(
        f"<tr><td>{html.escape(model)}</td><td>{count}</td></tr>"
        for model, count in build["judge_models"].items()
    )
    html_report = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LambdaMART 2000条训练集完成报告</title>
<style>body{{font:15px/1.65 system-ui;margin:0;background:#f6f8fa;color:#17212b}}
main{{max-width:1080px;margin:24px auto;background:#fff;padding:30px;border:1px solid #d0d7de}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}.card{{border:1px solid #d0d7de;padding:12px}}
.card strong{{display:block;font-size:24px}}table{{width:100%;border-collapse:collapse;margin:14px 0}}
th,td{{border:1px solid #d0d7de;padding:8px;text-align:left}}th{{background:#eef3f7}}
.ok{{border-left:4px solid #1a7f37;padding:10px 14px;background:#dafbe1}}code{{overflow-wrap:anywhere}}
@media(max-width:760px){{main{{margin:0;border:0}}.grid{{grid-template-columns:1fr 1fr}}}}</style>
</head><body><main><h1>LambdaMART 2000条训练集完成报告</h1>
<p class="ok"><b>状态：完成。</b>最终训练集已通过严格配额、chunk级证据、Query唯一，以及新增正证据Chunk唯一且不与基集重叠的门禁。</p>
<div class="grid"><div class="card">训练集<strong>{len(expanded)}</strong></div>
<div class="card">原有样本<strong>{build['base_samples']}</strong></div>
<div class="card">严格新增<strong>{build['new_samples']}</strong></div>
<div class="card">已盲审候选<strong>{build['validated_query_coverage']}</strong></div></div>
<h2>场景配额</h2><table><thead><tr><th>场景</th><th>入选</th><th>验证可用</th><th>状态</th></tr></thead>
<tbody>{quota_rows}</tbody></table>
<h2>质量门禁</h2><table><thead><tr><th>检查</th><th>结果</th></tr></thead><tbody>{check_rows}</tbody></table>
<h2>模型构成</h2><h3>Query生成</h3><table><thead><tr><th>模型</th><th>候选数</th></tr></thead>
<tbody>{generator_rows}</tbody></table><h3>独立判定</h3><table><thead><tr><th>模型</th><th>判定数</th></tr></thead>
<tbody>{judge_rows}</tbody></table>
<h2>筛选损耗</h2><p>无完整证据：{build['rejected'].get('judge_null', 0)}；
正证据Chunk重复：{build['rejected'].get('duplicate_positive_chunk', 0)}；
Query重复：{build['rejected'].get('duplicate_query', 0)}。</p>
<p>原有420条基集中有30个证据Chunk被多个不同Query复用；新增1580条不存在该问题，且不与基集证据重复。</p>
<h2>最终产物</h2><p><code>final_2000/expanded_tune_2000.jsonl</code><br>
SHA-256：<code>{report['artifacts']['expanded_tune_2000.jsonl']['sha256']}</code></p>
<p>该报告只确认训练数据完成；2000条候选缓存、重新训练和独立测试结果应作为下一阶段新报告保留。</p>
</main></body></html>"""
    html_path = FINAL / "training_set_2000_completion_report.html"
    html_path.write_text(html_report, encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
