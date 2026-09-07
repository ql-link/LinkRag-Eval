#!/usr/bin/env python3
"""One legacy/English comparison on saved Train/development; never discovers other roles."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from linkrag_eval.retrieval.learning_to_rank.features import (
    ENGLISH_FEATURE_VERSION,
    FEATURE_NAMES,
    FEATURE_VERSION,
)
from linkrag_eval.retrieval.learning_to_rank.online import (
    LambdaMartOnlineRanker,
    validate_production_bundle,
)
from linkrag_eval.retrieval.learning_to_rank.pairwise_training import (
    GRID,
    MAX_ITERATIONS,
    PATIENCE,
    SEED,
    assert_disjoint_roles,
    load_dataset,
    train_and_select,
    training_parameters,
)

CHANGED_COLUMNS = {"identifier_exact_coverage", "number_exact_coverage", "negation_overlap_coverage",
                   "negation_mismatch", "condition_coverage"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_rows(path):
    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                          encoding="utf-8")


def compare_predictions(legacy, english):
    if [r["source_query_id"] for r in legacy] != [r["source_query_id"] for r in english]:
        raise ValueError("comparison query order/identity mismatch")
    cells, sources, pairs, records = Counter(), defaultdict(Counter), defaultdict(list), []
    for left, right in zip(legacy, english, strict=True):
        for key in ("source_group_id", "pair_id", "direction", "exclusion_reasons", "candidate_count"):
            if left[key] != right[key]:
                raise ValueError(f"comparison association mismatch: {key}")
        a, b = left["preference_relation"], right["preference_relation"]
        if (a == "unavailable") != (b == "unavailable"):
            raise ValueError("comparison eligibility differs")
        if a == "unavailable":
            cell = "not_evaluable"
        elif a == "correct":
            cell = "both_correct" if b == "correct" else "harmed"
        else:
            cell = "corrected" if b == "correct" else "neither_strictly_correct"
        cells[cell] += 1
        sources[left["source_group_id"]][cell] += 1
        pairs[left["pair_id"]].append((a, b))
        records.append({"source_query_id": left["source_query_id"], "source_group_id": left["source_group_id"],
                        "pair_id": left["pair_id"], "direction": left["direction"],
                        "legacy": a, "english": b, "cell": cell, "label_basis": "official",
                        "human_adjudication": "pending"})
    covered_pairs = [pair for pair in pairs.values() if len(pair) == 2
                     and all(a != "unavailable" and b != "unavailable" for a, b in pair)]
    return {"scheduled_queries": len(legacy), "covered_queries": len(legacy) - cells["not_evaluable"],
            "scheduled_pairs": len(pairs), "covered_pairs": len(covered_pairs),
            "four_cells": dict(cells), "source_groups": {key: dict(value) for key, value in sorted(sources.items())},
            "legacy": {"relations": dict(Counter(r["preference_relation"] for r in legacy)),
                       "paired_correct": sum(all(a == "correct" for a, _ in pair) for pair in covered_pairs)},
            "english": {"relations": dict(Counter(r["preference_relation"] for r in english)),
                        "paired_correct": sum(all(b == "correct" for _, b in pair) for pair in covered_pairs)},
            "net_corrected": cells["corrected"] - cells["harmed"],
            "label_basis": "official", "human_adjudication": "pending",
            "independent_confirmation": False}, records


def check_dataset(dataset, historical):
    for key, expected in historical.items():
        if dataset.summary[key] != expected:
            raise ValueError(f"historical {dataset.role} dataset differs: {key}")
    if dataset.summary["full_pool_ready_query_count"] != dataset.summary["planned_query_count"]:
        raise ValueError("incomplete saved candidate input")


def compare_features(left, right):
    if left.feature_version != FEATURE_VERSION or right.feature_version != ENGLISH_FEATURE_VERSION:
        raise ValueError("feature comparison version mismatch")
    if left.groups != right.groups or len(left.queries) != len(right.queries):
        raise ValueError("ranking groups differ")
    for a, b in ((left.y, right.y), (left.weights, right.weights)):
        if not np.array_equal(a, b):
            raise ValueError("training targets/weights differ")
    counters = {name: Counter() for name in FEATURE_NAMES}
    for a, b in zip(left.queries, right.queries, strict=True):
        if (a.query_id != b.query_id or a.method_view != b.method_view or a.chunk_ids != b.chunk_ids
                or a.selected_indices != b.selected_indices or a.exclusion_reasons != b.exclusion_reasons):
            raise ValueError("full candidate inputs or supervised indices differ")
        for i, name in enumerate(FEATURE_NAMES):
            x, y = a.features[:, i], b.features[:, i]
            changes = int(np.count_nonzero(x != y))
            if changes and name not in CHANGED_COLUMNS:
                raise ValueError(f"unexpected feature change: {name}")
            counters[name].update(candidate_rows=len(x), changed_candidate_rows=changes,
                                  changed_queries=int(changes > 0), legacy_nonzero=int(np.count_nonzero(x)),
                                  english_nonzero=int(np.count_nonzero(y)))
    return {name: dict(value) for name, value in counters.items()}


def run(config_path: Path, out: Path):
    config = read_json(config_path)
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    state = {"status": "running", "config": config, "groups": {}, "fits_authorized": 2,
             "roles_consumed": ["train", "development"], "feature_cache_policy": "recompute from raw snapshots; no matrix cache reads"}
    try:
        if config["groups"] != {"legacy": FEATURE_VERSION, "english": ENGLISH_FEATURE_VERSION}:
            raise ValueError("fixed legacy/English group configuration required")
        old = read_json(config["historical_selection"])
        if old["status"] != "complete" or old["seed"] != SEED or old["patience"] != PATIENCE or old["maximum_iterations_per_fit"] != MAX_ITERATIONS:
            raise ValueError("historical training selection protocol mismatch")
        picked = next(c for c in old["grid"] if c["config_id"] == old["selected_config_id"])
        current = next(c for c in GRID if c["config_id"] == picked["config_id"])
        if config["config_id"] != picked["config_id"] or training_parameters(current) != picked["params"]:
            raise ValueError("fixed selected hyperparameters differ")
        for name, version in old["versions"].items():
            if importlib.metadata.version(name) != version:
                raise ValueError(f"historical training environment differs: {name}")
        for role in ("train", "development"):
            for kind in ("queries", "supervision", "inputs"):
                path = Path(config["inputs"][role][kind]).resolve()
                if path != Path(old["input_paths"][f"{role}_{kind}"]).resolve() or not path.is_file():
                    raise ValueError(f"missing or different historical input: {role}/{kind}: {path}")
        state["fixed_params"] = picked["params"]
        state["runtime_versions"] = old["versions"]
        state["historical_b_bundle"] = validate_production_bundle(config["historical_model_b"])
        state["policy_a_bundle"] = validate_production_bundle(config["policy_source"])
        write_json(out / "comparison.json", state)
        datasets, predictions = {}, {}
        for name in ("legacy", "english"):
            version = config["groups"][name]
            print(f"Preparing {name} Train/development from saved candidates", flush=True)
            prep_started = time.perf_counter()
            train, dev = [load_dataset(role=role, feature_version=version,
                                      **{key: Path(value) for key, value in config["inputs"][role].items()})
                          for role in ("train", "development")]
            for dataset in (train, dev):
                check_dataset(dataset, old[dataset.role])
            assert_disjoint_roles(train, dev)
            if name == "english":
                state["feature_response"] = {role: compare_features(left, right)
                                             for role, left, right in zip(("train", "development"), datasets["legacy"], (train, dev), strict=True)}
            datasets[name] = (train, dev)
            state["groups"][name] = {"feature_version": version, "prepare_including_io_seconds": time.perf_counter() - prep_started,
                                     "train_feature_seconds": train.summary["feature_compute_seconds"],
                                     "development_feature_seconds": dev.summary["feature_compute_seconds"]}
            print(f"Training {name}: {len(train.blocks)} queries, one {config['config_id']} fit", flush=True)
            selected = train_and_select(train, dev, out_dir=out / name, policy_source=Path(config["policy_source"]),
                                        input_paths={f"{role}_{kind}": value for role, paths in config["inputs"].items() for kind, value in paths.items()},
                                        model_version=f"nevir-{name}-same38-20260907", config_id=config["config_id"])
            prediction = read_rows(out / name / "dev-predictions.jsonl")
            predictions[name] = prediction
            loaded = LambdaMartOnlineRanker(selected["model_path"], feature_version=version, prediction_num_threads=1)
            for item, row in zip(dev.queries, prediction, strict=True):
                scores = loaded.predict_features(item.features, feature_version=version)
                if not np.array_equal(scores, [entry["score"] for entry in row["scores"]]):
                    raise ValueError("export/reload prediction mismatch")
            state["groups"][name].update(actual_trees=selected["actual_trees"],
                                         fit_prefix_and_dev_check_seconds=selected["grid"][0]["elapsed_seconds"],
                                         fitting_export_and_prediction_seconds=selected["elapsed_seconds"],
                                         development_prediction_and_order_seconds=selected["development_prediction_and_order_seconds"],
                                         bundle_validation=validate_production_bundle(selected["model_path"]),
                                         reload_predictions_exact=True)
            np.savez_compressed(out / name / f"development-{version}.npz", **{q.query_id: q.features for q in dev.queries})
            if name == "legacy":
                previous = read_rows(config["historical_b_predictions"])
                if prediction != previous:
                    raise ValueError("legacy control differs from historical B development predictions; stop English fit")
                if (Path(selected["model_path"]) / "model.txt").read_bytes() != (Path(config["historical_model_b"]) / "model.txt").read_bytes():
                    raise ValueError("legacy control model text differs from B; investigate before English fit")
                state["legacy_reproduces_historical_b"] = True
            write_json(out / "comparison.json", state)
        summary, records = compare_predictions(predictions["legacy"], predictions["english"])
        state.update(status="completed", summary=summary, research_fits_completed=2)
        with (out / "development-comparison.jsonl").open("w", encoding="utf-8") as stream:
            for row in records:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    except (ValueError, OSError, KeyError, StopIteration, TypeError, RuntimeError) as exc:
        state.update(status="blocked", blocker={"type": type(exc).__name__, "detail": str(exc)})
        raise
    finally:
        state["elapsed_seconds"] = time.perf_counter() - started
        write_json(out / "comparison.json", state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    run(args.config, args.out)


if __name__ == "__main__":
    main()
