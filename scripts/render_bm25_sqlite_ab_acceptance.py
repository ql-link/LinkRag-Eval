#!/usr/bin/env python3
"""Validate and render the final SQLite FTS5 BM25 A/B acceptance report."""

from __future__ import annotations

import argparse
import html
import json
import math
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    required = {"run_id", "snapshot", "metrics", "per_sample"}
    missing = sorted(required - set(data))
    if missing:
        raise ValueError(f"{path} 缺少字段: {', '.join(missing)}")
    return data


def _metric(data: dict[str, Any], name: str, k: int | None) -> dict[str, Any]:
    for row in data["metrics"]:
        if row["name"] == name and row.get("k") == k:
            return row
    raise ValueError(f"{data['run_id']} 缺少指标 {name}@{k}")


def _quality(data: dict[str, Any]) -> dict[str, Any]:
    failed: dict[str, int] = {}
    failed_samples = 0
    zero_ranked = 0
    for row in data["per_sample"]:
        sources = list(row.get("failed_sources") or [])
        if sources:
            failed_samples += 1
            for source in sources:
                failed[source] = failed.get(source, 0) + 1
        if int(row.get("n_ranked") or 0) == 0:
            zero_ranked += 1
    return {
        "clean": failed_samples == 0 and zero_ranked == 0,
        "failed_samples": failed_samples,
        "failed_sources": failed,
        "zero_ranked": zero_ranked,
    }


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(p * len(ordered)) - 1))
    return ordered[index]


def _latency(data: dict[str, Any]) -> dict[str, float]:
    values = [float(row.get("elapsed_ms") or 0.0) for row in data["per_sample"]]
    return {
        "mean_ms": mean(values) if values else 0.0,
        "p50_ms": median(values) if values else 0.0,
        "p95_ms": _percentile(values, 0.95),
    }


def _assert_comparable(
    off: dict[str, Any],
    on: dict[str, Any],
    *,
    expected_dataset_ids: list[int],
) -> list[str]:
    errors: list[str] = []
    off_snapshot = off["snapshot"]
    on_snapshot = on["snapshot"]
    off_quality = _quality(off)
    on_quality = _quality(on)

    if not off_quality["clean"]:
        errors.append(f"BM25 OFF 不是 clean run: {off_quality}")
    if not on_quality["clean"]:
        errors.append(f"BM25 ON 不是 clean run: {on_quality}")
    if "bm25" in off_snapshot.get("enabled_sources", []):
        errors.append("BM25 OFF 快照仍启用了 bm25 source")
    if "bm25" not in on_snapshot.get("enabled_sources", []):
        errors.append("BM25 ON 快照未启用 bm25 source")

    for label, snapshot in (("OFF", off_snapshot), ("ON", on_snapshot)):
        if snapshot.get("bm25_mode") != "sqlite_fts5":
            errors.append(f"BM25 {label} 未记录 bm25_mode=sqlite_fts5")
        identity = snapshot.get("bm25_sidecar_identity") or {}
        if identity.get("backend") != "sqlite_fts5" or not identity.get("exists"):
            errors.append(f"BM25 {label} 缺少有效 SQLite sidecar identity")
        if not identity.get("content_sha256") or int(identity.get("chunk_count") or 0) <= 0:
            errors.append(f"BM25 {label} sidecar 逻辑指纹或 chunk_count 无效")
        if not snapshot.get("computer_fingerprint"):
            errors.append(f"BM25 {label} 缺少 computer_fingerprint")
        if not snapshot.get("git_sha") or snapshot.get("git_sha") == "unknown":
            errors.append(f"BM25 {label} 缺少有效 git SHA")
        if not snapshot.get("feature_version"):
            errors.append(f"BM25 {label} 缺少 feature_version")

    if (
        off_snapshot.get("bm25_sidecar_identity", {}).get("content_sha256")
        != on_snapshot.get("bm25_sidecar_identity", {}).get("content_sha256")
    ):
        errors.append("A/B 两轮使用的 SQLite sidecar 内容指纹不同")

    ignored = {"run_id", "enabled_sources"}
    for key in sorted((set(off_snapshot) | set(on_snapshot)) - ignored):
        if off_snapshot.get(key) != on_snapshot.get(key):
            errors.append(f"A/B 非 BM25 source 配置不一致: {key}")

    off_samples = [row.get("sample_id") for row in off["per_sample"]]
    on_samples = [row.get("sample_id") for row in on["per_sample"]]
    if off_samples != on_samples:
        errors.append("A/B 样本 ID 或顺序不一致")

    dataset_counts = on_snapshot.get("bm25_sidecar_identity", {}).get("dataset_counts", {})
    for dataset_id in expected_dataset_ids:
        if int(dataset_counts.get(str(dataset_id), 0)) <= 0:
            errors.append(f"SQLite sidecar 缺少预期 dataset {dataset_id}")
    return errors


def build_report(
    off: dict[str, Any],
    on: dict[str, Any],
    *,
    expected_dataset_ids: list[int],
) -> dict[str, Any]:
    errors = _assert_comparable(off, on, expected_dataset_ids=expected_dataset_ids)
    if errors:
        raise ValueError("SQLite BM25 A/B 验收失败:\n- " + "\n- ".join(errors))

    off_recall = _metric(off, "recall_chunk", 10)
    on_recall = _metric(on, "recall_chunk", 10)
    off_mrr = _metric(off, "mrr_chunk", None)
    on_mrr = _metric(on, "mrr_chunk", None)
    off_latency = _latency(off)
    on_latency = _latency(on)
    all_types = sorted(
        set(off_recall.get("by_type", {})) | set(on_recall.get("by_type", {}))
    )

    return {
        "status": "passed",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope": {
            "granularity": "chunk",
            "sample_count": len(on["per_sample"]),
            "expected_dataset_ids": expected_dataset_ids,
        },
        "off": {
            "run_id": off["run_id"],
            "quality": _quality(off),
            "recall_at_10": off_recall["mean"],
            "mrr": off_mrr["mean"],
            "latency": off_latency,
        },
        "on": {
            "run_id": on["run_id"],
            "quality": _quality(on),
            "recall_at_10": on_recall["mean"],
            "mrr": on_mrr["mean"],
            "latency": on_latency,
        },
        "delta": {
            "recall_at_10": on_recall["mean"] - off_recall["mean"],
            "mrr": on_mrr["mean"] - off_mrr["mean"],
            "latency_mean_ms": on_latency["mean_ms"] - off_latency["mean_ms"],
            "latency_p50_ms": on_latency["p50_ms"] - off_latency["p50_ms"],
            "latency_p95_ms": on_latency["p95_ms"] - off_latency["p95_ms"],
            "recall_at_10_by_type": {
                qtype: on_recall.get("by_type", {}).get(qtype, 0.0)
                - off_recall.get("by_type", {}).get(qtype, 0.0)
                for qtype in all_types
            },
            "latency_interpretation": (
                "两轮串行执行且共享外部 dense/sparse 编码服务；延迟 delta 是观测值，"
                "包含冷启动、限流和网络抖动，不能单独归因为 SQLite BM25。"
            ),
        },
        "snapshot": {
            "git_sha": on["snapshot"]["git_sha"],
            "git_dirty": on["snapshot"].get("git_dirty", False),
            "git_worktree_sha256": on["snapshot"].get("git_worktree_sha256", ""),
            "feature_version": on["snapshot"]["feature_version"],
            "computer_fingerprint": on["snapshot"]["computer_fingerprint"],
            "bm25_mode": on["snapshot"]["bm25_mode"],
            "bm25_sidecar_identity": on["snapshot"]["bm25_sidecar_identity"],
            "route_top_ks": on["snapshot"].get("route_top_ks", {}),
            "route_score_thresholds": on["snapshot"].get("route_score_thresholds", {}),
            "fusion_strategy": on["snapshot"].get("fusion_strategy"),
            "fusion_weights": on["snapshot"].get("fusion_weights", {}),
        },
    }


def render_html(report: dict[str, Any]) -> str:
    off = report["off"]
    on = report["on"]
    delta = report["delta"]
    snapshot = report["snapshot"]
    sidecar = snapshot["bm25_sidecar_identity"]
    by_type_rows = "".join(
        f"<tr><td>{html.escape(qtype)}</td><td>{value:+.2%}</td></tr>"
        for qtype, value in delta["recall_at_10_by_type"].items()
    )
    dirty_note = (
        "<p class='warn'>注意：运行时工作区包含未提交改动；Git SHA 与 git_dirty=true 已固化。</p>"
        if snapshot["git_dirty"]
        else ""
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SQLite FTS5 BM25 最终验收</title>
<style>
body{{font:15px system-ui,sans-serif;background:#f6f8fa;color:#17212b;margin:0}}
main{{max-width:1050px;margin:32px auto;background:#fff;padding:32px;border:1px solid #d0d7de;border-radius:8px}}
h1{{margin-top:0}}.pass{{color:#087443;font-weight:700}}.warn{{color:#9a4d00}}
.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}.card{{padding:16px;border:1px solid #d0d7de;border-radius:7px}}
.value{{font-size:27px;font-weight:700}}table{{border-collapse:collapse;width:100%;margin:12px 0 24px}}
th,td{{padding:9px;border:1px solid #d0d7de;text-align:left}}th{{background:#eef3f7}}
code{{background:#f1f3f5;padding:2px 5px;word-break:break-all}}
</style></head><body><main>
<h1>SQLite FTS5 BM25 最终验收</h1>
<p class="pass">PASS：A/B 两轮均为 clean run，且快照证明使用同一 SQLite FTS5 sidecar。</p>
{dirty_note}
<div class="cards">
<div class="card"><div>Recall@10 delta</div><div class="value">{delta['recall_at_10']:+.2%}</div>
<small>{off['recall_at_10']:.2%} → {on['recall_at_10']:.2%}</small></div>
<div class="card"><div>MRR delta</div><div class="value">{delta['mrr']:+.2%}</div>
<small>{off['mrr']:.2%} → {on['mrr']:.2%}</small></div>
<div class="card"><div>平均延迟 delta</div><div class="value">{delta['latency_mean_ms']:+.0f} ms</div>
<small>{off['latency']['mean_ms']:.0f} → {on['latency']['mean_ms']:.0f} ms</small></div>
</div>
<p class="warn">{html.escape(delta['latency_interpretation'])}</p>
<h2>运行质量</h2>
<table><tr><th>运行</th><th>样本</th><th>failed_sources</th><th>zero_ranked</th><th>P50</th><th>P95</th></tr>
<tr><td>BM25 OFF<br><code>{html.escape(off['run_id'])}</code></td><td>{report['scope']['sample_count']}</td>
<td>{html.escape(str(off['quality']['failed_sources']))}</td><td>{off['quality']['zero_ranked']}</td>
<td>{off['latency']['p50_ms']:.0f} ms</td><td>{off['latency']['p95_ms']:.0f} ms</td></tr>
<tr><td>BM25 ON<br><code>{html.escape(on['run_id'])}</code></td><td>{report['scope']['sample_count']}</td>
<td>{html.escape(str(on['quality']['failed_sources']))}</td><td>{on['quality']['zero_ranked']}</td>
<td>{on['latency']['p50_ms']:.0f} ms</td><td>{on['latency']['p95_ms']:.0f} ms</td></tr></table>
<h2>分场景 Recall@10 delta</h2>
<table><tr><th>场景</th><th>ON − OFF</th></tr>{by_type_rows}</table>
<h2>可复现快照</h2>
<table>
<tr><th>Git</th><td><code>{html.escape(snapshot['git_sha'])}</code> dirty={snapshot['git_dirty']}
worktree=<code>{html.escape(snapshot['git_worktree_sha256'] or 'clean')}</code></td></tr>
<tr><th>Feature</th><td><code>{html.escape(snapshot['feature_version'])}</code></td></tr>
<tr><th>Backend</th><td><code>{html.escape(snapshot['bm25_mode'])}</code></td></tr>
<tr><th>Sidecar</th><td><code>{html.escape(sidecar['path'])}</code><br>{sidecar['chunk_count']} chunks,
SHA-256 <code>{html.escape(sidecar['content_sha256'])}</code></td></tr>
<tr><th>Datasets</th><td><code>{html.escape(json.dumps(sidecar['dataset_counts'], ensure_ascii=False, sort_keys=True))}</code></td></tr>
<tr><th>参数</th><td><code>{html.escape(json.dumps({k: snapshot[k] for k in ('route_top_ks','route_score_thresholds','fusion_strategy','fusion_weights')}, ensure_ascii=False, sort_keys=True))}</code></td></tr>
<tr><th>Computer fingerprint</th><td><code>{html.escape(json.dumps(snapshot['computer_fingerprint'], ensure_ascii=False, sort_keys=True))}</code></td></tr>
</table>
</main></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--off", type=Path, required=True, help="BM25 OFF results JSON")
    parser.add_argument("--on", type=Path, required=True, help="BM25 ON results JSON")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--expected-dataset-ids", default="")
    args = parser.parse_args()

    dataset_ids = [int(value) for value in args.expected_dataset_ids.split(",") if value.strip()]
    report = build_report(
        _load(args.off),
        _load(args.on),
        expected_dataset_ids=dataset_ids,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "bm25_sqlite_fts5_ab_acceptance_report.json"
    html_path = args.out_dir / "bm25_sqlite_fts5_ab_acceptance_report.html"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    html_path.write_text(render_html(report), encoding="utf-8")
    print(json_path)
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
