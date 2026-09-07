"""Replay original A and the frozen English model on the same saved development pools."""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import time
from contextlib import ExitStack
from pathlib import Path

import lightgbm
import numpy as np

from linkrag_eval.retrieval.learning_to_rank.diagnostic_features import trace_features
from linkrag_eval.retrieval.learning_to_rank.diagnostic_trees import audit_pair
from linkrag_eval.retrieval.learning_to_rank.features import (
    ENGLISH_FEATURE_VERSION,
    FEATURE_NAMES,
    FEATURE_VERSION,
    build_online_features,
)
from linkrag_eval.retrieval.learning_to_rank.nevir_diagnostics import (
    TREE_ATOL,
    _four_cell,
    _read_rows,
    _relation,
    _review_bodies,
    _summarize_cases,
    _write_json,
    _write_rows,
    make_review_packets,
)
from linkrag_eval.retrieval.learning_to_rank.nevir_evaluation import prepare_inputs
from linkrag_eval.retrieval.learning_to_rank.online import (
    LambdaMartOnlineRanker,
    validate_production_bundle,
)

MODEL_VERSIONS = {"A": FEATURE_VERSION, "English": ENGLISH_FEATURE_VERSION}


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _unique(rows):
    indexed = {r["source_query_id"]: r for r in rows}
    if len(indexed) != len(rows):
        raise ValueError("duplicate saved query identity")
    return indexed


def _check_saved_prediction(row, saved, ids, scores):
    for key in ("source_group_id", "pair_id", "direction", "official_label_available",
                "structural_conflict", "semantic_uncertain", "semantic_review_status", "candidate_count"):
        if row[key] != saved[key]:
            raise ValueError(f"saved English association mismatch: {row['source_query_id']}/{key}")
    records = saved["scores"]
    by_id = {entry["chunk_id"]: entry["score"] for entry in records}
    if len(by_id) != len(records) or set(by_id) != set(ids):
        raise ValueError("saved English candidate population differs")
    if not np.array_equal(scores, [by_id[cid] for cid in ids]):
        raise ValueError("saved English raw scores differ")
    if saved["order"] != sorted(ids, key=lambda cid: (-by_id[cid], cid)):
        raise ValueError("saved English score order differs")
    p, o = row["preferred_chunk_id"], row["other_chunk_id"]
    relation = _relation(by_id[p], by_id[o]) if p in by_id and o in by_id else "unavailable"
    if relation != saved["preference_relation"]:
        raise ValueError("saved English official preference differs")
    if relation != "unavailable" and by_id[p] - by_id[o] != saved["score_difference"]:
        raise ValueError("saved English score difference differs")


def _column_statistics(matrices):
    combined = np.concatenate(list(matrices.values()), axis=0)
    return {name: {"rows": len(combined), "minimum": float(combined[:, i].min()),
                   "maximum": float(combined[:, i].max()), "unique_values": len(np.unique(combined[:, i])),
                   "zero_count": int(np.count_nonzero(combined[:, i] == 0)),
                   "nonzero_count": int(np.count_nonzero(combined[:, i]))}
            for i, name in enumerate(FEATURE_NAMES)}


def run(*, experiment_dir: Path, model_a: Path, model_english: Path,
        saved_english_predictions: Path, previous_diagnostic: Path, out: Path):
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    files = {"queries": experiment_dir / "prepared/development/queries.jsonl",
             "supervision": experiment_dir / "prepared/development/supervision.jsonl",
             "inputs": experiment_dir / "candidates/development/inputs.jsonl",
             "passage_mapping": experiment_dir / "prepared/passage-mapping.jsonl",
             "saved_english_predictions": saved_english_predictions,
             "english_selection": saved_english_predictions.parent / "selection.json",
             "english_features": saved_english_predictions.parent / f"development-{ENGLISH_FEATURE_VERSION}.npz",
             "previous_manifest": previous_diagnostic / "manifest.json",
             "previous_predictions": previous_diagnostic / "raw-predictions.jsonl",
             "previous_features": previous_diagnostic / "model-inputs.npz",
             "previous_traces": previous_diagnostic / "feature-traces.jsonl",
             "previous_summary": previous_diagnostic / "summary.json"}
    model_paths = {"A": model_a, "English": model_english}
    manifest = {"status": "running", "mechanical_status": "running", "data_role": "development",
                "input_paths": {k: str(p.resolve()) for k, p in files.items()},
                "model_paths": {k: str(p.resolve()) for k, p in model_paths.items()},
                "feature_versions": MODEL_VERSIONS, "feature_names": FEATURE_NAMES,
                "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                "versions": {"python": platform.python_version(), "numpy": np.__version__, "lightgbm": lightgbm.__version__},
                "prediction_num_threads": 1, "tree_atol": TREE_ATOL, "tree_rtol": 0,
                "strict_preference": "exact raw score comparison", "human_review_status": "pending",
                "semantic_attribution": "unknown_pending_human_review",
                "boundary": {"fits": 0, "remote_calls": 0, "train_queries_read": 0,
                             "confirmation_queries_read": 0, "test_queries_read": 0}}
    _write_json(out / "manifest.json", manifest)
    try:
        for name, folder in model_paths.items():
            for file in ("model.txt", "manifest.json", "feature_contract.json", "test_vectors.json", "short_fallback.json"):
                files[f"{name}/{file}"] = folder / file
        missing = [str(p) for p in files.values() if not p.is_file()]
        if missing:
            raise FileNotFoundError(f"missing required local input: {missing}")
        before = {k: (p.stat().st_size, p.stat().st_mtime_ns) for k, p in files.items()}
        manifest["bundle_validation"] = {k: validate_production_bundle(p) for k, p in model_paths.items()}
        rankers = {k: LambdaMartOnlineRanker(p, feature_version=MODEL_VERSIONS[k], prediction_num_threads=1)
                   for k, p in model_paths.items()}
        selection, old_manifest = _read_json(files["english_selection"]), _read_json(files["previous_manifest"])
        if (selection["status"] != "complete" or selection["feature_version"] != ENGLISH_FEATURE_VERSION
                or Path(selection["model_path"]).resolve() != model_english.resolve()
                or selection["model_version"] != rankers["English"].manifest.model_version):
            raise ValueError("English saved predictions are not bound to this model")
        if (old_manifest["feature_version"] != FEATURE_VERSION
                or old_manifest["bundle_validation"]["A"]["model_version"] != rankers["A"].manifest.model_version):
            raise ValueError("previous diagnostic is not the original A/legacy reference")
        for kind in ("queries", "supervision", "inputs"):
            if Path(selection["input_paths"][f"development_{kind}"]).resolve() != files[kind].resolve():
                raise ValueError(f"English selection used a different development {kind}")
        loaded = {k: _read_rows(files[k]) for k in ("queries", "supervision", "inputs", "passage_mapping")}
        prepared = prepare_inputs(**loaded, role="development")
        saved, old_predictions = _unique(_read_rows(saved_english_predictions)), _unique(_read_rows(files["previous_predictions"]))
        query_ids = {r["source_query_id"] for r in prepared}
        if set(saved) != query_ids or set(old_predictions) != query_ids or not all(r["rank_input_complete"] for r in prepared):
            raise ValueError("incomplete or changed development population")
        cases, predictions, trees, replays = [], [], [], []
        matrices = {name: {} for name in MODEL_VERSIONS}
        with ExitStack() as stack:
            prior_features = stack.enter_context(np.load(files["previous_features"], allow_pickle=False))
            english_features = stack.enter_context(np.load(files["english_features"], allow_pickle=False))
            prior_traces = stack.enter_context(files["previous_traces"].open(encoding="utf-8"))
            streams = {}
            for name in MODEL_VERSIONS:
                (out / name).mkdir()
                streams[name] = stack.enter_context((out / name / "feature-traces.jsonl").open("x", encoding="utf-8"))
            for row in prepared:
                qid = row["source_query_id"]
                case = {k: row[k] for k in ("source_query_id", "source_group_id", "pair_id", "direction", "coverage_state", "target_presence", "candidate_count")}
                case.update(models={}, feature_collisions_by_model={}, route_preferences={},
                            human_review_status="pending", human_label=None, semantic_attribution="unknown_pending_human_review")
                scores_by_model, audits, pool = {}, {}, None
                prior_trace = json.loads(next(prior_traces))
                if prior_trace.pop("source_query_id") != qid:
                    raise ValueError("previous trace query order differs")
                prior_trace.pop("raw_input_reference")
                for name, ranker in rankers.items():
                    version = MODEL_VERSIONS[name]
                    ids, x = build_online_features(**row["method_row"], candidate_contents=row["contents"], feature_version=version)
                    frozen = prior_features[qid] if name == "A" else english_features[qid]
                    if frozen.dtype != x.dtype or not np.array_equal(x, frozen):
                        raise ValueError(f"saved {name} feature matrix mismatch: {qid}")
                    score = ranker.predict_features(x, feature_version=version)
                    if name == "English":
                        _check_saved_prediction(row, saved[qid], ids, score)
                    elif ids != old_predictions[qid]["chunk_ids"] or not np.array_equal(score, old_predictions[qid]["scores"]["A"]):
                        raise ValueError(f"original A prediction mismatch: {qid}")
                    trace = trace_features(**row["method_row"], candidate_contents=row["contents"],
                                           target_chunk_ids=[row["preferred_chunk_id"], row["other_chunk_id"]],
                                           reference_ids=ids, reference_features=x, feature_version=version)
                    if not trace["verification"]["passed"] or (name == "A" and trace != prior_trace):
                        raise ValueError(f"feature trace or original A trace mismatch: {qid}/{name}")
                    after_ids, after_x = build_online_features(**row["method_row"], candidate_contents=row["contents"], feature_version=version)
                    if after_ids != ids or not np.array_equal(x, after_x) or not np.array_equal(score, ranker.predict_features(after_x, feature_version=version)):
                        raise ValueError("tracing changed model inputs or scores")
                    trace.update(source_query_id=qid, model=name, input_reference=str(files["inputs"].resolve()))
                    streams[name].write(json.dumps(trace, ensure_ascii=False, allow_nan=False) + "\n")
                    matrices[name][qid], scores_by_model[name], pool = x, score.tolist(), trace["pool_summary"]
                    p, o = row["preferred_chunk_id"], row["other_chunk_id"]
                    if p in ids and o in ids:
                        a, b = ids.index(p), ids.index(o)
                        audit = audit_pair(booster=ranker.model, preferred_features=x[a], other_features=x[b], feature_names=FEATURE_NAMES,
                                           preferred_score=float(score[a]), other_score=float(score[b]), label_basis="official")
                        if not audit["verification"]["passed"]:
                            raise ValueError("tree path reconstruction failed")
                        audits[name] = audit
                        case["feature_collisions_by_model"][name] = audit["full_features_exactly_equal"]
                        case["models"][name] = {"relation": _relation(score[a], score[b]), "preferred_score": float(score[a]),
                                                "other_score": float(score[b]), "raw_delta": float(score[a]-score[b]),
                                                "different_leaf_count": audit["different_leaf_count"]}
                    else:
                        case["feature_collisions_by_model"][name] = None
                        case["models"][name] = {"relation": "not_evaluable", "reason": "missing_target"}
                for source, hits in row["method_row"]["routes"].items():
                    values = {hit["chunk_id"]: hit["score"] for hit in hits}
                    case["route_preferences"][source] = {"relation": _relation(values[p], values[o]) if p in values and o in values else "missing_target"}
                values = {h["chunk_id"]: h["score"] for h in pool["baseline_order"]}
                case["frozen_weighted_relation"] = _relation(values.get(p, 0), values.get(o, 0)) if row["coverage_state"] == "both" else "not_evaluable"
                case["full_features_exactly_equal"] = case["feature_collisions_by_model"]["English"]
                case["official_four_cell"] = _four_cell(case["models"]["A"]["relation"], case["models"]["English"]["relation"]).replace("only_b_correct", "only_english_correct")
                cases.append(case)
                predictions.append({"source_query_id": qid, "chunk_ids": ids, "feature_versions": MODEL_VERSIONS, "scores": scores_by_model})
                if audits:
                    trees.append({"source_query_id": qid, "models": audits})
                replays.append({"source_query_id": qid, "candidate_count": len(ids), "both_saved_feature_matrices_exact": True,
                                "both_saved_scores_exact": True, "legacy_trace_unchanged": True, "tracing_no_effect": True})
            if next(prior_traces, None) is not None:
                raise ValueError("previous trace contains additional queries")
        summary = _summarize_cases(cases, model_names=("A", "English"))
        summary["full_feature_collisions_primary_version"] = ENGLISH_FEATURE_VERSION
        summary["feature_column_statistics"] = {name: _column_statistics(values) for name, values in matrices.items()}
        summary["full_feature_collisions_by_model"] = {name: sum(c["feature_collisions_by_model"][name] is True for c in cases) for name in MODEL_VERSIONS}
        summary["model_split_counts"] = {name: dict(zip(FEATURE_NAMES, map(int, ranker.model.feature_importance(importance_type="split")), strict=True)) for name, ranker in rankers.items()}
        old = _read_json(files["previous_summary"])
        for key in ("scheduled_queries", "scheduled_pairs", "source_groups", "covered_queries", "covered_pairs", "route_preferences", "frozen_weighted_relations"):
            if summary[key] != old[key]:
                raise ValueError(f"previous diagnostic population/route summary differs: {key}")
        expected = selection["grid"][0]["dev_metrics"]
        actual = summary["models"]["English"]
        if any(actual["strict_relations"].get(k, 0) != expected[k] for k in ("correct", "wrong", "tie")) or actual["paired_correct"] != expected["pair_correct"]:
            raise ValueError("English summary differs from frozen selection")
        replay = {"status": "passed", "queries": replays, "candidate_rows": sum(r["candidate_count"] for r in replays),
                  "tree_pair_records": sum(a["tree_count"] for t in trees for a in t["models"].values()),
                  "tree_max_abs_delta_error": max(a["verification"]["max_abs_delta_error"] for t in trees for a in t["models"].values()),
                  "tree_max_abs_score_error": max(a["verification"]["max_abs_score_error"] for t in trees for a in t["models"].values()),
                  "tree_atol": TREE_ATOL, "tree_rtol": 0}
        for name, values in matrices.items():
            np.savez_compressed(out / name / f"model-inputs-{MODEL_VERSIONS[name]}.npz", **values)
        for filename, values in (("cases.jsonl", cases), ("raw-predictions.jsonl", predictions), ("tree-audit.jsonl", trees)):
            _write_rows(out / filename, values)
        _write_json(out / "summary.json", summary)
        _write_json(out / "replay-check.json", replay)
        bodies = _review_bodies(prepared, loaded["passage_mapping"], experiment_dir / "prepared/corpus.jsonl")
        review = make_review_packets(prepared, bodies, out / "review")
        review.pop("case_maps")
        review["public_cases_identical_to_previous"] = all((out / "review" / name / "cases.jsonl").read_bytes() == (previous_diagnostic / "review" / name / "cases.jsonl").read_bytes() for name in ("reviewer_1", "reviewer_2"))
        manifest.update(status="partially_completed", mechanical_status="completed", review=review,
                        summary=summary, input_file_metadata_unchanged=all(before[k] == (p.stat().st_size, p.stat().st_mtime_ns) for k, p in files.items()),
                        decision="no_model_change; semantic_error_attribution_pending")
        if not manifest["input_file_metadata_unchanged"]:
            raise ValueError("input/model file changed during diagnostic replay")
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, StopIteration) as exc:
        manifest.update(status="blocked", mechanical_status="blocked", blocker={"type": type(exc).__name__, "detail": str(exc)})
        raise
    finally:
        manifest["elapsed_seconds"] = time.perf_counter() - started
        _write_json(out / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("experiment-dir", "model-a", "model-english", "saved-english-predictions", "previous-diagnostic", "out"):
        parser.add_argument(f"--{arg}", type=Path, required=True)
    result = run(**vars(parser.parse_args()))
    print(json.dumps({k: result[k] for k in ("status", "mechanical_status", "human_review_status", "elapsed_seconds")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
