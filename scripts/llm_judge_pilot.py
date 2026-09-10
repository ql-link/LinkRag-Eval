#!/usr/bin/env python3
"""Fixed-pool LLM judge pilot; command outputs must not already exist."""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path

from linkrag_eval.retrieval.learning_to_rank.llm_judge import (
    STAGE1_FEATURE,
    CodexRunner,
    baseline_order,
    baseline_scores,
    build_items,
    check_exact,
    check_judged_scope,
    evaluate_pairs,
    evaluate_rankers,
    human_population,
    judge_items,
    judged_scores,
    l2_rankers,
    plan_batches,
    read_rows,
    runtime_metadata,
    score_maps,
    stage1_scores,
    write_json,
    write_rows,
)
from linkrag_eval.retrieval.learning_to_rank.llm_judge_local import (
    OllamaRunner,
    OpenAICompatRunner,
    agreement_report,
    probe_evaluate,
    probe_items,
)

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/post_recall/llm-judge-pilot-20260910"
EXPERIMENT = ROOT / "runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment"
SAVED = ROOT / "runs/post_recall/nevir-english-features-20260907/comparison/english/dev-predictions.jsonl"
HUMAN_POLICY = ROOT / "runs/post_recall/subject-binding-pilot-20260908/human/adjudication/analysis-policy-v2.json"
HUMAN_MAPPING = ROOT / "runs/post_recall/nevir-offline-diagnostic-20260907/review/private/reviewer_1-mapping.jsonl"
SCRATCH = RUN / "items-stage1-top20"


def role_paths(role):
    return {"queries": EXPERIMENT / f"prepared/{role}/queries.jsonl",
            "supervision": EXPERIMENT / f"prepared/{role}/supervision.jsonl",
            "inputs": EXPERIMENT / f"candidates/{role}/inputs.jsonl"}


def baseline(args):
    import lightgbm as lgb
    args.out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    if args.role != "development":
        verified = json.loads((RUN / "baseline/development/summary.json").read_text())
        if verified.get("exact_match_with_saved") is not True:
            raise ValueError("development exact-match self-check required")
    paths = role_paths(args.role)
    booster = lgb.Booster(model_file=str(ROOT / "models/english-baseline/model.txt"))
    rows = baseline_scores(read_rows(paths["queries"]), read_rows(paths["inputs"]), booster)
    if args.role == "development":
        check_exact(rows, read_rows(SAVED))
    meta = runtime_metadata()
    write_rows(args.out / "scores.jsonl", [dict(r, **meta) for r in rows])
    write_json(args.out / "summary.json", dict(meta, role=args.role, queries=len(rows),
               candidate_rows=sum(len(r["scores"]) for r in rows),
               exact_match_with_saved=True if args.role == "development" else None,
               wall_seconds=time.perf_counter() - started, inputs={k: str(v) for k, v in paths.items()}))


def stage1(args):
    args.out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    paths = role_paths(args.role)
    rows = stage1_scores(read_rows(paths["queries"]), read_rows(paths["inputs"]))
    if args.role == "development":
        check_exact(rows, read_rows(SCRATCH / "development/stage1-development.jsonl"))
    write_rows(args.out / f"stage1-{args.role}.jsonl", rows)
    write_json(args.out / "summary.json", dict(runtime_metadata(), role=args.role,
               stage1=STAGE1_FEATURE, queries=len(rows), candidate_rows=sum(len(r["scores"]) for r in rows),
               exact_match_with_scratch=True if args.role == "development" else None,
               wall_seconds=time.perf_counter() - started, inputs={k: str(v) for k, v in paths.items()}))


def items(args):
    args.out.mkdir(parents=True, exist_ok=False)
    paths = role_paths(args.role)
    if (args.level == "l1" and (args.baseline is None or args.stage1 is not None)) or (
            args.level != "l1" and (args.stage1 is None or args.baseline is not None)):
        raise ValueError("L1 requires --baseline; L2/L3 require --stage1 only")
    scores = read_rows(args.baseline if args.level == "l1" else args.stage1)
    rows = build_items(**{k: read_rows(v) for k, v in paths.items()},
                       **({"predictions": scores} if args.level == "l1" else {"stage1": scores}),
                       level=args.level, top_k=args.top_k)
    exact = None
    if args.role == "development" and args.level != "l1":
        scratch = SCRATCH / "development"
        check_exact(scores, read_rows(scratch / "stage1-development.jsonl"))
        scratch_k = json.loads((scratch / "summary.json").read_text())["top_k"]
        if args.top_k > scratch_k:
            raise ValueError("development scratch items do not cover requested K")
        selected = {qid: set(baseline_order(s)[:args.top_k]) for qid, s in score_maps(scores).items()}
        expected = {(r["source_query_id"], r["chunk_id"]) for r in read_rows(scratch / "development.jsonl")
                    if r["chunk_id"] in selected[r["source_query_id"]]}
        if {(r["source_query_id"], r["chunk_id"]) for r in rows} != expected or len(rows) != len(expected):
            raise ValueError("development item query/chunk set differs from scratch")
        exact = True
    meta = runtime_metadata()
    filename = f"l1-{args.role}.jsonl" if args.level == "l1" else f"{args.role}.jsonl"
    write_rows(args.out / filename, [dict(r, **meta) for r in rows])
    write_json(args.out / "summary.json", dict(meta, role=args.role, level=args.level,
               top_k=args.top_k, items=len(rows), baseline=str(args.baseline) if args.baseline else None,
               stage1=str(args.stage1) if args.stage1 else None, exact_match_with_scratch=exact))


def build_probe_items(args):
    if args.output.exists():
        raise FileExistsError(args.output)
    write_rows(args.output, probe_items(json.loads(args.fixture.read_text())))


def evaluate_probe(args):
    if args.output.exists():
        raise FileExistsError(args.output)
    write_json(args.output, probe_evaluate(read_rows(args.items), read_rows(args.scores)))


def judge(args):
    if args.out.exists():
        raise FileExistsError(args.out)
    rows = read_rows(args.items)
    if args.smoke:
        rows = plan_batches(rows, seed=args.seed)[0][args.smoke_offset:args.smoke_offset + 3]
        if len(rows) != 3:
            raise ValueError("smoke requires three items from distinct pairs")
    batch_size = args.batch_size if args.batch_size is not None else (40 if args.runner == "codex" else 1)
    if args.runner == "codex":
        runner = CodexRunner(model=args.model, effort=args.effort, isolated_state=args.isolated_state)
    else:
        if not args.endpoint or not args.model:
            raise ValueError("local judge requires --endpoint and --model")
        if args.runner == "ollama":
            if args.api_key_env:
                raise ValueError("--api-key-env is only supported with --runner openai")
            runner = OllamaRunner(args.endpoint, args.model, num_ctx=args.num_ctx)
        else:
            api_key = os.environ.get(args.api_key_env) if args.api_key_env else None
            if args.api_key_env and not api_key:
                raise ValueError("--api-key-env must name a nonempty environment variable")
            floor = 4096 if args.think else 1024
            max_tokens = args.max_tokens if args.max_tokens is not None else max(floor, 80 * batch_size)
            runner = OpenAICompatRunner(args.endpoint, args.model, api_key=api_key, think=args.think,
                                        num_ctx=args.num_ctx, max_tokens=max_tokens)
    caches = sorted({*args.cache, *RUN.rglob("judge-cache")})
    _, summary = judge_items(rows, runner, args.out, metadata=runner.metadata,
                             cache_dirs=caches, batch_size=batch_size,
                             workers=args.workers, seed=args.seed)
    print(json.dumps(summary, indent=2))
    if args.smoke and summary["unavailable"]:
        raise RuntimeError("real smoke failed; full run must not proceed")


def agreement(args):
    if args.output.exists():
        raise FileExistsError(args.output)
    report = agreement_report(read_rows(args.a / "scores.jsonl"), read_rows(args.b / "scores.jsonl"))
    write_json(args.output, report)


def evaluation_report(role, baseline_rows, judged, summary):
    base = score_maps(baseline_rows)
    labels = read_rows(role_paths(role)["supervision"])
    official, official_rows = evaluate_pairs(labels, base, judged)
    result = {"role": role, "official": official, "judge_run": summary}
    rows = {"official": official_rows}
    if role == "development":
        human, population = human_population(HUMAN_POLICY, HUMAN_MAPPING, base)
        report, human_rows = evaluate_pairs(labels, base, judged, human=human)
        if (official["E0"]["n"], official["E0"]["strict_correct"],
                official["E0"]["both_directions_correct"], report["E0"]["strict_correct"],
                report["E0"]["reverse"], report["E0"]["model_tie"]) != (74, 44, 9, 31, 21, 0):
            raise ValueError("E0 official/human population self-check failed")
        result.update(human_v5=report, human_population=population, baseline_self_check=True)
        rows["human_v5"] = human_rows
    return result, rows


def evaluate(args):
    args.out.mkdir(parents=True, exist_ok=False)
    baseline_rows = read_rows(args.baseline)
    if args.role == "development":
        check_exact(baseline_rows, read_rows(SAVED))
    raw = read_rows(args.scores)
    judged = judged_scores(raw)
    summary = json.loads(args.scores.with_name("summary.json").read_text())
    if summary["items"] != len(raw) or any(any(r.get(k) != summary[k] for k in
            ("model", "effort", "prompt_version")) for r in raw):
        raise ValueError("judge result metadata/count mismatch")
    base = score_maps(baseline_rows)
    labels = read_rows(role_paths(args.role)["supervision"])
    expected = {r["source_query_id"]: {r["preferred_chunk_id"], r["other_chunk_id"]} for r in labels
                if r["official_label_available"] and {r["preferred_chunk_id"], r["other_chunk_id"]}
                <= base[r["source_query_id"]].keys()}
    if ({q: set(s) for q, s in judged.items()} != expected
            or any(r.get("level") != "l1" for r in raw)):
        raise ValueError("L1 requires all jointly covered designated items, including unavailable rows")
    result, rows = evaluation_report(args.role, baseline_rows, judged, summary)
    result.update({k: summary[k] for k in ("model", "effort", "codex_version", "prompt_version")})
    result.update(status="completed" if not summary["unavailable"] else "completed_with_unavailable",
                  wall_seconds=summary["wall_seconds"], batch_count=summary["batch_count"],
                  score_distribution=dict(Counter(str(r["score"]) for r in raw)),
                  cache_stats={k: summary[k] for k in ("cache_hits", "cache_misses", "duplicate_items")})
    write_json(args.out / "results.json", result)
    for name, values in rows.items():
        write_rows(args.out / f"{name}-per-query.jsonl", [dict(r, **{k: summary[k] for k in
                   ("model", "effort", "codex_version", "prompt_version")}) for r in values])
    print(json.dumps({k: result[k] for k in ("status", "official", "human_v5") if k in result}, indent=2))


def load_judge_arm(path, schema):
    rows = read_rows(path)
    for row in rows:
        if any(row.get(k) != schema[k] for k in ("model", "effort", "prompt_version")):
            raise ValueError("judge score cache does not match model contract")
        if row.get("level") not in {"l2", "l3"}:
            raise ValueError("L3 requires top-K judging, not L1 designated pairs")
    return judged_scores(rows)


def listwise_report(role, baseline_rows, rankers, orders, summary):
    # Preserve the frozen development E0/population assertions shared with L1.
    reference, _ = evaluation_report(role, baseline_rows, rankers["E0"], summary)
    labels = read_rows(role_paths(role)["supervision"])
    populations = {"official": None}
    result, rows = {"role": role, "judge_run": summary}, {}
    if role == "development":
        populations["human_v5"], population = human_population(HUMAN_POLICY, HUMAN_MAPPING, rankers["E0"])
        result.update(human_population=population, baseline_self_check=reference.get("baseline_self_check"))
    for name, human in populations.items():
        result[name], rows[name] = evaluate_rankers(labels, rankers, orders, human=human)
    return result, rows


def evaluate_l2(args):
    args.out.mkdir(parents=True, exist_ok=False)
    baseline_rows = read_rows(args.baseline)
    if args.role == "development":
        check_exact(baseline_rows, read_rows(SAVED))
    summary = json.loads(args.scores.with_name("summary.json").read_text())
    raw = read_rows(args.scores)
    if len(raw) != summary["items"]:
        raise ValueError("judge result count mismatch")
    judged = load_judge_arm(args.scores, summary)
    rankers, orders, trigger = l2_rankers(score_maps(baseline_rows), score_maps(read_rows(args.stage1)),
                                         judged, top_k=args.top_k)
    result, rows = listwise_report(args.role, baseline_rows, rankers, orders, summary)
    meta = {k: summary[k] for k in ("model", "effort", "codex_version", "prompt_version")}
    result.update(meta, K=args.top_k, stage1=STAGE1_FEATURE, trigger=trigger,
                  status="completed_with_fallback" if trigger["stage1_judge"]["fallback_queries"] else "completed",
                  inputs={k: str(getattr(args, k)) for k in ("baseline", "stage1", "scores")})
    write_json(args.out / "results.json", result)
    write_rows(args.out / "orders.jsonl", [dict(meta, source_query_id=q,
               orders={name: values[q] for name, values in orders.items()}) for q in rankers["E0"]])
    for name, values in rows.items():
        write_rows(args.out / f"{name}-per-query.jsonl", [dict(r, **meta) for r in values])
    print(json.dumps({"status": result["status"], "role": args.role, "K": args.top_k}))


def train_l3(args):
    from linkrag_eval.retrieval.learning_to_rank.features import ENGLISH_FEATURE_VERSION
    from linkrag_eval.retrieval.learning_to_rank.llm_judge_model import (
        OfflineJudgeModel,
        augmented_dataset,
        contract,
        judge_split_counts,
        save_bundle,
    )
    from linkrag_eval.retrieval.learning_to_rank.pairwise_training import (
        CANDIDATE_TIMEOUT_SECONDS,
        GRID,
        _bounded_fit,
        _development_predictions,
        _layout,
        assert_disjoint_roles,
        load_dataset,
        train_and_select,
        training_parameters,
    )
    args.out.mkdir(parents=True, exist_ok=False)
    config = json.loads(args.config.read_text())
    if config["config_id"] != "c3":
        raise ValueError("L3 requires fixed N08 c3")
    meta = runtime_metadata(args.model, args.effort)
    schema = contract(model=meta["model"], effort=meta["effort"], top_k=args.top_k)
    datasets = [load_dataset(role=role, feature_version=ENGLISH_FEATURE_VERSION,
                **{k: Path(v) for k, v in config["inputs"][role].items()}) for role in ("train", "development")]
    train, dev = datasets
    assert_disjoint_roles(train, dev)
    baseline_rows = [read_rows(path) for path in (args.train_baseline, args.dev_baseline)]
    check_exact(baseline_rows[1], read_rows(SAVED))
    stage1_rows = [read_rows(path) for path in (args.train_stage1, args.dev_stage1)]
    judged = [load_judge_arm(path, schema) for path in (args.train_scores, args.dev_scores)]
    for base, first in zip(baseline_rows, stage1_rows, strict=True):
        if {q: set(s) for q, s in score_maps(base).items()} != {q: set(s) for q, s in score_maps(first).items()}:
            raise ValueError("E0/stage1 candidate populations differ")
    a, b = [augmented_dataset(d, score_maps(base), scores, feature_contract=schema)
            for d, base, scores in zip(datasets, stage1_rows, judged, strict=True)]
    fitted_e0 = train_and_select(train, dev, out_dir=args.out / "E0",
                    policy_source=Path(config["policy_source"]), input_paths=config["inputs"],
                    model_version="llm-judge-E0-c3", config_id="c3")
    check_exact(read_rows(args.out / "E0/dev-predictions.jsonl"), read_rows(SAVED))
    params = training_parameters(next(c for c in GRID if c["config_id"] == "c3"))
    history = []
    started = time.perf_counter()
    text, fitted = _bounded_fit((a.x, a.y, a.groups, a.weights, b.x, _layout(b), params,
                               schema["feature_names"]), timeout_seconds=CANDIDATE_TIMEOUT_SECONDS,
                               progress=history.append)
    fitted.update(training_parameters=params, wall_seconds=time.perf_counter() - started, **meta)
    save_bundle(args.out / "judge-model", text, feature_contract=schema, fit=fitted)
    model = OfflineJudgeModel(args.out / "judge-model", expected_contract=schema)
    splits = judge_split_counts(model.booster)
    predictions = _development_predictions(b, model.booster)
    for q, row in zip(b.queries, predictions, strict=True):
        values = model.predict(q.features, feature_contract=schema)
        if list(values) != [v["score"] for v in row["scores"]]:
            raise ValueError("L3 model reload prediction mismatch")
    write_rows(args.out / "dev-predictions.jsonl", [dict(r, **meta) for r in predictions])
    write_rows(args.out / "fit-history.jsonl", [dict(r, **meta) for r in history])
    rankers = {"E0": score_maps(baseline_rows[1]), "stage1": score_maps(stage1_rows[1]), "L3": score_maps(predictions)}
    orders = {name: {q: baseline_order(s) for q, s in values.items()} for name, values in rankers.items()}
    report, _ = listwise_report("development", baseline_rows[1], rankers, orders, meta)
    write_json(args.out / "results.json", dict(report, **meta, E0_fit=fitted_e0, judge_fit=fitted,
               judge_feature_splits=splits, K=args.top_k, stage1=STAGE1_FEATURE,
               inputs={k: str(getattr(args, k)) for k in
                       ("config", "train_baseline", "dev_baseline", "train_stage1", "dev_stage1", "train_scores", "dev_scores")}))


def evaluate_l3(args):
    from linkrag_eval.retrieval.learning_to_rank.features import (
        ENGLISH_FEATURE_VERSION,
        build_online_features,
    )
    from linkrag_eval.retrieval.learning_to_rank.llm_judge_model import (
        OfflineJudgeModel,
        augment,
        judge_split_counts,
    )
    from linkrag_eval.retrieval.learning_to_rank.pairwise_training import _indexed, _method_view
    args.out.mkdir(parents=True, exist_ok=False)
    schema = json.loads((args.bundle / "manifest.json").read_text())["contract"]
    model = OfflineJudgeModel(args.bundle, expected_contract=schema)
    baseline_rows = read_rows(args.baseline)
    if args.role == "development":
        check_exact(baseline_rows, read_rows(SAVED))
    base, judged = score_maps(baseline_rows), load_judge_arm(args.scores, schema)
    first = score_maps(read_rows(args.stage1))
    judged = check_judged_scope(judged, first, top_k=schema["top_k"])
    paths = role_paths(args.role)
    queries, inputs = (_indexed(read_rows(paths[k])) for k in ("queries", "inputs"))
    if set(queries) != set(inputs) or set(queries) != set(base) or set(queries) != set(first):
        raise ValueError("L3 evaluation query population mismatch")
    predictions = []
    for qid, query in queries.items():
        ids, features = build_online_features(**_method_view(inputs[qid], query["query"]),
                                             feature_version=ENGLISH_FEATURE_VERSION)
        if set(base[qid]) != set(ids):
            raise ValueError("E0 candidate pool differs from L3 input")
        matrix = augment(features, ids, first[qid], judged[qid],
                         base_feature_version=ENGLISH_FEATURE_VERSION, feature_contract=schema)
        values = model.predict(matrix, feature_contract=schema)
        predictions.append({"source_query_id": qid, "scores": [{"chunk_id": cid, "score": float(v)}
                           for cid, v in zip(ids, values, strict=True)]})
    meta = json.loads(args.scores.with_name("summary.json").read_text())
    rankers = {"E0": base, "stage1": first, "L3": score_maps(predictions)}
    orders = {name: {q: baseline_order(s) for q, s in values.items()} for name, values in rankers.items()}
    report, _ = listwise_report(args.role, baseline_rows, rankers, orders, meta)
    report.update({k: meta[k] for k in ("model", "effort", "codex_version", "prompt_version")})
    report.update(judge_feature_splits=judge_split_counts(model.booster), K=schema["top_k"], stage1=STAGE1_FEATURE,
                  inputs={k: str(getattr(args, k)) for k in ("bundle", "baseline", "stage1", "scores")})
    write_rows(args.out / "predictions.jsonl", [dict(r, **{k: meta[k] for k in
               ("model", "effort", "codex_version", "prompt_version")}) for r in predictions])
    write_json(args.out / "results.json", report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, function in (("baseline-scores", baseline), ("stage1-scores", stage1), ("items", items)):
        p = sub.add_parser(name)
        p.add_argument("--out", type=Path, required=True)
        p.add_argument("--role", choices=("development", "train", "confirmation"), default="development")
        p.set_defaults(function=function)
        if name == "items":
            p.add_argument("--baseline", type=Path)
            p.add_argument("--stage1", type=Path)
            p.add_argument("--level", choices=("l1", "l2", "l3"), required=True)
            p.add_argument("--top-k", type=int, default=20)
    p = sub.add_parser("probe-items")
    p.set_defaults(function=build_probe_items)
    p.add_argument("--fixture", type=Path,
                   default=ROOT / "runs/post_recall/ood-probe-20260910/fixture.json")
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("probe-evaluate")
    p.set_defaults(function=evaluate_probe)
    p.add_argument("--items", type=Path, required=True)
    p.add_argument("--scores", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("judge")
    p.set_defaults(function=judge)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--items", type=Path, required=True)
    p.add_argument("--model")
    p.add_argument("--runner", choices=("codex", "ollama", "openai"), default="codex")
    p.add_argument("--endpoint", help="server base URL, without /v1/chat/completions or /api/chat")
    p.add_argument("--max-tokens", type=int, default=None,
                   help="OpenAI 兼容后端的生成上限；默认 max(1024, 80×batch_size)，须小于 --num-ctx")
    p.add_argument("--num-ctx", type=int, default=8192,
                   help="Ollama num_ctx；OpenAI 兼容后端仅用于校验 --max-tokens 上限（默认 8192）")
    p.add_argument("--think", action="store_true",
                   help="OpenAI 兼容后端开启 Qwen3 思考模式（effort 标签为 think，缓存与非思考运行分离；服务端需配置 reasoning parser）")
    p.add_argument("--api-key-env", help="environment variable containing the OpenAI-compatible API key")
    p.add_argument("--effort", choices=("low", "medium"), default="low")
    p.add_argument("--batch-size", type=int, help="default: 40 for codex, 1 for local runners")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--seed", type=int, default=20260910)
    p.add_argument("--cache", type=Path, action="append", default=[])
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--smoke-offset", type=int, default=0)
    p.add_argument("--isolated-state", action="store_true")
    p = sub.add_parser("agreement")
    p.set_defaults(function=agreement)
    p.add_argument("--a", type=Path, required=True)
    p.add_argument("--b", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    for name in ("evaluate-l1", "evaluate-l2", "evaluate-l3"):
        p = sub.add_parser(name)
        p.set_defaults(function={"evaluate-l1": evaluate, "evaluate-l2": evaluate_l2, "evaluate-l3": evaluate_l3}[name])
        p.add_argument("--out", type=Path, required=True)
        p.add_argument("--role", choices=("development", "confirmation"), default="development")
        p.add_argument("--baseline", type=Path, required=True)
        p.add_argument("--scores", type=Path, required=True)
        if name == "evaluate-l2":
            p.add_argument("--top-k", type=int, default=20)
        if name != "evaluate-l1":
            p.add_argument("--stage1", type=Path, required=True)
        if name == "evaluate-l3":
            p.add_argument("--bundle", type=Path, required=True)
    p = sub.add_parser("train-l3")
    p.set_defaults(function=train_l3)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--config", type=Path, required=True)
    for flag in ("train-baseline", "dev-baseline", "train-stage1", "dev-stage1", "train-scores", "dev-scores"):
        p.add_argument(f"--{flag}", type=Path, required=True)
    p.add_argument("--model")
    p.add_argument("--effort", choices=("low", "medium"), default="low")
    p.add_argument("--top-k", type=int, default=20)
    args = parser.parse_args(argv)
    args.function(args)


if __name__ == "__main__":
    main()
