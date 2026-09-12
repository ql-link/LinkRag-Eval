"""Offline NevIR A/B evaluation on one complete, fixed three-route input.

Only within-pair preferences are judged. Background candidates remain unjudged.
This module never retrieves, encodes, trains, or reads an implicit data split.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import math
import os
import platform
import subprocess
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from linkrag_eval.retrieval.learning_to_rank.features import (
    BASELINE_THRESHOLDS,
    BASELINE_WEIGHTS,
    FEATURE_NAMES,
    FEATURE_VERSION,
    ROUTES,
    build_online_features,
)
from linkrag_eval.retrieval.learning_to_rank.online import (
    LambdaMartOnlineRanker,
    ModelManifest,
    _load_manifest,
    _load_short_fallback,
)

MODELS = ("A", "B")
RELATIONS = ("correct", "wrong", "tie", "unavailable")
BOOTSTRAP_SEED = 20260907
BOOTSTRAP_REPEATS = 10_000
FROZEN_A_VERSION = "candidate-difference-v3-20260728-final33"
# Existing artifact checksum identifies the one positional-schema exception.
FROZEN_A_MODEL_SHA256 = "1de4d9380ae16b26e210a67280335c5ed6976001fc23641c54241e13da82de41"


class EvaluationContractError(ValueError):
    """Invalid identities or incompatible model contracts, never a filtered sample."""


def _unique(rows: list[dict], field: str) -> dict[str, dict]:
    result = {}
    for row in rows:
        key = row.get(field)
        if not isinstance(key, str) or not key or key in result:
            raise EvaluationContractError(f"invalid or duplicate {field}")
        result[key] = row
    return result


def _identity_matches(row: dict, mapping: dict) -> bool:
    return all(row.get(key) == mapping[key] for key in ("dataset_id", "doc_id", "chunk_id"))


def prepare_inputs(
    queries: list[dict],
    supervision: list[dict],
    inputs: list[dict],
    passage_mapping: list[dict],
    *,
    role: str,
) -> list[dict]:
    """Join explicit supervision; preserve the scheduled query denominator.

    Mapping supplies identity only. Missing candidate text is never filled from
    a corpus, a partner query, or a supervised passage.
    """
    if role not in {"train", "development", "confirmation", "test"}:
        raise EvaluationContractError("unknown data role")
    query_by_id = _unique(queries, "source_query_id")
    labels = _unique(supervision, "source_query_id")
    candidate_inputs = _unique(inputs, "source_query_id")
    mapping = _unique(passage_mapping, "chunk_id")
    _unique(passage_mapping, "source_passage_id")
    if set(query_by_id) != set(labels) or not set(candidate_inputs) <= set(query_by_id):
        raise EvaluationContractError("query/supervision/input identity mismatch")
    for row in mapping.values():
        if not all(type(row.get(key)) is int for key in ("dataset_id", "doc_id")):
            raise EvaluationContractError("invalid passage identity")
    paired = defaultdict(dict)
    for qid, label in labels.items():
        if label.get("role") != role or label.get("direction") not in {"q1", "q2"}:
            raise EvaluationContractError("supervision role/direction mismatch")
        for key in ("source_group_id", "pair_id"):
            if not isinstance(label.get(key), str) or not label[key]:
                raise EvaluationContractError(f"missing {key}")
        for key in ("official_label_available", "structural_conflict", "semantic_uncertain"):
            if type(label.get(key)) is not bool:
                raise EvaluationContractError(f"invalid {key}")
        if not isinstance(label.get("issue_reasons"), list):
            raise EvaluationContractError("missing issue_reasons")
        targets = [label.get(f"{side}_chunk_id") for side in ("preferred", "other")]
        if targets[0] == targets[1] or any(cid not in mapping for cid in targets):
            raise EvaluationContractError("invalid supervised target identity")
        for side, cid in zip(("preferred", "other"), targets, strict=True):
            if label.get(f"{side}_passage_id") != mapping[cid]["source_passage_id"]:
                raise EvaluationContractError("supervised passage/chunk mismatch")
        pair = paired[label["pair_id"]]
        if label["direction"] in pair:
            raise EvaluationContractError("duplicate pair direction")
        pair[label["direction"]] = label
    for pair in paired.values():
        if set(pair) != {"q1", "q2"}:
            raise EvaluationContractError("pair must contain exactly q1 and q2")
        first, second = pair["q1"], pair["q2"]
        if (first["source_group_id"] != second["source_group_id"]
                or first["preferred_chunk_id"] != second["other_chunk_id"]
                or first["other_chunk_id"] != second["preferred_chunk_id"]):
            raise EvaluationContractError("pair group or reciprocal target mismatch")
    prepared = []
    for qid, query_row in query_by_id.items():
        query = query_row.get("query")
        if not isinstance(query, str) or not query.strip():
            raise EvaluationContractError("invalid scheduled query text")
        label = labels[qid]
        row = candidate_inputs.get(qid)
        if row is not None and row.get("query") != query:
            raise EvaluationContractError("saved query text mismatch")
        item = {
            **copy.deepcopy(label), "query": query,
            "input_status": row.get("status", "invalid") if row else "not_executed",
            "coverage_state": "unknown", "coverage_reason": "not_executed",
            "target_presence": "unknown", "both_targets_observed_in_partial": False,
            "route_status": copy.deepcopy(row.get("route_status", {})) if row else {},
            "route_observation": {}, "rank_input_complete": False,
            "input_issues": [], "candidate_count": None, "method_row": None, "contents": {},
        }
        prepared.append(item)
        if row is None:
            continue
        route_ids, method_routes = set(), {}
        try:
            if set(row["routes"]) != set(ROUTES):
                raise ValueError("route set")
            for source in ROUTES:
                method_routes[source] = []
                seen = set()
                for rank, hit in enumerate(row["routes"][source]):
                    cid = hit["chunk_id"]
                    if (cid in seen or cid not in mapping
                            or not _identity_matches(hit, mapping[cid])
                            or type(hit["rank"]) is not int or hit["rank"] != rank
                            or not math.isfinite(float(hit["score"]))):
                        raise ValueError("route identity/rank/score")
                    seen.add(cid)
                    route_ids.add(cid)
                    method_routes[source].append({
                        key: hit[key]
                        for key in ("dataset_id", "chunk_id", "doc_id", "score", "rank")
                    })
                targets = {label["preferred_chunk_id"], label["other_chunk_id"]}
                status = row.get("route_status", {}).get(source, "unavailable")
                if status == "empty" and seen:
                    raise ValueError("empty route contains hits")
                item["route_observation"][source] = {
                    "status": status, "returned": len(seen),
                    "both_observed": targets <= seen,
                    "both_on_success": status in {"ok", "empty"} and targets <= seen,
                }
        except (KeyError, TypeError, ValueError, OverflowError):
            item.update(coverage_reason="invalid_route_evidence", input_issues=["invalid_routes"])
            continue
        complete = (not row.get("failed_sources")
                    and all(item["route_status"].get(s) in {"ok", "empty"} for s in ROUTES))
        preferred = label["preferred_chunk_id"] in route_ids
        other = label["other_chunk_id"] in route_ids
        presence = "both" if preferred and other else (
            "preferred_only" if preferred else "other_only" if other else "neither")
        item.update(
            candidate_count=len(route_ids), target_presence=presence,
            coverage_state=("both" if presence == "both" else "missing_target") if complete else "unknown",
            coverage_reason="complete_routes" if complete else "incomplete_routes",
            both_targets_observed_in_partial=not complete and preferred and other,
        )
        issues, candidates = [], {}
        try:
            for candidate in row["candidate_rows"]:
                cid = candidate["chunk_id"]
                if cid in candidates or cid not in mapping:
                    raise ValueError("duplicate/unknown candidate")
                candidates[cid] = candidate
                if not _identity_matches(candidate, mapping[cid]):
                    issues.append("candidate_identity_mismatch")
                if candidate.get("source_passage_id") != mapping[cid]["source_passage_id"]:
                    issues.append("candidate_source_mapping_mismatch")
                if not isinstance(candidate.get("content"), str) or not candidate["content"].strip():
                    issues.append("candidate_content_missing")
        except (KeyError, TypeError, ValueError):
            issues.append("invalid_candidate_rows")
        if set(candidates) != route_ids:
            issues.append("candidate_pool_incomplete")
        if not row.get("ranking_input_ready"):
            issues.append("ranking_input_not_ready")
        item["input_issues"] = sorted(set(issues))
        item["rank_input_complete"] = complete and not issues
        if item["rank_input_complete"]:
            item["method_row"] = {"query": query, "routes": method_routes}
            item["contents"] = {cid: candidate["content"] for cid, candidate in candidates.items()}
    return prepared


def _unavailable(status: str, error_type: str | None = None) -> dict:
    return {"status": status, "relation": "unavailable", "error_type": error_type}


async def _score_query(item: dict, ranker: Any) -> dict:
    raw, online = _unavailable("input_unavailable"), _unavailable("input_unavailable")
    result = {"raw": raw, "online": online}
    if not item["rank_input_complete"]:
        return result
    if item["candidate_count"] == 0:
        return {"raw": _unavailable("empty"), "online": _unavailable("empty")}
    method_row, contents = item["method_row"], item["contents"]
    judgeable = item["coverage_state"] == "both" and item["official_label_available"]
    preferred, other = item["preferred_chunk_id"], item["other_chunk_id"]
    try:
        outcome = await ranker.rank(copy.deepcopy(method_row), copy.deepcopy(contents))
        order = list(outcome.ranked_chunk_ids)
        if len(order) != len(contents) or set(order) != set(contents):
            raise ValueError("online output is not a complete candidate permutation")
        elapsed = float(outcome.elapsed_ms)
        if not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("invalid online elapsed_ms")
        online.update(status="ranked", order=order, mode=outcome.mode,
                      reason=outcome.reason, elapsed_ms=elapsed,
                      model_version=outcome.model_version)
        if judgeable:
            online["relation"] = "correct" if order.index(preferred) < order.index(other) else "wrong"
    except Exception as exc:  # noqa: BLE001 — Per-query errors never remove the denominator.
        online.update(_unavailable("online_error", type(exc).__name__))
    try:
        ids, features = build_online_features(**method_row, candidate_contents=contents)
        scores = np.asarray(ranker.model.predict(features.copy(), num_threads=1), dtype=np.float64)
        if (scores.shape != (len(ids),) or not np.isfinite(scores).all()
                or not np.isfinite(features).all()):
            raise ValueError("non-finite or invalid complete model output")
        replay_ids, replay_features = build_online_features(**method_row, candidate_contents=contents)
        replay_scores = np.asarray(
            ranker.model.predict(replay_features.copy(), num_threads=1), dtype=np.float64)
        replay_equal = (ids == replay_ids and np.array_equal(features, replay_features)
                        and np.array_equal(scores, replay_scores))
        raw.update(
            status="scored" if replay_equal else "replay_mismatch", replay_equal=replay_equal,
            scores=[{"chunk_id": cid, "score": float(score)}
                    for cid, score in zip(ids, scores, strict=True)],
            order=[cid for cid, score in sorted(zip(ids, scores, strict=True),
                                                key=lambda pair: (-float(pair[1]), pair[0]))],
        )
        if judgeable and replay_equal:
            by_id = dict(zip(ids, scores, strict=True))
            # Compare the finite operands directly; subtraction can overflow.
            left, right = float(by_id[preferred]), float(by_id[other])
            difference = left - right
            raw["score_difference"] = difference if math.isfinite(difference) else None
            raw["relation"] = "correct" if left > right else "wrong" if left < right else "tie"
    except Exception as exc:  # noqa: BLE001
        raw.update(_unavailable("model_error", type(exc).__name__))
    online["raw_relation"] = raw["relation"]
    online["raw_unavailable"] = raw["relation"] == "unavailable"
    online["raw_diagnostic_failed"] = raw["status"] in {"model_error", "replay_mismatch"}
    return result


async def _warmup(ranker: Any) -> str | None:
    """One fixed, unlabelled, synthetic call; never a held-out query."""
    row = {"query": "Synthetic warmup for fixed candidate ranking", "routes": {
        source: [{"dataset_id": 999999, "doc_id": 1, "chunk_id": "warmup",
                  "score": 0.9, "rank": 0}] for source in ROUTES}}
    try:
        await ranker.rank(row, {"warmup": "Synthetic warmup text."})
        return None
    except Exception as exc:  # noqa: BLE001
        return type(exc).__name__


async def evaluate_ab(
    prepared: list[dict], rankers: dict[str, Any], *,
    load_errors: dict[str, str] | None = None, warmup: bool = True,
) -> list[dict]:
    """Evaluate both models on the same input; alternate A/B execution order."""
    if set(rankers) != set(MODELS):
        raise EvaluationContractError("exactly A and B rankers required")
    load_errors = load_errors or {}
    warmup_errors = {}
    if warmup:
        for name in MODELS:
            if rankers[name] is not None:
                warmup_errors[name] = await _warmup(rankers[name])
    results = []
    for index, item in enumerate(prepared):
        row = {key: copy.deepcopy(value) for key, value in item.items()
               if key not in {"method_row", "contents"}}
        row["models"] = {}
        row["execution_order"] = list(MODELS if index % 2 == 0 else reversed(MODELS))
        row["warmup_errors"] = warmup_errors
        for name in row["execution_order"]:
            if rankers[name] is None:
                row["models"][name] = {kind: _unavailable(
                    "model_load_failed", load_errors.get(name, "model_unavailable"))
                    for kind in ("raw", "online")}
            else:
                row["models"][name] = await _score_query(item, rankers[name])
        results.append(row)
    return results


def _relation_bounds(relation: str) -> list[int]:
    if relation not in RELATIONS:
        raise EvaluationContractError("unknown relation")
    return [1, 1] if relation == "correct" else [0, 1] if relation == "unavailable" else [0, 0]


def _pair_rows(results: list[dict]) -> list[dict]:
    by_pair = defaultdict(dict)
    for row in results:
        pair = by_pair[row["pair_id"]]
        if row["direction"] in pair:
            raise EvaluationContractError("duplicate evaluated pair direction")
        pair[row["direction"]] = row
    paired = []
    for pid, directions in by_pair.items():
        if set(directions) != {"q1", "q2"}:
            raise EvaluationContractError("incomplete evaluated pair")
        first, second = directions["q1"], directions["q2"]
        if first["source_group_id"] != second["source_group_id"]:
            raise EvaluationContractError("evaluated source groups disagree")
        coverage = [first["coverage_state"], second["coverage_state"]]
        row = {
            "pair_id": pid, "source_group_id": first["source_group_id"],
            "q1_id": first["source_query_id"], "q2_id": second["source_query_id"],
            "coverage_directions": coverage,
            "coverage_state": "both" if coverage == ["both", "both"] else (
                "missing_target" if "missing_target" in coverage else "unknown"),
            "sensitivity_eligible": all(not q["semantic_uncertain"] and not q["structural_conflict"]
                                        for q in (first, second)),
            "models": {},
        }
        for name in MODELS:
            row["models"][name] = {}
            for kind in ("raw", "online"):
                relations = [q["models"][name][kind]["relation"] for q in (first, second)]
                bounds = [_relation_bounds(relation) for relation in relations]
                row["models"][name][kind] = {
                    "directions": relations,
                    "status": "unavailable" if "unavailable" in relations else (
                        "correct" if relations == ["correct", "correct"] else (
                            "tie" if "tie" in relations and "wrong" not in relations else "wrong")),
                    "bounds": [bounds[0][0] * bounds[1][0], bounds[0][1] * bounds[1][1]],
                    "contains_unavailable": "unavailable" in relations,
                    "contains_tie": "tie" in relations, "contains_wrong": "wrong" in relations,
                }
        paired.append(row)
    return paired


def _rate(numerator: int, denominator: int) -> dict:
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def _coverage(rows: list[dict]) -> dict:
    counts = {key: sum(row["coverage_state"] == key for row in rows)
              for key in ("both", "missing_target", "unknown")}
    n = len(rows)
    return {"denominator": n, "counts": counts,
            "proportions": {key: _rate(value, n) for key, value in counts.items()},
            "complete_execution_coverage": counts["both"] / n if n and not counts["unknown"] else None,
            "bounds": [counts["both"] / n, (counts["both"] + counts["unknown"]) / n] if n else None}


def _bootstrap_delta(
    groups: list[str], differences: list[float], *, seed: int, repeats: int,
) -> dict:
    """Resample whole source groups, retaining the micro-average estimand."""
    if repeats <= 0:
        raise ValueError("bootstrap repeats must be positive")
    grouped = defaultdict(list)
    for group, difference in zip(groups, differences, strict=True):
        grouped[group].append(difference)
    keys = sorted(grouped)
    sizes = np.asarray([len(grouped[key]) for key in keys], dtype=np.int64)
    details = {
        "groups": len(keys), "group_sizes": {key: len(grouped[key]) for key in keys},
        "max_group_fraction": int(sizes.max()) / int(sizes.sum()) if len(sizes) else None,
        "seed": seed, "repeats": repeats, "confidence": 0.95,
        "method": "source_group_percentile_bootstrap_micro_average",
        "quantile_method": "linear", "interval": None,
    }
    if len(keys) < 2:
        return {**details, "interval_reason": "fewer_than_two_source_groups"}
    sums = np.asarray([sum(grouped[key]) for key in keys], dtype=np.float64)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(keys), size=(repeats, len(keys)))
    estimates = sums[draws].sum(axis=1) / sizes[draws].sum(axis=1)
    interval = np.quantile(estimates, [0.025, 0.975], method="linear").tolist()
    return {**details, "interval": interval, "interval_reason": None,
            "degenerate": bool(np.all(estimates == estimates[0])),
            "scope": "fixed selected set; source-group resampling stability, not population coverage"}


def _measure(rows: list[dict], kind: str, *, paired: bool, seed: int, repeats: int) -> dict:
    n = len(rows)
    values = {name: [r["models"][name][kind]["bounds"] if paired else
                     _relation_bounds(r["models"][name][kind]["relation"]) for r in rows]
              for name in MODELS}
    result = {"denominator": n}
    for name in MODELS:
        low, high = sum(v[0] for v in values[name]), sum(v[1] for v in values[name])
        unknown = sum(v[0] != v[1] for v in values[name])
        result[name] = {**_rate(low, n), "unknown": unknown,
                        "bounds": [low / n, high / n] if n else None}
        if unknown:
            result[name]["value"] = None
    lower = sum(b[0] - a[1] for a, b in zip(values["A"], values["B"], strict=True))
    upper = sum(b[1] - a[0] for a, b in zip(values["A"], values["B"], strict=True))
    unknown = any(v[0] != v[1] for name in MODELS for v in values[name])
    delta = {"value": lower / n if n and not unknown else None,
             "bounds": [lower / n, upper / n] if n else None,
             "interval": None, "interval_reason": "unknown_outcomes" if unknown else "empty_denominator"}
    groups = [r["source_group_id"] for r in rows]
    if n and not unknown:
        delta.update(_bootstrap_delta(groups, [b[0] - a[0] for a, b in
                     zip(values["A"], values["B"], strict=True)], seed=seed, repeats=repeats))
    else:
        group_sizes = dict(Counter(groups))
        delta.update(groups=len(group_sizes), group_sizes=group_sizes, seed=seed, repeats=repeats)
    result["delta"] = delta
    transitions = dict.fromkeys(
        ("corrected", "regressed", "both_correct", "both_not_correct", "unavailable"), 0)
    states = ("correct", "not_correct", "unavailable") if paired else RELATIONS
    matrix = {a: dict.fromkeys(states, 0) for a in states}
    for index, row in enumerate(rows):
        a, b = values["A"][index], values["B"][index]
        if paired:
            pair_states = ["unavailable" if bound[0] != bound[1] else
                           "correct" if bound[0] else "not_correct" for bound in (a, b)]
        else:
            pair_states = [row["models"][name][kind]["relation"] for name in MODELS]
        matrix[pair_states[0]][pair_states[1]] += 1
        if a[0] != a[1] or b[0] != b[1]:
            transitions["unavailable"] += 1
        else:
            cell = {(0, 1): "corrected", (1, 0): "regressed", (1, 1): "both_correct",
                    (0, 0): "both_not_correct"}[(a[0], b[0])]
            transitions[cell] += 1
    transitions["rates"] = {key: _rate(value, n) for key, value in transitions.items()}
    transitions["matrix"] = matrix
    if not paired:
        transitions.update(reverse_corrected=matrix["wrong"]["correct"],
                           reverse_regressed=matrix["correct"]["wrong"],
                           tie_corrected=matrix["tie"]["correct"],
                           regressed_to_tie=matrix["correct"]["tie"])
    result["transitions"] = transitions
    return result


def _summarize_subset(rows: list[dict], pairs: list[dict], *, seed: int, repeats: int) -> dict:
    common = [r for r in rows if r["coverage_state"] == "both"]
    jointly = [r for r in pairs if r["coverage_state"] == "both"]
    result = {"query_count": len(rows), "pair_count": len(pairs),
              "coverage": {"query": _coverage(rows), "pair": _coverage(pairs)},
              "input_status_counts": dict(Counter(r["input_status"] for r in rows)),
              "label_unavailable_count": sum(not r["official_label_available"] for r in rows),
              "semantic_uncertain_count": sum(r["semantic_uncertain"] for r in rows),
              "semantic_review_status_counts": dict(Counter(
                  r.get("semantic_review_status", "unspecified") for r in rows)),
              "structural_conflict_count": sum(r["structural_conflict"] for r in rows),
              "route_observations": {}}
    for source in ROUTES:
        observations = [r.get("route_observation", {}).get(source, {}) for r in rows]
        result["route_observations"][source] = {
            "denominator": len(rows),
            "status_counts": dict(Counter(r.get("status", "unavailable") for r in observations)),
            "successful_empty": sum(r.get("status") in {"ok", "empty"} and r.get("returned") == 0
                                    for r in observations),
            "both_on_success": sum(bool(r.get("both_on_success")) for r in observations),
        }
    for kind in ("raw", "online"):
        result[kind] = {
            "single_query": _measure(common, kind, paired=False, seed=seed, repeats=repeats),
            "paired": _measure(jointly, kind, paired=True, seed=seed, repeats=repeats),
            "status_counts": {name: dict(Counter(r["models"][name][kind]["status"] for r in rows))
                              for name in MODELS},
            "paired_flags": {name: {flag: sum(p["models"][name][kind][flag] for p in jointly)
                                    for flag in ("contains_unavailable", "contains_tie", "contains_wrong")}
                             for name in MODELS},
        }
    result["online"]["mode_counts"] = {name: dict(Counter(
        r["models"][name]["online"].get("mode", "unavailable") for r in rows)) for name in MODELS}
    result["online"]["mode_transitions"] = dict(Counter(
        f"{r['models']['A']['online'].get('mode', 'unavailable')} -> "
        f"{r['models']['B']['online'].get('mode', 'unavailable')}" for r in rows))
    result["online"]["order_when_raw_tied"] = {name: dict(Counter(
        r["models"][name]["online"]["relation"] for r in common
        if r["models"][name]["raw"]["relation"] == "tie")) for name in MODELS}
    return result


def summarize(
    query_results: list[dict], *, bootstrap_repeats: int = BOOTSTRAP_REPEATS,
    bootstrap_seed: int = BOOTSTRAP_SEED,
) -> tuple[dict, list[dict]]:
    """Official results plus the common, predeclared uncertainty mask."""
    _unique(query_results, "source_query_id")
    pairs = _pair_rows(query_results)
    official = _summarize_subset(query_results, pairs, seed=bootstrap_seed, repeats=bootstrap_repeats)
    kept = [r for r in query_results if not r["semantic_uncertain"] and not r["structural_conflict"]]
    eligible_pairs = [p for p in pairs if p["sensitivity_eligible"]]
    sensitivity = {"applied": len(kept) != len(query_results),
                   "excluded_query_count": len(query_results) - len(kept),
                   "excluded_pair_count": len(pairs) - len(eligible_pairs),
                   "mask": "predeclared semantic_uncertain or structural_conflict; official labels unchanged",
                   "semantic_issue_scope_counts": dict(Counter(
                       r.get("semantic_issue_scope", "unspecified") for r in query_results
                       if r["semantic_uncertain"])),
                   "scope_note": "existing_pair_level_note is a conservative pair-level mask, "
                                 "not a judgment that both query directions are ambiguous"}
    if sensitivity["applied"]:
        sensitivity["results"] = _summarize_subset(
            kept, eligible_pairs, seed=bootstrap_seed, repeats=bootstrap_repeats)
    return {"official": official, "sensitivity": sensitivity,
            "interpretation": {
                "primary": "B-A micro-averaged strict preference on common real recall",
                "ties": "exact finite score equality; tie is not strict correctness",
                "transitions": "wrong includes ties in main four cells; full relation matrix separates them",
                "bounds": "logical missing-outcome bounds, not confidence intervals",
                "online": "actual local loaded-model policy order; raw scores are separate calls",
                "scope": "fixed confirmation set and candidate snapshot; no nDCG, overall Top1 or natural error rate",
                "uncertainty": "source-group resampling stability conditional on selected model and common coverage",
            }}, pairs


def load_rankers(model_a: Path, model_b: Path) -> tuple[dict, dict, dict]:
    """Validate both feature/policy contracts before either Booster is loaded."""
    paths, contracts, errors = {"A": model_a, "B": model_b}, {}, {}
    for name, path in paths.items():
        try:
            declared = ModelManifest(**json.loads((path / "manifest.json").read_text(encoding="utf-8")))
            try:
                declared.validate()
            except ValueError as exc:
                raise EvaluationContractError("package manifest feature/runtime contract mismatch") from exc
            manifest = _load_manifest(path)
            if name == "A" and (manifest.model_version != FROZEN_A_VERSION
                                or manifest.model_file_sha256 != FROZEN_A_MODEL_SHA256):
                raise EvaluationContractError("A is not the fixed final33 model")
            short = _load_short_fallback(path, manifest)
            feature = json.loads((path / "feature_contract.json").read_text(encoding="utf-8"))
            expected = {"feature_version": FEATURE_VERSION, "feature_names": FEATURE_NAMES,
                        "feature_signature": manifest.feature_signature, "alias_enabled": False}
            if any(feature.get(k) != value for k, value in expected.items()):
                raise EvaluationContractError("package feature contract mismatch")
            if feature.get("fallback") != {"type": "weighted-score-baseline",
                    "weights": BASELINE_WEIGHTS, "thresholds": BASELINE_THRESHOLDS}:
                raise EvaluationContractError("package baseline semantics mismatch")
            contracts[name] = {"path": str(path.resolve()), "manifest": asdict(manifest),
                               "short_fallback": asdict(short) if short else None}
        except EvaluationContractError:
            raise
        except Exception as exc:  # noqa: BLE001 — Save load failure without exposing exception contents.
            errors[name] = type(exc).__name__
    if len(contracts) == 2:
        for key in ("feature_version", "feature_signature", "feature_names", "latency_budget_ms",
                    "timeout_ms", "fallback_policy", "alias_enabled"):
            if contracts["A"]["manifest"][key] != contracts["B"]["manifest"][key]:
                raise EvaluationContractError(f"A/B {key} differs")
        if contracts["A"]["short_fallback"] != contracts["B"]["short_fallback"]:
            raise EvaluationContractError("A/B short fallback differs")
    rankers = {}
    for name, path in paths.items():
        rankers[name] = None
        if name not in errors:
            try:
                ranker = LambdaMartOnlineRanker(path, prediction_num_threads=1)
                names = ranker.model.feature_name()
                # The fixed final33 artifact predates named feature export. Its
                # positional schema is an explicit baseline exception, not a
                # compatibility rule for newly trained models.
                legacy = (name == "A" and ranker.manifest.model_version == FROZEN_A_VERSION
                          and ranker.manifest.model_file_sha256 == FROZEN_A_MODEL_SHA256
                          and names == [f"Column_{i}" for i in range(len(FEATURE_NAMES))])
                if ranker.model.num_feature() != len(FEATURE_NAMES) or (names != FEATURE_NAMES and not legacy):
                    raise EvaluationContractError("Booster feature count/order mismatch")
                policy = asdict(ranker.short_fallback) if ranker.short_fallback else None
                if (asdict(ranker.manifest) != contracts[name]["manifest"]
                        or policy != contracts[name]["short_fallback"]):
                    raise EvaluationContractError("package changed during loading")
                serialized_threads = ranker.model.params.get("num_threads")
                contracts[name].update(booster_feature_names=names,
                                       serialized_num_threads=serialized_threads,
                                       explicit_prediction_num_threads=1)
                rankers[name] = ranker
            except EvaluationContractError:
                raise
            except Exception as exc:  # noqa: BLE001
                errors[name] = type(exc).__name__
    return rankers, errors, contracts


def _read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def _report(summary: dict) -> str:
    official = summary["official"]
    lines = ["# NevIR 固定输入 A/B 独立评测", "",
             f"预定查询 {official['query_count']}；配对 {official['pair_count']}。",
             "官方指定偏好原样保留；背景未判断。四格中的未严格正确包括逆序与同分。", "",
             "| 结果 | 分母 | A | B | B−A | 95% 来源组重采样区间 | 纠正 / 改坏 |",
             "| --- | ---: | --- | --- | --- | --- | --- |"]
    for kind, endpoint, label in (("raw", "single_query", "原始分数严格单查询（主）"),
                                 ("raw", "paired", "原始分数双查询都严格正确"),
                                 ("online", "single_query", "在线实际单查询顺序"),
                                 ("online", "paired", "在线实际双查询顺序")):
        measure = official[kind][endpoint]
        render = lambda value: "不可估计" if value is None else f"{value:.4f}"
        lines.append(f"| {label} | {measure['denominator']} | {render(measure['A']['value'])} | "
                     f"{render(measure['B']['value'])} | {render(measure['delta']['value'])} | "
                     f"{measure['delta']['interval']} | {measure['transitions']['corrected']} / "
                     f"{measure['transitions']['regressed']} |")
    main = official["raw"]["single_query"]
    transition = main["transitions"]
    interval = main["delta"]["interval"]
    conclusion = "主差值不可估计。" if main["delta"]["value"] is None else (
        "主差值的收益方向尚未确定。" if interval is None or interval[0] <= 0 <= interval[1] else (
            "本集合的主差值区间位于零以上。" if interval[0] > 0 else "本集合的主差值区间位于零以下。"))
    lines.extend(["", conclusion,
                  (f"主四格：纠正 {transition['corrected']}，改坏 {transition['regressed']}，"
                  f"共同正确 {transition['both_correct']}，共同未严格正确 {transition['both_not_correct']}，"
                  f"转移不可判定 {transition['unavailable']}。"),
                  (f"其中逆序→正确 {transition['reverse_corrected']}，正确→逆序 {transition['reverse_regressed']}，"
                  f"同分→正确 {transition['tie_corrected']}，正确→同分 {transition['regressed_to_tie']}。"),
                  (f"主差值逻辑界限 {main['delta']['bounds']}；来源组数 {main['delta'].get('groups')}；"
                  f"区间不可用原因 {main['delta'].get('interval_reason')}。"), "",
                  "| 覆盖口径 | 已共同召回 | 已知未共同召回 | 未知 | 总数 |",
                  "| --- | ---: | ---: | ---: | ---: |"])
    for key, label in (("query", "单查询"), ("pair", "双查询配对")):
        coverage = official["coverage"][key]
        counts = coverage["counts"]
        lines.append(f"| {label} | {counts['both']} | {counts['missing_target']} | "
                     f"{counts['unknown']} | {coverage['denominator']} |")
    lines.extend(["", f"Raw 执行状态：{json.dumps(official['raw']['status_counts'], ensure_ascii=False)}。",
                  f"在线模式：{json.dumps(official['online']['mode_counts'], ensure_ascii=False)}。",
                  "完整迁移表、故障原因、同分和配对方向见 summary.json 与逐题 JSONL。",
                  "在线次序包含回退及同分破局，不是严格分数区分。区间仅描述本集合的来源组重采样稳定性，",
                  "不包含训练／选模随机性、标签疑点或远端召回变化，不外推自然业务或未来 Test。",
                  "部分配对标签不支持全池 nDCG、整体 Top1 或自然错误率。",
                  f"预标疑点敏感性掩码是否应用：{summary['sensitivity']['applied']}。官方主结果未被替换。",
                  "existing_pair_level_note 按预定配对范围保守排除，不表示两方向均已确认有歧义；未审读不等于已核实。"])
    if summary["sensitivity"]["applied"]:
        sensitive = summary["sensitivity"]["results"]
        delta = sensitive["raw"]["single_query"]["delta"]
        lines.append(f"敏感性子集：{sensitive['query_count']} 查询、{sensitive['pair_count']} 完整配对；"
                     f"严格单查询分母 {sensitive['raw']['single_query']['denominator']}，"
                     f"Δ={delta['value']}，区间={delta['interval']}。其余敏感性指标见 summary.json。")
    lines.append("")
    return "\n".join(lines)


def _code_metadata() -> dict:
    source_root = Path(__file__).resolve().parents[4]
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=source_root, text=True, stderr=subprocess.DEVNULL).strip()
        paths = subprocess.check_output(
            ["git", "status", "--short", "--", "src/linkrag_eval/retrieval/learning_to_rank"],
            cwd=source_root, text=True, stderr=subprocess.DEVNULL).splitlines()
        return {"code_revision": revision, "uncommitted_runtime_paths": paths}
    except (OSError, subprocess.CalledProcessError):
        return {"code_revision": None}


async def run_evaluation(*, experiment_dir: Path, role: str, model_a: Path,
                         model_b: Path, out: Path) -> dict:
    """Read exactly one explicit role and write a new evaluation directory."""
    out.mkdir(parents=True, exist_ok=False)
    prepared_dir = experiment_dir / "prepared"
    files = {
        "queries": prepared_dir / role / "queries.jsonl",
        "supervision": prepared_dir / role / "supervision.jsonl",
        "passage_mapping": prepared_dir / "passage-mapping.jsonl",
        "inputs": experiment_dir / "candidates" / role / "inputs.jsonl",
    }
    metadata = {"role": role, "input_paths": {k: str(v.resolve()) for k, v in files.items()},
                "run_metadata_path": str((experiment_dir / "run.json").resolve()),
                "feature_version": FEATURE_VERSION, "feature_names": FEATURE_NAMES,
                "baseline_weights": BASELINE_WEIGHTS, "baseline_thresholds": BASELINE_THRESHOLDS,
                "bootstrap_seed": BOOTSTRAP_SEED, "bootstrap_repeats": BOOTSTRAP_REPEATS,
                "python_version": platform.python_version(), "numpy_version": np.__version__,
                "thread_environment": {key: os.environ.get(key) for key in
                                       ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
                "execution": "one synthetic warmup per model; alternating A/B; online then separate raw replay"}
    metadata.update(await asyncio.to_thread(_code_metadata))
    try:
        loaded = {"queries": _read_rows(files["queries"])}
        metadata["scheduled_query_count"] = len(loaded["queries"])
        loaded.update({key: _read_rows(path) for key, path in files.items() if key != "queries"})
        prepared = prepare_inputs(**loaded, role=role)
        rankers, errors, contracts = load_rankers(model_a, model_b)
        metadata.update(model_contracts=contracts, model_load_errors=errors)
        if any(ranker is not None for ranker in rankers.values()):
            import lightgbm
            metadata["lightgbm_version"] = lightgbm.__version__
        results = await evaluate_ab(prepared, rankers, load_errors=errors)
        summary, pairs = summarize(results)
    except Exception as exc:
        metadata.update(status="evaluation_failed", error_type=type(exc).__name__)
        if isinstance(exc, EvaluationContractError):
            metadata["contract_error"] = str(exc)
        _write_json(out / "metadata.json", metadata)
        raise
    error_statuses = {"model_load_failed", "online_error", "model_error", "replay_mismatch"}
    metadata["status"] = "completed_with_unavailable" if any(
        r["coverage_state"] == "unknown" or not r["rank_input_complete"] or
        (r["coverage_state"] == "both" and any(
            r["models"][name][kind]["relation"] == "unavailable"
            for name in MODELS for kind in ("raw", "online"))) or
        any(r["models"][name][kind]["status"] in error_statuses
            for name in MODELS for kind in ("raw", "online")) for r in results) else "completed"
    for name, rows in (("queries.jsonl", results), ("pairs.jsonl", pairs)):
        with (out / name).open("x", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    _write_json(out / "metadata.json", metadata)
    _write_json(out / "summary.json", summary)
    (out / "report.md").write_text(_report(summary), encoding="utf-8")
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--role", choices=("train", "development", "confirmation"), required=True)
    parser.add_argument("--model-a", type=Path, required=True)
    parser.add_argument("--model-b", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        metadata = asyncio.run(run_evaluation(**vars(args)))
    except Exception as exc:  # noqa: BLE001 — Do not print credential-bearing exception messages.
        print(json.dumps({"status": "evaluation_failed", "error_type": type(exc).__name__}))
        return 1
    print(json.dumps({"status": metadata["status"], "out": str(args.out.resolve())}))
    return int(metadata["status"] != "completed")


if __name__ == "__main__":
    raise SystemExit(main())
