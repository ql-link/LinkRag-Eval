#!/usr/bin/env python3
"""Statistics for saved judge outcomes; no inference or official Test item access."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

from linkrag_eval.retrieval.learning_to_rank.llm_judge import (
    baseline_order,
    evaluate_rankers,
    read_rows,
    score_maps,
)
from linkrag_eval.retrieval.learning_to_rank.pair_statistics import RELATIONS, comparison_table

REPO = Path(__file__).resolve().parents[1]
ROLES = ("confirmation", "development")
IDENTITY = ("source_query_id", "source_group_id", "pair_id", "direction")


def indexed(rows):
    result = {}
    for row in rows:
        qid = row.get("source_query_id")
        if not isinstance(qid, str) or not qid or qid in result:
            raise ValueError("missing or duplicate source_query_id")
        result[qid] = row
    return result


def join_reference(reference, other, keys):
    """Require identical populations, identities and shared baseline relations."""
    left, right = indexed(reference), indexed(other)
    if left.keys() != right.keys():
        raise ValueError("per-query populations differ")
    for qid, row in left.items():
        if any(row.get(k) != right[qid].get(k) for k in (*IDENTITY, *keys)):
            raise ValueError("per-query identity or baseline relation differs")


def saved_path(value):
    path = Path(value)
    return path if path.is_absolute() else REPO / path


def derive_l3(root, role):
    """Reuse evaluate-l3's official evaluate_rankers path, without rerunning models.

    Baseline provenance supplies the same prepared role supervision used by
    llm_judge_pilot.role_paths. Only that exact development/confirmation path
    is accepted; no queries, passages, items or official Test split are opened.
    """
    folder = root / f"l3s-{role}-v2-evaluation"
    report_path, prediction_path = folder / "results.json", folder / "predictions.jsonl"
    paths = [report_path, prediction_path]
    try:
        saved = json.loads(report_path.read_text())
        if saved["role"] != role:
            raise ValueError("L3 report role mismatch")
        base_path, first_path = (saved_path(saved["inputs"][k]) for k in ("baseline", "stage1"))
        summary_path = base_path.with_name("summary.json")
        paths.extend([base_path, first_path, summary_path])
        summary = json.loads(summary_path.read_text())
        labels_path = saved_path(summary["inputs"]["supervision"])
        expected = REPO / (
            "runs/post_recall/nevir-ltr-validation-20260907/"
            f"data-preparation/experiment/prepared/{role}/supervision.jsonl"
        )
        if labels_path.resolve() != expected.resolve():
            raise ValueError("L3 supervision differs from pilot role_paths; refusing to read")
        paths.append(labels_path)
        rankers = {
            name: score_maps(read_rows(path))
            for name, path in (("E0", base_path), ("stage1", first_path), ("L3", prediction_path))
        }
        orders = {
            name: {q: baseline_order(s) for q, s in scores.items()}
            for name, scores in rankers.items()
        }
        report, rows = evaluate_rankers(read_rows(labels_path), rankers, orders)
        for name in rankers:
            if (
                report["rankers"][name]["pairwise"]
                != saved["official"]["rankers"][name]["pairwise"]
            ):
                raise ValueError(f"derived {name} metrics differ from saved L3 report")
    except FileNotFoundError as exc:
        return None, {
            "status": "missing_inputs",
            "missing_path": str(exc.filename),
            "input_paths": [str(p) for p in paths],
        }
    return rows, {
        "status": "derived_and_verified",
        "input_paths": [str(p) for p in paths],
        "evaluation": "llm_judge.evaluate_rankers",
        "source_inputs": saved["inputs"],
    }


def load_extra(specs):
    extras = {}
    for spec in specs:
        selector, sep, filename = spec.partition("=")
        match = re.fullmatch(
            r"(?P<name>[A-Za-z][A-Za-z0-9_.-]*)(?::(?P<column>[A-Za-z][A-Za-z0-9_.-]*))?",
            selector,
        )
        if not sep or not filename or not match:
            raise ValueError("--extra must be ranker[:column]=path/to/per-query.jsonl")
        name, column = match.group("name", "column")
        if name in extras or name in {
            *IDENTITY,
            "E0",
            "stage1",
            "judge",
            "L3",
            "stage1_judge",
            "E0_judge",
        }:
            raise ValueError("duplicate or reserved extra ranker name")
        path = Path(filename).resolve()
        rows = read_rows(path)
        by_id = indexed(rows)
        if column is None:
            column = name if rows and name in rows[0] else "judge"
        if not rows or any(r.get(column) not in RELATIONS for r in rows):
            raise ValueError(f"extra {name} requires valid {column} relations")
        extras[name] = (by_id, path, column)
    return extras


def format_effect(stat):
    if stat["estimate"] is None:
        return "NA", "NA"
    delta = f"{100 * stat['estimate']:+.2f}"
    interval = stat["interval"]
    ci = "NA" if interval is None else f"[{100 * interval[0]:+.2f}, {100 * interval[1]:+.2f}]"
    return delta, ci


def markdown(roles, *, both=True):
    lines = []
    for role in ROLES:
        lines.extend([f"## {'确认集' if role == 'confirmation' else '开发集（已曝光）'}", ""])
        header = "| 排序器差值（a − b） | Δ 严格正确率 pp | 95% CI pp | a独对/b独对/同态 | p |"
        separator = "|---|---:|---|---:|---:|"
        if both:
            header += " Δ 双向全对 pp | 95% CI pp | n/来源组 | 缺失剔除 |"
            separator += "---:|---|---:|---:|"
        lines.extend([header, separator])
        for row in roles[role]["comparisons"]:
            delta, ci = format_effect(row["strict"])
            sign = row["sign_test"]
            p = "NA" if sign["p_value"] is None else f"{sign['p_value']:.4g}"
            line = (
                f"| {row['level']} {row['ranker_a']} − {row['ranker_b']} | {delta} | {ci} | "
                f"{sign['a_correct_b_not']}/{sign['b_correct_a_not']}/{sign['ties']} | {p} |"
            )
            if both:
                bidelta, bici = format_effect(row["bidirectional"])
                line += (
                    f" {bidelta} | {bici} | {row['strict']['n']}/{row['strict']['groups']} | "
                    f"{row['strict']['dropped_unavailable']} |"
                )
            lines.append(line)
        lines.append("")
    return "\n".join(lines)


def run(args):
    if args.out.exists():
        raise FileExistsError(f"refusing to overwrite {args.out}")
    root = args.root.resolve()
    extras = load_extra(args.extra)
    roles, populations = {}, {}
    for role in ROLES:
        l1_path = root / f"l1-{role}-eval/official-per-query.jsonl"
        l2_path = root / f"l2s-{role}-k20-v2/official-per-query.jsonl"
        l1, l2 = read_rows(l1_path), read_rows(l2_path)
        join_reference(l1, l2, ["E0"])
        populations[role] = set(indexed(l2))
        comparisons = []

        def append(rows, pairs, level, target=comparisons):
            target.extend(
                dict(r, level=level)
                for r in comparison_table(rows, pairs, seed=args.seed, repeats=args.repeats)
            )

        append(l1, [("judge", "E0")], "L1")
        append(l2, [("stage1_judge", "E0"), ("stage1_judge", "stage1"), ("E0_judge", "E0")], "L2")
        l3, provenance = derive_l3(root, role)
        if l3 is not None:
            join_reference(l2, l3, ["E0", "stage1"])
            append(l3, [("L3", "E0"), ("L3", "stage1")], "L3")
        extra_meta = {}
        for name, (by_id, path, column) in extras.items():
            matched = populations[role] & by_id.keys()
            extra_meta[name] = {
                "input_path": str(path),
                "relation_column": column,
                "matched": len(matched),
                "missing": len(l2) - len(matched),
            }
            if not matched:
                continue
            joined = []
            for row in l2:
                extra = by_id.get(row["source_query_id"], {})
                if any(k in extra and extra[k] != row[k] for k in IDENTITY):
                    raise ValueError(f"extra {name} identity mismatch")
                joined.append(dict(row, **{name: extra.get(column, "unavailable")}))
            append(joined, [(name, "E0"), (name, "stage1")], "extra")
        roles[role] = {
            "exposed": role == "development",
            "comparisons": comparisons,
            "input_paths": [str(l1_path), str(l2_path)],
            "l3": provenance,
            "extras": extra_meta,
        }
    if populations["development"] & populations["confirmation"]:
        raise ValueError("development/confirmation query populations overlap")
    for name, (by_id, _, _) in extras.items():
        if by_id.keys() - set.union(*populations.values()):
            raise ValueError(f"extra {name} contains queries outside the two official populations")
    result = {
        "seed": args.seed,
        "repeats": args.repeats,
        "alpha": 0.05,
        "code_version": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip(),
        "code_worktree_status": subprocess.check_output(
            ["git", "status", "--short"], cwd=REPO, text=True
        ).strip(),
        "command": shlex.join([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]),
        "roles": roles,
    }
    notes = (
        "差值为 a − b；pp 为百分点。严格正确仅指 strict_correct。"
        "CI 与符号检验均剔除任一排序器 unavailable 的行；双向指标剔除不完整或含缺失的配对。\n\n"
        "CI 复用 N04 来源组有放回重采样，组内全部保留，按实际抽中行数计算微平均；"
        "少于两个来源组不报告区间。区间描述固定候选集合的组重采样稳定性。"
        "精确双侧符号检验以逐题不一致结果为单位，不校正组内相关性或多重比较。"
        "开发集已曝光，不作独立确认。\n"
    )
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    (args.out / "tables.md").write_text(markdown(roles) + "\n" + notes)
    (args.out / "README.md").write_text(
        "# 判断器统计\n\n输入：" + str(root) + " 下的 L1/L2 官方逐题关系、L3 保存预测与报告，"
        "以及 L3 报告指定的基线、融合分数和基线 summary 指定的角色监督标签。"
        "具体路径与 L3 可派生状态见 results.json；未读取官方 Test 条目。\n\n"
        f"命令：\n```sh\n{result['command']}\n```\n\n"
        f"种子 {args.seed}，重采样 {args.repeats} 次，95% 百分位区间。\n\n"
        "开源判断器到位后复跑（输出目录必须不存在）：\n```sh\n"
        f".venv/bin/python scripts/llm_judge_statistics.py run --root {shlex.quote(str(root))} "
        f"--out runs/post_recall/judge-statistics-open --seed {args.seed} --repeats {args.repeats} "
        "--extra open_judge=path/to/per-query.jsonl\n```\n\n"
        "--extra 名称[:关系列]=路径 可重复使用不同名称；显式列必须存在且关系有效。"
        "L2 用 --extra open_l2:stage1_judge=path/to/official-per-query.jsonl 读取融合破同分结果；"
        "选择 E0_judge 则读取 E0 破同分结果。未指定列时优先读取同名关系列，否则读取 judge 列。"
        "按 source_query_id 连接并自动分角色；可只提供一个角色或部分查询，缺项记 unavailable，"
        "无匹配角色不生成额外比较。重复 ID、身份冲突、域外查询和非法关系直接报错。"
        "额外排序器均相对 E0 和 stage1 比较。\n\n" + notes
    )
    print(markdown(roles, both=False))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_subparsers(dest="command", required=True).add_parser("run")
    command.add_argument(
        "--root", type=Path, default=Path("runs/post_recall/llm-judge-pilot-20260910")
    )
    command.add_argument("--out", type=Path, required=True)
    command.add_argument("--seed", type=int, default=20260910)
    command.add_argument("--repeats", type=int, default=2000)
    command.add_argument(
        "--extra", action="append", default=[], metavar="RANKER[:COLUMN]=JSONL",
        help="saved relations; select stage1_judge explicitly for fusion-tiebroken L2 results",
    )
    run(parser.parse_args(argv))


if __name__ == "__main__":
    main()
