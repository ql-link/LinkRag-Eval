"""Replay the fixed N=8 Test model once; retain member artifacts and show aggregates only."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import platform
import subprocess
import time
import traceback
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import lightgbm as lgb

from linkrag_eval.retrieval.learning_to_rank.features import ENGLISH_FEATURE_VERSION, FEATURE_NAMES
from linkrag_eval.retrieval.learning_to_rank.llm_judge import (
    baseline_order,
    baseline_scores,
    read_rows,
    score_maps,
    write_json,
    write_rows,
)
from linkrag_eval.retrieval.learning_to_rank.online import validate_production_bundle

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
FLOAT_TOLERANCE = 1e-12


def original_evaluator():
    path = ROOT / "runs/post_recall/nevir-test-final-20260911/evaluate_official_test.py"
    spec = importlib.util.spec_from_file_location("issue49_original_test_metrics", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def aggregate(label_rows, predictions):
    """Use the member's unchanged metrics and populations on aligned full-pool scores."""
    original = original_evaluator()
    labels = original.indexed(label_rows)
    scores = {name: score_maps(rows) for name, rows in predictions.items()}
    if set(scores) != {"E0", "fusion", "background_n8"}:
        raise ValueError("exactly the three original rankers are required")
    if any(set(values) != set(labels) for values in scores.values()):
        raise ValueError("score query population differs from supervision")
    for qid in labels:
        if any(set(values[qid]) != set(scores["E0"][qid]) for values in scores.values()):
            raise ValueError("rankers must score identical full candidate pools")
    orders = {
        name: {qid: baseline_order(values) for qid, values in rows.items()}
        for name, rows in scores.items()
    }
    covered = [qid for qid, label in labels.items() if
               {label["preferred_chunk_id"], label["other_chunk_id"]} <= set(scores["E0"][qid])]
    official = [qid for qid in covered if labels[qid]["official_label_available"]]
    primary = [qid for qid in official if not labels[qid]["structural_conflict"]]
    populations = {"primary_no_structural_conflict": primary, "including_conflict": official}
    results, flags = {}, {}
    for population_name, population in populations.items():
        results[population_name], flags[population_name] = {}, {}
        for name, values in scores.items():
            result, correct = original.metrics(labels, orders[name], values, population)
            results[population_name][name] = result
            flags[population_name][name] = correct
    return {
        "coverage": {
            "all_queries": len(labels),
            "both_designated_in_candidate_union": len(covered),
            "both_designated_in_fusion_top20": sum(
                {label["preferred_chunk_id"], label["other_chunk_id"]}
                <= set(orders["fusion"][qid][:20]) for qid, label in labels.items()
            ),
            "official_and_covered": len(official),
            "primary_no_structural_conflict": len(primary),
        },
        "results": results,
        "mcnemar_primary_e0_vs_background_n8": original.exact_mcnemar(
            flags["primary_no_structural_conflict"]["E0"],
            flags["primary_no_structural_conflict"]["background_n8"],
        ),
    }


def differences(actual, expected, path=""):
    """Compare all original aggregates, with exact counts and a declared float tolerance."""
    if isinstance(expected, dict) and isinstance(actual, dict) and actual.keys() == expected.keys():
        return [difference for key in expected for difference in
                differences(actual[key], expected[key], f"{path}.{key}".lstrip("."))]
    if isinstance(expected, list) and isinstance(actual, list) and len(actual) == len(expected):
        return [difference for index, value in enumerate(expected) for difference in
                differences(actual[index], value, f"{path}[{index}]")]
    if isinstance(expected, float) and isinstance(actual, (int, float)):
        same = math.isclose(actual, expected, rel_tol=0, abs_tol=FLOAT_TOLERANCE)
    else:
        same = type(actual) is type(expected) and actual == expected
    return [] if same else [{"metric": path, "actual": actual, "expected": expected}]


def reserve_output(out):
    out = Path(out)
    if any((out / name).exists() for name in ("run.json", "scores.jsonl", "results.json")):
        raise FileExistsError("replay outputs already exist; use a separate new run directory")
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "run.json", {"status": "started", "started_at": datetime.now(UTC).isoformat()})


def run(data_root, out):
    data_root, out = Path(data_root).resolve(), Path(out).resolve()
    reserve_output(out)
    record = json.loads((out / "run.json").read_text())
    started = time.perf_counter()
    try:
        runs = data_root / "runs/post_recall"
        model_dir = runs / "list-collapse-20260910/background-n8-training/model-b"
        snapshot = runs / "nevir-test-candidates-20260910/snapshot"
        member_dir = runs / "nevir-test-final-20260911"
        accepted = json.loads((snapshot.parent / "run.json").read_text())
        if accepted["status"] != "accepted" or Path(accepted["snapshot"]).resolve() != snapshot:
            raise ValueError("the declared Test snapshot must have been accepted")
        frozen = json.loads((member_dir / "frozen-config.json").read_text())
        manifest = json.loads((model_dir / "manifest.json").read_text())
        bundle = validate_production_bundle(model_dir)
        if (manifest["model_file_sha256"] != frozen["rankers"]["background_n8"]["sha256"]
                or manifest["feature_version"] != ENGLISH_FEATURE_VERSION
                or manifest["feature_names"] != FEATURE_NAMES
                or manifest["n_estimators"] != 69):
            raise ValueError("the N=8 model or feature contract changed")
        e0_dir = runs / "nevir-test-main-20260911/baseline"
        e0_summary = json.loads((e0_dir / "summary.json").read_text())
        if (e0_summary["status"] != "completed"
                or e0_summary["model"]["sha256"] != frozen["rankers"]["E0"]["sha256"]
                or Path(e0_summary["source"]).resolve() != snapshot):
            raise ValueError("saved E0 scores must use the same snapshot and fixed model")
        record.update(
            issue=49, code_revision=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            implementation="uncommitted issue49 replay.py and its synthetic tests; core code unchanged",
            command=["replay.py", "--data-root", str(data_root), "--out", str(out)],
            snapshot=str(snapshot), model=str(model_dir), model_bundle=bundle,
            model_trees=manifest["n_estimators"], feature_count=len(FEATURE_NAMES),
            versions={name: version(name) for name in ("lightgbm", "numpy", "scikit-learn")},
            python=platform.python_version(), platform=platform.platform(), num_threads=1,
            saved_e0=str(e0_dir / "scores.jsonl"),
            saved_fusion=str(runs / "nevir-test-main-20260911/inputs/stage1-test.jsonl"),
            member_results=str(member_dir / "results.json"),
            training=False, new_retrieval=False, remote_requests=0,
            exposure="Previously exposed member Test aggregates; fixed-model local replay only",
            historical_limitations=[
                "Member per-query scores and original execution logs remain unavailable",
                "Aggregate agreement cannot establish original run timing or per-query identity",
                "Original fusion version label differs from the actual feature contract",
                "Query-level Wilson/McNemar do not adjust paired/source dependence",
            ],
        )
        print(json.dumps({"stage": "load_accepted_snapshot"}), flush=True)
        queries = read_rows(snapshot / "prepared/test/queries.jsonl")
        labels = read_rows(snapshot / "prepared/test/supervision.jsonl")
        inputs = read_rows(snapshot / "candidates/test/inputs.jsonl")
        if len(queries) != 2766 or len(labels) != 2766 or len(inputs) != 2766:
            raise ValueError("official Test input counts changed")
        booster = lgb.Booster(model_file=str(model_dir / "model.txt"))
        if booster.num_trees() != 69 or booster.num_feature() != len(FEATURE_NAMES):
            raise ValueError("loaded N=8 model dimensions changed")
        print(json.dumps({"stage": "score_fixed_n8", "queries": len(queries)}), flush=True)
        scoring_started = time.perf_counter()
        predictions = baseline_scores(queries, inputs, booster)
        record["feature_and_prediction_seconds"] = time.perf_counter() - scoring_started
        record["scored_queries"] = len(predictions)
        record["scored_candidates"] = sum(len(row["scores"]) for row in predictions)
        write_rows(out / "scores.jsonl", predictions)
        del inputs
        print(json.dumps({"stage": "aggregate_and_compare"}), flush=True)
        actual = aggregate(labels, {
            "E0": read_rows(e0_dir / "scores.jsonl"),
            "fusion": read_rows(record["saved_fusion"]),
            "background_n8": predictions,
        })
        received = json.loads((member_dir / "results.json").read_text())
        expected = {key: received[key] for key in actual}
        mismatches = differences(actual, expected)
        write_json(out / "results.json", {
            "issue": 49, "record_kind": "local fixed N8 Test replay; E0/fusion from saved scores",
            **actual, "comparison": {"all_aggregates_match": not mismatches,
                                      "float_absolute_tolerance": FLOAT_TOLERANCE,
                                      "mismatches": mismatches},
        })
        record["status"] = "completed_match" if not mismatches else "completed_mismatch"
        record["comparison_mismatches"] = len(mismatches)
        print(json.dumps({"status": record["status"], "coverage": actual["coverage"],
                          "n8": actual["results"]["primary_no_structural_conflict"]["background_n8"]}),
              flush=True)
    except BaseException as exc:
        record.update(status="failed", error_type=type(exc).__name__)
        (out / "failure.txt").write_text(traceback.format_exc())
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}), flush=True)
        raise
    finally:
        record.update(completed_at=datetime.now(UTC).isoformat(),
                      wall_seconds=time.perf_counter() - started,
                      timing_scope="model validation, input loading, N8 features/prediction, score output, aggregation and comparison")
        (out / "run.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        record = run(args.data_root, args.out)
    except Exception:  # noqa: BLE001 -- Keep raw Test context out of terminal tracebacks.
        raise SystemExit("Replay failed; inspect the local run.json and failure.txt without displaying Test rows.") from None
    raise SystemExit(0 if record["status"] == "completed_match" else 1)


if __name__ == "__main__":
    main()
