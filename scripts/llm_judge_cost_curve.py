#!/usr/bin/env python3
"""Replay cached L2 scores; write cost curves without new judge calls."""
from __future__ import annotations

import argparse
import csv
import json
import shlex
import subprocess
import sys
import time
from datetime import UTC, datetime
from html import escape
from pathlib import Path

from linkrag_eval.retrieval.learning_to_rank.judge_cost_curve import (
    RoleInputs,
    curve_points,
    select_margin_threshold,
    trigger_variants,
)
from linkrag_eval.retrieval.learning_to_rank.llm_judge import (
    PROMPT_VERSION,
    judged_scores,
    read_rows,
    score_maps,
)

REPO = Path(__file__).resolve().parents[1]
ROLES = ("development", "confirmation")


def load_role(args, role, suffix):
    paths = {
        "baseline": args.root / f"baseline/{role}/scores.jsonl",
        "stage1": args.root / f"items-stage1-top20/{role}/stage1-{role}.jsonl",
        "scores": args.root / f"l2s-{role}-judge{suffix}/scores.jsonl",
        "supervision": args.candidates.parent / f"prepared/{role}/supervision.jsonl",
        "candidates": args.candidates / role / "inputs.jsonl",
    }
    paths["summary"] = paths["scores"].with_name("summary.json")
    raw = read_rows(paths["scores"])
    summary = json.loads(paths["summary"].read_text())
    metadata = {key: summary[key] for key in ("model", "effort", "prompt_version")}
    if (type(summary.get("items")) is not int or summary["items"] != len(raw)
            or any(not isinstance(value, str) or not value for value in metadata.values())
            or any(row.get(key) != value for row in raw for key, value in metadata.items())):
        raise ValueError("judge result metadata/count mismatch")
    if metadata["prompt_version"] != PROMPT_VERSION:
        raise ValueError(f"requires {PROMPT_VERSION} cached scores")
    if any(r.get("level") not in {"l2", "l3"} for r in raw):
        raise ValueError("requires top-K scores, not designated-pair L1 scores")
    inputs = RoleInputs(
        role, score_maps(read_rows(paths["baseline"])), score_maps(read_rows(paths["stage1"])),
        judged_scores(raw), read_rows(paths["supervision"]), read_rows(paths["candidates"]),
    )
    return inputs, {"paths": {k: str(v.resolve()) for k, v in paths.items()},
                    "judge_metadata": metadata}


def write_csv(path, points):
    rows = [{k: v for k, v in p.items() if k != "evaluation"} for p in points]
    with path.open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def svg_chart(role, curve, triggers):
    """Standalone SVG, fixed 0–1 accuracy axis and 0–20 cost axis."""
    parts = [('<svg xmlns="http://www.w3.org/2000/svg" width="900" height="570" '
              'viewBox="0 0 900 570" role="img">'),
             f'<title>{role}: cached judge cost versus strict accuracy</title>',
             '<rect width="900" height="570" fill="white"/>',
             '<g font-family="sans-serif" font-size="14" fill="#222">']

    def label(x, y, value, extra=""):
        parts.append(f'<text x="{x}" y="{y}" {extra}>{escape(str(value))}</text>')

    def xy(p):
        return 85 + p["mean_judged"] / 20 * 745, 435 - p["strict_accuracy"] * 350

    label(85, 32, f"{role} — strict correct / {curve[0]['n']}", 'font-size="20"')
    for i in range(6):
        y = 435 - i / 5 * 350
        parts.append(f'<path d="M85 {y} H830" stroke="#ddd"/>')
        label(70, y + 5, f"{i / 5:.1f}", 'text-anchor="end"')
    for cost in range(0, 21, 5):
        x = 85 + cost / 20 * 745
        parts.append(f'<path d="M{x} 435 v6" stroke="#333"/>')
        label(x, 460, cost, 'text-anchor="middle"')
    parts.append('<path d="M85 85 V435 H830" fill="none" stroke="#333"/>')
    label(450, 491, "Mean judged candidates per query (all queries)", 'text-anchor="middle"')
    label(23, 260, "Strict accuracy", 'transform="rotate(-90 23 260)" text-anchor="middle"')
    coords = " ".join(f"{x:.2f},{y:.2f}" for x, y in map(xy, curve))
    parts.append(f'<polyline points="{coords}" fill="none" stroke="#2864b4" stroke-width="2"/>')
    for p in curve:
        x, y = xy(p)
        parts.append(f'<circle cx="{x}" cy="{y}" r="3" fill="#2864b4">'
                     f'<title>K={p["K"]}: {p["strict_correct"]}/{p["n"]}</title></circle>')
        if p["K"] in {1, 5, 10, 20}:
            label(x, y - 12, f'K={p["K"]}', 'text-anchor="middle" font-size="12"')
    label(85, 530, "● K=1–20", 'fill="#2864b4"')
    styles = [("#666", "never_call"), ("#bd4300", "fusion_margin"),
              ("#16825d", "route_disagreement")]
    for i, (color, name) in enumerate(styles):
        p = next(p for p in triggers if p["variant"] == name)
        x, y = xy(p)
        parts.append(f'<circle cx="{x}" cy="{y}" r="7" fill="white" '
                     f'stroke="{color}" stroke-width="2"><title>{name}: '
                     f'{p["strict_correct"]}/{p["n"]}, cost={p["mean_judged"]:.3f}</title></circle>')
        label(240 + i * 200, 530, f"○ {name}", f'fill="{color}"')
    parts.append('</g></svg>')
    return "\n".join(parts) + "\n"


def tables(curves, variants):
    lines = ["confirmation", "", "|K|strict|both|pref@1|mean judged|", "|---|---|---|---|---|"]
    for p in curves["confirmation"]:
        if p["K"] in {1, 2, 3, 5, 10, 15, 20}:
            lines.append(f'|{p["K"]}|{p["strict_correct"]}|{p["both_directions_correct"]}|'
                         f'{p["preferred@1"]:.4f}|{p["mean_judged"]:.3f}|')
    for role, points in variants.items():
        lines.extend(["", role, "", "|variant|threshold|triggered fraction|mean judged|strict|both|pref@1|",
                      "|---|---|---|---|---|---|---|"])
        for p in points:
            threshold = "—" if p["threshold"] is None else f'{p["threshold"]:.8g}'
            lines.append(f'|{p["variant"]}|{threshold}|{p["triggered_fraction"]:.4f}|'
                         f'{p["mean_judged"]:.3f}|{p["strict_correct"]}|'
                         f'{p["both_directions_correct"]}|{p["preferred@1"]:.4f}|')
    return "\n".join(lines)


def run(args):
    started = time.perf_counter()
    started_at = datetime.now(UTC).isoformat()
    if args.out.exists():
        raise FileExistsError(f"refusing to overwrite {args.out}")
    if args.judge_dir_suffix and (not args.judge_dir_suffix.startswith("-")
                                  or any(c in args.judge_dir_suffix for c in "/\\")):
        raise ValueError("judge suffix must be a single directory suffix such as -qwen")
    inputs, provenance = {}, {}
    for role in ROLES:
        inputs[role], provenance[role] = load_role(args, role, args.judge_dir_suffix)
    if provenance["development"]["judge_metadata"] != provenance["confirmation"]["judge_metadata"]:
        raise ValueError("development/confirmation must use the same judge model, effort and prompt")
    # Freeze the threshold before evaluating any confirmation curve or trigger.
    selection = select_margin_threshold(inputs["development"])
    curves = {role: curve_points(value) for role, value in inputs.items()}
    variants = {role: trigger_variants(value, threshold=selection["threshold"])
                for role, value in inputs.items()}
    reference_path = args.root / "l2s-confirmation-k20-v2/results.json"
    reference = json.loads(reference_path.read_text())["official"]["rankers"]["stage1_judge"]
    check_inputs = inputs["confirmation"]
    check_provenance = provenance["confirmation"]
    if args.judge_dir_suffix:
        check_inputs, check_provenance = load_role(args, "confirmation", "")
    check_point = curve_points(check_inputs, [20])[0]
    if check_point["evaluation"] != reference:
        raise ValueError("K=20 stage1_judge reference mismatch")
    check_line = ("K=20 self-check PASS (GPT-6 confirmation stage1_judge, all pairwise/list metrics): "
                  f'strict={check_point["strict_correct"]}/{check_point["n"]}, '
                  f'both={check_point["both_directions_correct"]}, '
                  f'pref@1={check_point["preferred@1"]!r}')
    result = {
        "provenance": provenance, "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "command": shlex.join([".venv/bin/python", *sys.argv]),
        "started_at": started_at, "wall_seconds": time.perf_counter() - started,
        "timing_scope": "input loading, cached evaluation and self-check; before artifact writes",
        "selection": selection, "curves": curves, "triggers": variants,
        "self_check": {"passed": True, "reference": str(reference_path.resolve()),
                       "inputs": check_provenance, "message": check_line},
        "cost_definition": "available selected query/candidate cache scores / all role queries; "
                           "includes available entries in whole-query fallbacks; no new calls",
        "missing_definition": "selected top-K entries absent or unavailable; whole-query stage1 fallback",
        "route_definition": "routes.dense/sparse/bm25 minimum zero-based rank chunk_id; "
                            "any absent/empty route or absent query triggers and is counted",
    }
    args.out.mkdir(parents=True, exist_ok=False)
    for role in ROLES:
        write_csv(args.out / f"curve-{role}.csv", curves[role])
        write_csv(args.out / f"triggers-{role}.csv", variants[role])
        (args.out / f"curve-{role}.svg").write_text(svg_chart(role, curves[role], variants[role]))
    write_csv(args.out / "margin-threshold-development.csv", selection["sweep"])
    (args.out / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                                    allow_nan=False) + "\n")
    table_text = tables(curves, variants)
    readme = f"""# 缓存判断成本与准确率曲线

输入：`{args.root}` 下的英文 `baseline/<role>/scores.jsonl`、
`items-stage1-top20/<role>/stage1-<role>.jsonl`、`l2s-<role>-judge{args.judge_dir_suffix}/scores.jsonl`
及对应 `summary.json`（核对条数与模型／推理强度／提示词，两集必须一致）；
三路来自 `{args.candidates}/<role>/inputs.jsonl`，标签来自其同级 `prepared/<role>/supervision.jsonl`。
仅使用 validation 的 development、confirmation，不读取 NevIR 官方 Test。

```sh
{result['command']}
```

输出目录必须不存在。重跑开放模型缓存时添加 `--judge-dir-suffix=-<tag>`，选择
`l2s-<role>-judge-<tag>/scores.jsonl`，并将 `--out` 换成新目录；仍会独立核验原 GPT-6 K=20。

阈值只用开发集：扫融合前两名分差的 0–100% 分位数（步长 1%，linear），补充最大值的
下一个浮点数以覆盖严格 `<` 的全触发端点。固定 K=20，在严格正确数达到全 K 的 95%
的点中最小化平均有效判断数，成本相同取较小阈值。选定 `{selection['threshold']!r}` 后直接用于确认集。
完整阈值扫描见 `margin-threshold-development.csv`；曲线、触发 CSV、SVG 与来源/参数见 `results.json`。

成本分母是全部查询（开发 76、确认 374），准确率分母是指定对共同召回的可评价查询
（开发 74、确认 371）。判断数按有效缓存候选计，缺失数和请求槽位另列；任一选中候选
未判断即按现有 `resort` 整条查询回退，已存在的判断仍计成本。K=1 也会重建分数，跨
窗口的原始平分可能被打破，因此严格指标不必与 never-call 完全相同。
触发比例表示调用条件成立，`changed_queries` 才表示实际改序。三路使用 `routes` 中
`rank=0` 的 chunk_id，`candidate_rows` 不是逐路排序。缺失/空路视为分歧并计数。

## 报告章节草稿

本实验只重放已有判断，不产生新模型调用；成本是每查询候选判断数，不是 API 批次数、
实际 tokens、延迟或货币成本。开发集选择的阈值结果带选择偏差，确认集只报告固定阈值；
确认集 K 曲线为描述性对照，不据此再次选阈值。结果沿用官方偏好标签，不代表人工语义裁定。

{check_line}

{table_text}
"""
    (args.out / "README.md").write_text(readme)
    print(check_line)
    print(table_text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("run")
    command.add_argument("--root", type=Path, required=True)
    command.add_argument("--candidates", type=Path, required=True)
    command.add_argument("--out", type=Path, required=True)
    command.add_argument("--judge-dir-suffix", default="")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
