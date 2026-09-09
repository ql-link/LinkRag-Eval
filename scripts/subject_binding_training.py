#!/usr/bin/env python3
"""Fixed five-arm training on explicit existing Train/development snapshots only."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import time
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

import numpy as np
from subject_binding_development import (
    check_summary,
    read_json,
    read_rows,
    rules_from_config,
    write_json,
)

from linkrag_eval.retrieval.learning_to_rank.features import ENGLISH_FEATURE_VERSION
from linkrag_eval.retrieval.learning_to_rank.pairwise_training import (
    CANDIDATE_TIMEOUT_SECONDS,
    GRID,
    MAX_ITERATIONS,
    PATIENCE,
    SEED,
    _bounded_fit,
    _development_predictions,
    _layout,
    _method_view,
    assert_disjoint_roles,
    load_dataset,
    train_and_select,
    training_parameters,
)
from linkrag_eval.retrieval.learning_to_rank.subject_binding import (
    GATE_VERSION,
    RULE_VERSION,
    SHUFFLE_SEEDS,
    cache_key,
    extract,
    score_conditions,
    shuffled_subjects,
    text_hash,
    training_signal_gate,
)
from linkrag_eval.retrieval.learning_to_rank.subject_binding_model import (
    OfflineBindingModel,
    augment,
    contract,
    save_bundle,
)


def train_texts(config, out):
    out.mkdir(parents=True, exist_ok=False)
    paths = config["inputs"]["train"]
    planned = {r["source_query_id"]: r["query"] for r in read_rows(paths["queries"])}
    inputs = read_rows(paths["inputs"])
    if len(planned) != 1896 or len(inputs) != len(planned):
        raise ValueError("historical training query count differs")
    records, seen, candidate_count = {}, set(), 0
    for r in inputs:
        qid = r["source_query_id"]
        if qid in seen or qid not in planned:
            raise ValueError("duplicate or unplanned training query")
        seen.add(qid)
        view = _method_view(r, planned[qid])
        records[("query", view["query"])] = {"kind": "query", "text": view["query"]}
        for text in view["candidate_contents"].values():
            records[("paragraph", text)] = {"kind": "paragraph", "text": text}
            candidate_count += 1
    with (out / "texts.jsonl").open("x") as f:
        f.writelines(json.dumps(v, ensure_ascii=False) + "\n" for v in records.values())
    write_json(out / "summary.json", {"planned_queries": len(planned), "candidate_rows": candidate_count,
                "unique_text_roles": len(records), "roles_read": ["train"],
                "text_lengths": {kind: {"count": len(values), "min": min(values), "max": max(values),
                                        "median": float(np.median(values)), "p95": float(np.percentile(values, 95))}
                    for kind in ("query", "paragraph")
                    for values in [[len(t) for k, t in records if k == kind]]}})
    print(json.dumps({"candidate_rows": candidate_count, "unique_text_roles": len(records)}), flush=True)


def compute_scores(dataset, cache, out, *, shuffle_seed=None, rules_version=RULE_VERSION):
    parsed_queries, parsed_paragraphs = {}, {}
    by_query, timings, rows = {}, [], []
    shuffle_reports = {}
    for q in dataset.queries:
        qh = text_hash(q.query)
        if qh not in parsed_queries:
            parsed_queries[qh] = extract(q.query, read_json(cache / f"{cache_key(q.query)}.json"), query=True, rules_version=rules_version)
        query = parsed_queries[qh]
        scores = []
        load_started = time.perf_counter()
        candidates = []
        for cid in q.chunk_ids:
            text = q.method_view["candidate_contents"][cid]
            ph = text_hash(text)
            if ph not in parsed_paragraphs:
                paragraph = extract(text, read_json(cache / f"{cache_key(text)}.json"), rules_version=rules_version)
                if shuffle_seed is not None:
                    paragraph, info = shuffled_subjects(paragraph, shuffle_seed)
                    shuffle_reports[ph] = info
                parsed_paragraphs[ph] = paragraph
            candidates.append((cid, ph, parsed_paragraphs[ph]))
        loaded_seconds = time.perf_counter() - load_started
        started = time.perf_counter()
        for cid, ph, paragraph in candidates:
            result = score_conditions(query, paragraph)
            scores.append(result)
            rows.append({"source_query_id": q.query_id, "chunk_id": cid,
                         "paragraph_text_sha256": ph, "scores": result})
        timings.append({"source_query_id": q.query_id, "candidate_count": len(candidates),
                        "paragraph_load_extract_seconds": loaded_seconds,
                        "full_pool_matching_seconds": time.perf_counter() - started})
        by_query[q.query_id] = scores
    out.mkdir(parents=True, exist_ok=False)
    for filename, values in (("full-pool-scores.jsonl", rows), ("timings.jsonl", timings),
                              ("query-structures.jsonl", list(parsed_queries.values())),
                              ("paragraph-facts.jsonl", list(parsed_paragraphs.values()))):
        with (out / filename).open("x") as f:
            f.writelines(json.dumps(v, ensure_ascii=False) + "\n" for v in values)
    summary = {"rules_version": rules_version,
               "candidate_rows": len(rows), "supported_queries": sum(parsed_queries[text_hash(q.query)]["query_structure_supported"] for q in dataset.queries),
               "availability": dict(Counter(r["scores"]["availability"] for r in rows)),
               "score_distributions": {n: dict(Counter(str(r["scores"][n]) for r in rows)) for n in ("loose", "sentence", "entity")},
               "matching_seconds": sum(t["full_pool_matching_seconds"] for t in timings),
               "paragraph_load_extract_seconds": sum(t["paragraph_load_extract_seconds"] for t in timings),
               "shuffle_seed": shuffle_seed, "shuffle_effective_paragraphs": sum(s["effective"] for s in shuffle_reports.values()),
               "shuffle_reports": shuffle_reports}
    write_json(out / "summary.json", summary)
    return by_query, summary


def augmented_dataset(dataset, scores, arm, *, rules_version=RULE_VERSION):
    items = [replace(q, features=augment(q.features, scores[q.query_id], arm=arm,
                                        base_feature_version=dataset.feature_version, rules_version=rules_version))
             for q in dataset.queries]
    blocks = [q for q in items if not q.exclusion_reasons]
    result = replace(dataset, queries=items, blocks=blocks,
                     x=np.concatenate([q.features[q.selected_indices] for q in blocks]),
                     feature_version=contract(arm, rules_version=rules_version)["feature_version"])
    if [q.query_id for q in result.blocks] != [q.query_id for q in dataset.blocks]:
        raise ValueError("augmentation changed supervision")
    return result


def evaluate(predictions, subset=None):
    rows = [r for r in predictions if r["preference_relation"] != "unavailable"
            and (subset is None or r["source_query_id"] in subset)]
    counts = Counter(r["preference_relation"] for r in rows)
    sources, pairs = defaultdict(list), defaultdict(list)
    for r in rows:
        sources[r["source_group_id"]].append(r["preference_relation"] == "correct")
        pairs[r["pair_id"]].append(r["preference_relation"] == "correct")
    full_pairs = [v for v in pairs.values() if len(v) == 2]
    return {"queries": len(rows), "correct": counts["correct"], "wrong": counts["wrong"], "tie": counts["tie"],
            "strict_accuracy": counts["correct"] / len(rows) if rows else None,
            "pairs": len(full_pairs), "pair_both_correct": sum(all(p) for p in full_pairs),
            "source_macro": sum(sum(v) / len(v) for v in sources.values()) / len(sources) if sources else None,
            "source_groups": {s: {"queries": len(v), "correct": sum(v)} for s, v in sorted(sources.items())}}


def contrast(left, right):
    if [r["source_query_id"] for r in left] != [r["source_query_id"] for r in right]:
        raise ValueError("prediction query order differs")
    cells, sources = Counter(), defaultdict(Counter)
    for a, b in zip(left, right, strict=True):
        for key in ("candidate_count", "source_group_id", "pair_id", "exclusion_reasons"):
            if a[key] != b[key]:
                raise ValueError("evaluation input/eligibility differs")
        if a["preference_relation"] == "unavailable":
            continue
        x, y = a["preference_relation"] == "correct", b["preference_relation"] == "correct"
        cell = "both_correct" if x and y else "corrected" if y else "harmed" if x else "neither_correct"
        cells[cell] += 1
        sources[a["source_group_id"]][cell] += 1
    total = sum(cells.values())
    net = cells["corrected"] - cells["harmed"]
    return {"four_cells": {k: cells[k] for k in ("both_correct", "corrected", "harmed", "neither_correct")},
            "net_correct": net, "delta": net / total, "positive_sources": sum(v["corrected"] > 0 for v in sources.values()),
            "source_groups": {s: dict(v) for s, v in sorted(sources.items())},
            "leave_one_source_out": {s: (net - v["corrected"] + v["harmed"]) / (total - sum(v.values())) for s, v in sorted(sources.items())}}


def fit_arm(train, dev, *, arm, out, params, train_scores, dev_scores, rules_version=RULE_VERSION):
    import lightgbm as lgb
    out.mkdir(parents=True, exist_ok=False)
    a, b = (augmented_dataset(d, scores, arm, rules_version=rules_version) for d, scores in ((train, train_scores), (dev, dev_scores)))
    schema = contract(arm, rules_version=rules_version)
    history = []
    def progress(row):
        history.append(row)
        write_json(out / "history.json", history)
    started = time.perf_counter()
    text, fitted = _bounded_fit((a.x, a.y, a.groups, a.weights, b.x, _layout(b), params, schema["feature_names"]),
                                timeout_seconds=CANDIDATE_TIMEOUT_SECONDS, progress=progress)
    fitted.update(training_parameters=params, rounds_executed=len(history),
                  fit_with_process_seconds=time.perf_counter() - started)
    save_bundle(out / "model", text, arm=arm, fit=fitted, rules_version=rules_version)
    loaded = OfflineBindingModel(out / "model", expected_contract=schema)
    booster = lgb.Booster(model_str=text)
    started = time.perf_counter()
    predictions = _development_predictions(b, booster)
    fitted["full_pool_prediction_and_order_seconds"] = time.perf_counter() - started
    for q, row in zip(b.queries, predictions, strict=True):
        scores = loaded.predict(q.features, feature_contract=schema)
        if not np.array_equal(scores, [v["score"] for v in row["scores"]]):
            raise ValueError("pilot export/reload differs")
    with (out / "dev-predictions.jsonl").open("x") as f:
        f.writelines(json.dumps(r) + "\n" for r in predictions)
    np.savez_compressed(out / "development-features.npz", **{q.query_id: q.features for q in b.queries})
    write_json(out / "feature-cache-contract.json", schema)
    write_json(out / "fit.json", fitted)
    return predictions, fitted


def run(config, cache, out):
    version = rules_from_config(config)
    out.mkdir(parents=True, exist_ok=False)
    old = read_json(config["english_selection"])
    if (old["seed"], old["maximum_iterations_per_fit"], old["patience"]) != (SEED, MAX_ITERATIONS, PATIENCE):
        raise ValueError("historical early stopping protocol differs")
    picked = next(c for c in old["grid"] if c["config_id"] == old["selected_config_id"])
    params = training_parameters(next(c for c in GRID if c["config_id"] == config["config_id"]))
    if params != picked["params"]:
        raise ValueError("historical fixed hyperparameters differ")
    for package, version in old["versions"].items():
        if importlib.metadata.version(package) != version:
            raise ValueError(f"training environment differs: {package}")
    prep_started = time.perf_counter()
    datasets = []
    for role in ("train", "development"):
        print(f"Preparing complete {role} English38 features", flush=True)
        dataset = load_dataset(role=role, feature_version=ENGLISH_FEATURE_VERSION,
                               **{k: Path(v) for k, v in config["inputs"][role].items()})
        check_summary(dataset, old[role])
        datasets.append(dataset)
    train, dev = datasets
    assert_disjoint_roles(train, dev)
    state = {"status": "running", "roles_read": ["train", "development"], "arms": {},
             "prepare_seconds": time.perf_counter() - prep_started,
             "train": train.summary, "development": dev.summary, "parameters": params,
             "official_label_exploration_only": True, "rules_version": version}
    # Recompute eligibility from these exact inputs, even when run() is called directly
    # or a stale/incorrect stage-A summary says True. Do not fit even E0 before this check.
    train_scores, train_cost = compute_scores(train, cache, out / "train-signals", rules_version=version)
    dev_scores, dev_cost = compute_scores(dev, cache, out / "development-signals", rules_version=version)
    gates = {"development_full_pools": training_signal_gate(dev_scores),
             "train_supervised_rows": training_signal_gate({
                 q.query_id: [train_scores[q.query_id][i] for i in q.selected_indices]
                 for q in train.blocks})}
    state.update(signal_cost={"train": train_cost, "development": dev_cost}, training_signal_gates=gates)
    if not all(g["allowed"] for g in gates.values()):
        state.update(status="stopped_before_fit", stop_reason="insufficient_numeric_aggregation_contrast")
        write_json(out / "results.json", state)
        print(json.dumps({"status": state["status"], "gates": gates}), flush=True)
        return
    write_json(out / "results.json", state)
    print("Fitting E0 once; must reproduce frozen English baseline", flush=True)
    fit = train_and_select(train, dev, out_dir=out / "E0", policy_source=Path(config["policy_source"]),
                           input_paths={f"{role}_{k}": v for role, paths in config["inputs"].items() for k, v in paths.items()},
                           model_version="nevir-subject-binding-E0-20260908", config_id=config["config_id"])
    predictions = {"E0": read_rows(out / "E0/dev-predictions.jsonl"), "B": read_rows(config["history"]["B"]["predictions"])}
    if predictions["E0"] != read_rows(config["history"]["english"]["predictions"]):
        raise ValueError("E0 cannot reproduce frozen English baseline; dependent arms stopped")
    state["arms"]["E0"] = {"metrics": evaluate(predictions["E0"]), "best_iteration": fit["actual_trees"], "historical_predictions_exact": True}
    write_json(out / "results.json", state)
    available = {q.query_id for q in dev.blocks if all(dev_scores[q.query_id][i]["availability"] == "available" for i in q.selected_indices)}
    state["signal_cost"] = {"train": train_cost, "development": dev_cost}
    for arm in ("EM", "E1", "E2", "E3"):
        print(f"Fitting {arm} once", flush=True)
        pred, fitted = fit_arm(train, dev, arm=arm, out=out / arm, params=params,
                               train_scores=train_scores, dev_scores=dev_scores, rules_version=version)
        predictions[arm] = pred
        state["arms"][arm] = {"metrics": evaluate(pred), "available_subset": evaluate(pred, available), "fit": fitted}
        write_json(out / "results.json", state)
    state["arms"]["E0"]["available_subset"] = evaluate(predictions["E0"], available)
    state["history_B"] = evaluate(predictions["B"])
    state["contrasts"] = {f"{base}->{arm}": contrast(predictions[base], predictions[arm])
                          for base in ("E0", "EM", "B") for arm in ("E0", "EM", "E1", "E2", "E3") if base != arm}
    state["contrasts"].update({f"{base}->E3": contrast(predictions[base], predictions["E3"]) for base in ("E1", "E2")})
    stage_c = (all(evaluate(predictions["E3"])["correct"] > evaluate(predictions[k])["correct"] for k in ("E0", "EM", "E1", "E2", "B"))
               and all(state["contrasts"][f"{k}->E3"]["positive_sources"] > 1 for k in ("E1", "E2")))
    state["stage_c"] = {"triggered": stage_c, "seeds": list(SHUFFLE_SEEDS), "runs": []}
    if stage_c:
        for seed in SHUFFLE_SEEDS:
            folder = out / f"E3-shuffled-{seed}"
            t_scores, t_cost = compute_scores(train, cache, out / f"shuffle-train-{seed}", shuffle_seed=seed, rules_version=version)
            d_scores, d_cost = compute_scores(dev, cache, out / f"shuffle-development-{seed}", shuffle_seed=seed, rules_version=version)
            pred, fitted = fit_arm(train, dev, arm="E3", out=folder, params=params, train_scores=t_scores, dev_scores=d_scores, rules_version=version)
            state["stage_c"]["runs"].append({"seed": seed, "metrics": evaluate(pred), "fit": fitted, "train": t_cost, "development": d_cost})
            write_json(out / "results.json", state)
        state["stage_c"]["mean_correct"] = float(np.mean([r["metrics"]["correct"] for r in state["stage_c"]["runs"]]))
    state["status"] = "complete"
    state["stage_c"]["stop_reason"] = None if stage_c else "E3 did not pass preregistered superiority/multiple-source trigger"
    write_json(out / "results.json", state)
    print(json.dumps({k: {"correct": v["metrics"]["correct"], "wrong": v["metrics"]["wrong"], "tie": v["metrics"]["tie"]} for k, v in state["arms"].items()}), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["prepare-texts", "train"])
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--development-summary", type=Path, required=True)
    p.add_argument("--cache", type=Path)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    config = read_json(args.config)
    version = rules_from_config(config)
    summary = read_json(args.development_summary)
    if (summary.get("rules_version") != version
            or summary.get("training_signal_gate", {}).get("version") != GATE_VERSION):
        raise ValueError("stage A extraction/gate version mismatch; regenerate with current rules")
    if not summary["stage_b_allowed"]:
        raise ValueError("stage A stopped dependent training")
    if args.action == "prepare-texts":
        train_texts(config, args.out)
    else:
        if args.cache is None:
            p.error("train requires --cache")
        run(config, args.cache, args.out)


if __name__ == "__main__":
    main()
