"""Issue 22: scene-local preparation, human-review intake and offline analysis."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))
TYPES = ("original", "synonym", "entity_rename")
QWEN_REVISION = "31c69efc29464b6bb0aee1398b5a7b50a99340c3"
STATUSES = ("pending", "approved", "needs_revision", "undecided")


def utcnow():
    return datetime.now(UTC).isoformat()


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_json(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def write_rows(path, rows):
    with Path(path).open("x") as stream:
        stream.writelines(
            json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows
        )


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def scene_digest(scene):
    # Consumer: reject review decisions after their English text/targets have changed.
    return digest(
        {
            key: scene[key]
            for key in (
                "version_id",
                "source_scene_id",
                "rewrite_type",
                "revision",
                "supersedes",
                "language",
                "paragraphs",
                "queries",
                "expected_preferences",
            )
        }
    )


def review_binding(scene, original):
    if (
        original["rewrite_type"] != "original"
        or original["source_scene_id"] != scene["source_scene_id"]
        or (scene["rewrite_type"] == "original" and original["version_id"] != scene["version_id"])
    ):
        raise ValueError("review reference must be the same-scene original")
    return {
        "input_digest": scene_digest(scene),
        "reference_original_version_id": original["version_id"],
        "reference_original_digest": scene_digest(original),
    }


def load_scenes(directory=HERE):
    sources = json.loads((directory / "source/control-scenes.json").read_text())
    source_index = {s["probe_id"]: s for s in sources}
    all_rows = read_rows(directory / "scenes-original.jsonl")
    all_rows += read_rows(directory / "scenes-paraphrased.jsonl")
    by_id = {}
    superseded = set()
    for row in all_rows:
        vid = row["version_id"]
        if not isinstance(vid, str) or not vid or vid in by_id:
            raise ValueError("duplicate/empty version ID")
        if row["source_scene_id"] not in source_index or row["rewrite_type"] not in TYPES:
            raise ValueError("unknown source or rewrite type")
        if row["language"] != "en" or type(row["revision"]) is not int or row["revision"] < 1:
            raise ValueError("English scenes and positive integer revisions required")
        for field in ("paragraphs", "queries"):
            if len(row[field]) != 2 or any(
                not isinstance(t, str) or not t.strip() or not t.isascii() for t in row[field]
            ):
                raise ValueError("each scene requires two nonempty English paragraphs/queries")
        if any(type(x) is not int for x in row["expected_preferences"]) or sorted(
            row["expected_preferences"]
        ) != [0, 1]:
            raise ValueError("two opposite intended paragraph preferences required")
        if row["paragraphs"][0] == row["paragraphs"][1]:
            raise ValueError("identical paragraphs cannot express strict opposing preferences")
        if row["supersedes"]:
            old = by_id.get(row["supersedes"])
            if (
                old is None
                or old["version_id"] in superseded
                or old["source_scene_id"] != row["source_scene_id"]
                or old["rewrite_type"] != row["rewrite_type"]
                or old["revision"] + 1 != row["revision"]
            ):
                raise ValueError("revision must link to the previous same-source/type revision")
            superseded.add(old["version_id"])
        elif row["revision"] != 1:
            raise ValueError("later revisions must preserve a supersedes link")
        if row["rewrite_type"] == "original" and row["revision"] == 1:
            source = source_index[row["source_scene_id"]]
            if any(row[field] != source[field] for field in ("paragraphs", "queries")):
                raise ValueError("original v1 differs from the supplied source")
            if row["expected_preferences"] != source["intended_entity_preferences"]:
                raise ValueError("original v1 preference differs from source")
        by_id[vid] = row
    active = [row for vid, row in by_id.items() if vid not in superseded]
    for sid in source_index:
        rows = [r for r in active if r["source_scene_id"] == sid]
        if Counter(r["rewrite_type"] for r in rows) != Counter(TYPES):
            raise ValueError("each source needs one active original, synonym and renamed version")
        if len({tuple(r["expected_preferences"]) for r in rows}) != 1:
            raise ValueError("rewrite paragraph/query correspondence changed")
    if len(source_index) != 12 or len(active) != 36:
        raise ValueError("this fixed probe requires 12 sources / 36 active versions")
    active.sort(
        key=lambda r: (
            list(source_index).index(r["source_scene_id"]),
            TYPES.index(r["rewrite_type"]),
        )
    )
    return active, by_id


def build_items(scenes):
    from linkrag_eval.retrieval.learning_to_rank.llm_judge_local import probe_items

    items = []
    for scene in scenes:
        vid = scene["version_id"]
        fixture = {
            "english": {
                "docs": [
                    {"id": f"{vid}--p{i}", "text": text}
                    for i, text in enumerate(scene["paragraphs"])
                ],
                "queries": [
                    {
                        "id": f"{vid}--q{i}",
                        "query": query,
                        "expected_doc_id": f"{vid}--p{scene['expected_preferences'][i]}",
                        "kind": scene["category"],
                    }
                    for i, query in enumerate(scene["queries"])
                ],
            },
            "chinese": {"pairs": []},
        }
        # The legacy English API requires a shared pool WITHIN one call only.
        rows = probe_items(fixture)
        for row in rows:
            row.update(
                version_id=vid,
                source_scene_id=scene["source_scene_id"],
                rewrite_type=scene["rewrite_type"],
                content_family=scene["content_family"],
            )
        if len(rows) != 4:
            raise ValueError("expected two directions times two passages per scene")
        items.extend(rows)
    if len({(r["source_query_id"], r["chunk_id"]) for r in items}) != len(items):
        raise ValueError("cross-scene item ID collision")
    return items


def prepare(directory=HERE):
    scenes, _ = load_scenes(directory)
    items = build_items(scenes)
    originals = {s["source_scene_id"]: s for s in scenes if s["rewrite_type"] == "original"}
    payload = [{**s, **review_binding(s, originals[s["source_scene_id"]])} for s in scenes]
    encoded = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    template = (directory / "review-template.html").read_text()
    (directory / "review.html").write_text(template.replace("__SCENES_JSON__", encoded))
    template_rows = [
        {
            "version_id": s["version_id"],
            **review_binding(s, originals[s["source_scene_id"]]),
            "status": "pending",
            "reviewer": None,
            "reviewed_at": None,
            "reason": "",
            "conditions_checked": False,
            "preferences_checked": False,
            "equivalence_checked": False,
            "human_confirmed": False,
            "assistance": "",
            "source": "unfilled template; not human evidence",
        }
        for s in scenes
    ]
    path = directory / "human-review-template.jsonl"
    # This is generated blank scaffolding, never a received human submission.
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in template_rows))
    (directory / "human-review.jsonl").touch(exist_ok=True)
    return {
        "versions": len(scenes),
        "originals": 12,
        "rewrites": 24,
        "queries": len(items) // 2,
        "logical_items_per_model": len(items),
        "human_decisions": len(read_rows(directory / "human-review.jsonl")),
        "status": "awaiting_human_review",
    }


def validate_review(row, scene, original):
    if row.get("input_digest") != scene_digest(scene):
        raise ValueError("review text/target digest mismatch; re-review changed input")
    if any(row.get(k) != value for k, value in review_binding(scene, original).items()):
        raise ValueError("review original reference mismatch; re-review against current original")
    if row.get("status") not in STATUSES:
        raise ValueError("unknown review status")
    if row["status"] == "pending":
        return
    if not all(
        isinstance(row.get(k), str) and row[k].strip()
        for k in ("reviewer", "reviewed_at", "reason", "assistance")
    ):
        raise ValueError("human identity, review date, reason and assistance declaration required")
    datetime.fromisoformat(row["reviewed_at"])
    if row.get("human_confirmed") is not True:
        raise ValueError("actual reviewer must confirm this is their own human decision")
    if row["status"] == "approved" and not all(
        row.get(k) is True
        for k in ("conditions_checked", "preferences_checked", "equivalence_checked")
    ):
        raise ValueError("approval requires all three semantic checks")


def receive(path, directory=HERE):
    scenes, known = load_scenes(directory)
    originals = {s["source_scene_id"]: s for s in scenes if s["rewrite_type"] == "original"}
    rows = read_rows(path)
    seen = set()
    for row in rows:
        vid = row.get("version_id")
        if vid not in known or vid in seen:
            raise ValueError("unknown or duplicate review version")
        seen.add(vid)
        scene = known[vid]
        validate_review(row, scene, originals[scene["source_scene_id"]])
    history = directory / "human-review.jsonl"
    existing = read_rows(history)
    new = [r for r in rows if r["status"] != "pending" and r not in existing]
    if not new:
        raise ValueError("no new human decisions in this submission")
    receipt = directory / "review-submissions" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    receipt.mkdir(parents=True, exist_ok=False)
    (receipt / "original.jsonl").write_bytes(Path(path).read_bytes())
    with history.open("a") as stream:
        for row in new:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {
        "received_at": utcnow(),
        "new_decisions": len(new),
        "statuses": dict(Counter(r["status"] for r in new)),
        "receipt": str(receipt),
        "note": "Reviewer self-declaration; not independent attestation.",
    }


def approved_reviews(scenes, directory=HERE):
    _, known = load_scenes(directory)
    originals = {s["source_scene_id"]: s for s in scenes if s["rewrite_type"] == "original"}
    latest = {}
    for row in read_rows(directory / "human-review.jsonl"):
        if row["version_id"] not in known:
            raise ValueError("unknown version in review history")
        original = known.get(row.get("reference_original_version_id"))
        if original is None:
            raise ValueError("unknown original reference in review history")
        # Historical decisions remain valid evidence about their original reference;
        # only a decision about the current reference may authorize inference.
        validate_review(row, known[row["version_id"]], original)
        latest[row["version_id"]] = row
    missing = [
        s["version_id"]
        for s in scenes
        if latest.get(s["version_id"], {}).get("status") != "approved"
        or any(
            latest.get(s["version_id"], {}).get(k) != value
            for k, value in review_binding(s, originals[s["source_scene_id"]]).items()
        )
    ]
    if missing:
        raise ValueError(
            f"human review incomplete: {len(missing)} versions need approval or revision"
        )
    return [latest[s["version_id"]] for s in scenes]


def code_identity(directory=HERE):
    # Consumers: execution preflight and later attribution to an uncommitted worktree.
    paths = [directory / name for name in ("probe.py", "run_model.py")]
    paths += [ROOT / "scripts/llm_judge_pilot.py"]
    paths += [
        ROOT / "src/linkrag_eval/retrieval/learning_to_rank" / name
        for name in ("llm_judge.py", "llm_judge_local.py")
    ]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def freeze(runtime_path, directory=HERE):
    scenes, _ = load_scenes(directory)
    reviews = approved_reviews(scenes, directory)
    runtime = json.loads(Path(runtime_path).read_text())
    for key in (
        "qwen_revision",
        "qwen_server_environment",
        "qwen_deployment_evidence",
        "gpu",
        "gpt_access",
    ):
        if not isinstance(runtime.get(key), str) or not runtime[key].strip():
            raise ValueError(f"actual runtime record required: {key}")
    if runtime["qwen_revision"] != QWEN_REVISION:
        raise ValueError("Qwen revision must match research plan section 1.3")
    if runtime.get("operator_confirmed") is not True:
        raise ValueError("record actual runtime/deployment verification before freezing")
    items = build_items(scenes)
    config = {
        "status": "frozen_before_inference",
        "frozen_at": utcnow(),
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "code_files": code_identity(directory),
        "python": sys.version,
        "packages": {
            name: importlib.metadata.version(name) for name in ("numpy", "httpx", "linkrag-eval")
        },
        "codex_version": subprocess.check_output(["codex", "--version"], text=True).strip(),
        "runtime_observation": runtime,
        "items_file": "frozen/items.jsonl",
        "items_digest": digest(items),
        "scene_digests": {s["version_id"]: scene_digest(s) for s in scenes},
        "review_decisions_digest": digest(reviews),
        "prompt_version": "judge_prompt_v1",
        "score_schema": [0, 1, 2, 3, 4],
        "models": {
            "qwen": {
                "model": "Qwen/Qwen3-14B-AWQ",
                "runner": "openai",
                "revision": QWEN_REVISION,
                "think": True,
                "temperature": 0,
                "max_tokens": 6144,
                "num_ctx": 8192,
            },
            "gpt": {
                "model": "gpt-6-astra",
                "runner": "codex",
                "effort": "low",
                "weights_revision": None,
                "note": "Hosted model weights and training data unknown.",
            },
        },
        "batch_size": 1,
        "workers": {"qwen": 4, "gpt": 2},
        "seed": 20260910,
        "failure_policy": "Primary scores use the first batch attempt only. Existing CLI "
        "retries stay in raw/ and never replace primary scores; missing first output is "
        "unavailable. Interrupted/unstarted items remain unavailable and are distinguished.",
        "cache_policy": "Reject matching historical caches before invoking the existing CLI. "
        "In-run exact query/passage deduplication is logged separately.",
        "logical_items_per_model": len(items),
        "accuracy_denominator": "all planned query directions including ties/unavailable",
        "consistency_denominator": "both versions available; ties separately, strict "
        "non-tie agreement additionally reported",
        "monetary_cost": None,
    }
    if (directory / "execution-config.json").exists():
        raise FileExistsError("execution config already exists; preserve prior experiment")
    frozen = directory / "frozen"
    frozen.mkdir(exist_ok=False)
    write_rows(frozen / "items.jsonl", items)
    write_rows(frozen / "scenes.jsonl", scenes)
    write_rows(frozen / "approved-reviews.jsonl", reviews)
    write_json(directory / "execution-config.json", config)
    return {"status": config["status"], "logical_items_per_model": len(items)}


def summarize(scenes, items, scores):
    from linkrag_eval.retrieval.learning_to_rank.llm_judge_local import probe_evaluate

    key = lambda r: (r["source_query_id"], r["chunk_id"])
    if len({key(r) for r in scores}) != len(scores) or {key(r) for r in scores} != {
        key(r) for r in items
    }:
        raise ValueError("scores must cover every planned item exactly, including unavailable")
    indexed = {key(r): r for r in scores}
    directions = []
    for scene in scenes:
        subset = [r for r in items if r["version_id"] == scene["version_id"]]
        saved = [indexed[key(r)] for r in subset]
        outcome = probe_evaluate(subset, saved)  # never concatenate independent English pools
        for row in outcome["queries"]:
            i = int(row["source_query_id"].rsplit("--q", 1)[1])
            row.update(
                version_id=scene["version_id"],
                source_scene_id=scene["source_scene_id"],
                rewrite_type=scene["rewrite_type"],
                direction=i,
                content_family=scene["content_family"],
                query=scene["queries"][i],
                paragraphs=scene["paragraphs"],
                scores=[
                    indexed[(row["source_query_id"], f"{scene['version_id']}--p{j}")]["score"]
                    for j in range(2)
                ],
            )
            directions.append(row)
    groups = {}
    for kind in TYPES:
        rows = [r for r in directions if r["rewrite_type"] == kind]
        counts = Counter(r["outcome"] for r in rows)
        groups[kind] = {
            "n_queries": len(rows),
            **{k: counts[k] for k in ("strict", "reverse", "tie", "unavailable")},
            "strict_accuracy": counts["strict"] / len(rows),
        }
    originals = {
        (r["source_scene_id"], r["direction"]): r
        for r in directions
        if r["rewrite_type"] == "original"
    }
    consistency = {}
    transitions = []
    for kind in TYPES[1:]:
        pairs = [
            (originals[(r["source_scene_id"], r["direction"])], r)
            for r in directions
            if r["rewrite_type"] == kind
        ]
        usable = [(a, b) for a, b in pairs if "unavailable" not in (a["outcome"], b["outcome"])]
        strict = [(a, b) for a, b in usable if "tie" not in (a["outcome"], b["outcome"])]
        same = sum(a["outcome"] == b["outcome"] for a, b in usable)
        both_tie = sum(a["outcome"] == b["outcome"] == "tie" for a, b in usable)
        strict_same = sum(a["outcome"] == b["outcome"] for a, b in strict)
        consistency[kind] = {
            "n_comparisons": len(pairs),
            "jointly_available": len(usable),
            "excluded_unavailable": len(pairs) - len(usable),
            "same_direction_including_both_ties": same,
            "agreement_including_both_ties": same / len(usable) if usable else None,
            "both_tie": both_tie,
            "one_side_tie": len(usable) - len(strict) - both_tie,
            "strict_non_tie_denominator": len(strict),
            "same_strict_direction": strict_same,
            "strict_direction_agreement": strict_same / len(strict) if strict else None,
            "both_correct": sum(a["outcome"] == b["outcome"] == "strict" for a, b in usable),
            "both_reverse": sum(a["outcome"] == b["outcome"] == "reverse" for a, b in usable),
        }
        transitions.extend(
            {
                "source_scene_id": b["source_scene_id"],
                "direction": b["direction"],
                "rewrite_type": kind,
                "original": a["outcome"],
                "rewrite": b["outcome"],
                "original_scores": a["scores"],
                "rewrite_scores": b["scores"],
                "original_query": a["query"],
                "rewrite_query": b["query"],
                "original_paragraphs": a["paragraphs"],
                "rewrite_paragraphs": b["paragraphs"],
            }
            for a, b in pairs
        )
    return {
        "by_type": groups,
        "consistency": consistency,
        "directions": directions,
        "transitions": transitions,
    }


def evaluate(directory=HERE):
    config = json.loads((directory / "execution-config.json").read_text())
    scenes = read_rows(directory / "frozen/scenes.jsonl")
    items = read_rows(directory / config["items_file"])
    if config["scene_digests"] != {s["version_id"]: scene_digest(s) for s in scenes}:
        raise ValueError("frozen scenes changed")
    if digest(items) != config["items_digest"]:
        raise ValueError("frozen inputs changed")
    models = {}
    for model in ("qwen", "gpt"):
        path = directory / "inference" / model
        rows = read_rows(path / "first-pass-scores.jsonl")
        meta = config["models"][model]
        effort = "think" if model == "qwen" else meta["effort"]
        if any(
            r.get("model") != meta["model"]
            or r.get("effort") != effort
            or r.get("prompt_version") != config["prompt_version"]
            for r in rows
        ):
            raise ValueError("score model/effort/prompt differs from frozen config")
        models[model] = {
            **summarize(scenes, items, rows),
            "execution": json.loads((path / "execution-summary.json").read_text()),
        }
    results = {
        "status": "first_pass_analyzed",
        "created_at": utcnow(),
        "models": models,
        "scope": "12 AI-authored English scenes; 4 repeated content families and 3 structures. "
        "Human-reviewed before inference; no official Test items.",
        "limitations": "Small wording/entity sensitivity probe. Consistency is not accuracy. "
        "Cannot establish absence of NevIR training exposure or contamination; cannot replace #20.",
    }
    lines = [
        "# Issue #22：改写探针首轮结果",
        "",
        results["scope"],
        "",
        "主正确率分母包括同分和不可用；下列数字来自首次尝试，后续重试不替换首轮。",
        "",
        "| 模型 | 类型 | 查询数 | 严格正确 | 逆序 | 同分 | 不可用 | 正确率 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, result in models.items():
        for kind, c in result["by_type"].items():
            lines.append(
                f"| {name} | {kind} | {c['n_queries']} | {c['strict']} | {c['reverse']} | "
                f"{c['tie']} | {c['unavailable']} | {c['strict_accuracy']:.2%} |"
            )
    lines += [
        "",
        "## 原版与改写的一致性",
        "",
        "一致率仅对双方可用的方向计算；双方同分计入含同分一致率，另报去除任何同分后的严格方向一致率。",
        "",
    ]
    for name, result in models.items():
        for kind, c in result["consistency"].items():
            lines.append(
                f"- {name}/{kind}：计划 {c['n_comparisons']}，双方可用 {c['jointly_available']}，"
                f"排除不可用 {c['excluded_unavailable']}；含同分一致 "
                f"{c['same_direction_including_both_ties']}/{c['jointly_available']}，"
                f"双方同分 {c['both_tie']}，单边同分 {c['one_side_tie']}；严格方向一致 "
                f"{c['same_strict_direction']}/{c['strict_non_tie_denominator']}，"
                f"两次都正确 {c['both_correct']}，两次都逆序 {c['both_reverse']}。"
            )
        examples = [
            r
            for r in result["transitions"]
            if r["original"] != r["rewrite"] or r["rewrite"] == "reverse"
        ]
        lines += [
            "",
            f"### {name}：改变判断／仍逆序的例子",
            "",
            "按固定输入顺序展示前 8 条；完整记录在 results.json。"
            if examples
            else "本轮没有符合上述条件的例子；不编造案例。",
            "",
        ]
        for row in examples[:8]:
            lines += [
                (
                    f"- {row['source_scene_id']} Q{row['direction'] + 1}/{row['rewrite_type']}："
                    f"{row['original']} → {row['rewrite']}；A/B 分数 "
                    f"{row['original_scores']} → {row['rewrite_scores']}。"
                ),
                f"  原问题：{row['original_query']} 改写问题：{row['rewrite_query']}",
            ]
    lines += [
        "",
        "## 过程与成本",
        "",
        (
            "各模型 execution-summary.json 保留起止时间、"
            "实际 HTTP 请求／Codex 进程数、缓存、重试、失败和已观测 tokens。未知费用不补成零。"
        ),
        "",
        "## 解释边界",
        "",
        (
            "仅描述固定模型在这些小样本中的措辞／实体敏感性。"
            "12 个场景共享 4 组内容和 3 种句式，不能外推总体比例。原版和改写均由 AI 起草，"
            "人工审核记录的身份与辅助方式需一并报告。双方都逆序不算正确。"
        ),
        "",
        (
            "模型训练材料未知；改写保持正确也不能证明模型未见过 NevIR，不能排除训练数据污染，"
            "不替代 #20 的正式 Test。此报告不主张任何未经核验的数据公开日期或训练截止日期。"
        ),
    ]
    if (directory / "report.md").exists() or (directory / "results.json").exists():
        raise FileExistsError("preserve existing final report/results")
    write_json(directory / "results.json", results)
    (directory / "report.md").write_text("\n".join(lines) + "\n")
    return {"status": results["status"], "models": list(models)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("prepare")
    p = subs.add_parser("receive")
    p.add_argument("submission", type=Path)
    p = subs.add_parser("freeze")
    p.add_argument("--runtime-record", type=Path, required=True)
    subs.add_parser("evaluate")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare()
    elif args.command == "receive":
        result = receive(args.submission)
    elif args.command == "freeze":
        result = freeze(args.runtime_record)
    else:
        result = evaluate()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
