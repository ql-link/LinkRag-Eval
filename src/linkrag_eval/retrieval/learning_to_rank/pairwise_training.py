"""Fixed-budget NevIR adaptation of the unchanged 38-column LambdaMART features.

Only explicit train/development files are consumed. Unjudged candidates affect
the full-pool features; they enter the training loss only when background
negative sampling is explicitly enabled (default: disabled).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import multiprocessing
import random
import subprocess
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from linkrag_eval.retrieval.learning_to_rank.features import (
    FEATURE_NAMES,
    FEATURE_VERSION,
    FEATURE_VERSIONS,
    ROUTES,
    build_online_features,
    rules_version,
)

SEED = 20260907
MAX_ITERATIONS = 300
PATIENCE = 40
CANDIDATE_TIMEOUT_SECONDS = 600
TOTAL_TIMEOUT_SECONDS = 3600
PRIMARY_METRIC = "source_macro_query_accuracy"
GRID = tuple(
    {"config_id": f"c{index}", "num_leaves": leaves, "max_depth": depth, "reg_lambda": reg}
    for index, (leaves, depth, reg) in enumerate(
        ((3, 2, 1.0), (3, 2, 10.0), (7, 3, 1.0), (7, 3, 10.0), (15, 4, 1.0), (15, 4, 10.0)), 1
    )
)


@dataclass
class PreparedQuery:
    query_id: str
    query: str
    supervision: dict[str, Any]
    chunk_ids: list[str] = field(default_factory=list)
    features: np.ndarray | None = None
    selected_indices: list[int] = field(default_factory=list)
    loss_indices: list[int] = field(default_factory=list)
    exclusion_reasons: list[str] = field(default_factory=list)
    method_view: dict[str, Any] | None = None
    duplicate_of: str | None = None


@dataclass
class PairwiseDataset:
    role: str
    queries: list[PreparedQuery]
    blocks: list[PreparedQuery]
    x: np.ndarray
    y: np.ndarray
    groups: list[int]
    weights: np.ndarray
    summary: dict[str, Any]
    feature_version: str = FEATURE_VERSION


def _text(row: dict[str, Any], name: str) -> str:
    if not isinstance(row, dict):
        raise TypeError("record must be an object")
    value = row.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing or invalid {name}")
    return value


def _indexed(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for row in rows:
        qid = _text(row, "source_query_id")
        if qid in result:
            raise ValueError("duplicate source_query_id")
        result[qid] = row
    return result


def _identity(row: dict[str, Any]) -> tuple[int, int]:
    if any(type(row.get(key)) is not int for key in ("dataset_id", "doc_id")):
        raise ValueError("invalid candidate identity")
    return row["dataset_id"], row["doc_id"]


def _method_view(row: dict[str, Any], query: str) -> dict[str, Any]:
    """Validate the saved complete pool; never fetch or repair candidate text."""
    if row.get("query") != query:
        raise ValueError("query mismatch")
    if (
        row.get("ranking_input_ready") is not True
        or row.get("failed_sources") != []
        or row.get("status") not in {"ready", "empty"}
    ):
        raise ValueError("incomplete candidate input")
    routes = row.get("routes")
    statuses = row.get("route_status")
    if not isinstance(routes, dict) or set(routes) != set(ROUTES):
        raise ValueError("incomplete routes")
    if not isinstance(statuses, dict) or set(statuses) != set(ROUTES):
        raise ValueError("incomplete route status")
    scope = row.get("dataset_ids")
    if not isinstance(scope, list) or not scope or any(type(v) is not int for v in scope):
        raise ValueError("invalid dataset scope")
    identities: dict[str, tuple[int, int]] = {}
    doc_owner: dict[int, str] = {}
    method_routes = {}
    for source in ROUTES:
        hits = routes[source]
        if not isinstance(hits, list) or statuses[source] != ("ok" if hits else "empty"):
            raise ValueError("route status mismatch")
        seen = set()
        clean_hits = []
        for rank, hit in enumerate(hits):
            cid = _text(hit, "chunk_id")
            identity = _identity(hit)
            if identity[0] not in scope or cid in seen:
                raise ValueError("duplicate or out-of-scope route candidate")
            if type(hit.get("rank")) is not int or hit["rank"] != rank:
                raise ValueError("route rank mismatch")
            score = hit.get("score")
            if (
                isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not math.isfinite(score)
            ):
                raise ValueError("non-finite or invalid route score")
            if cid in identities and identities[cid] != identity:
                raise ValueError("cross-route identity mismatch")
            # This experiment has one independent document per passage. The
            # existing feature core groups on doc_id alone, so collisions matter.
            if identity[1] in doc_owner and doc_owner[identity[1]] != cid:
                raise ValueError("independent passage doc_id collision")
            identities[cid], doc_owner[identity[1]] = identity, cid
            seen.add(cid)
            clean_hits.append(
                {
                    "chunk_id": cid,
                    "dataset_id": identity[0],
                    "doc_id": identity[1],
                    "score": score,
                    "rank": rank,
                }
            )
        method_routes[source] = clean_hits
    candidate_rows = row.get("candidate_rows")
    if not isinstance(candidate_rows, list):
        raise TypeError("missing candidate rows")
    contents = {}
    for candidate in candidate_rows:
        cid = _text(candidate, "chunk_id")
        if cid in contents or cid not in identities or _identity(candidate) != identities[cid]:
            raise ValueError("candidate identity mismatch")
        contents[cid] = _text(candidate, "content")
        _text(candidate, "source_passage_id")
    if set(contents) != set(identities):
        raise ValueError("candidate rows do not cover full union")
    return {"query": query, "routes": method_routes, "candidate_contents": contents}


def _check_supervision(
    role: str,
    query_by_id: dict[str, dict[str, Any]],
    labels: dict[str, dict[str, Any]],
) -> set[str]:
    if set(labels) != set(query_by_id):
        raise ValueError("supervision must match all planned queries")
    pairs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    comparisons: dict[tuple[str, tuple[str, str]], list[dict[str, Any]]] = defaultdict(list)
    for qid, label in labels.items():
        if label.get("role") != role:
            raise ValueError("supervision role mismatch")
        for key in (
            "source_group_id",
            "pair_id",
            "label_basis",
            "preferred_chunk_id",
            "other_chunk_id",
            "preferred_passage_id",
            "other_passage_id",
        ):
            _text(label, key)
        for key in ("official_label_available", "structural_conflict", "semantic_uncertain"):
            if type(label.get(key)) is not bool:
                raise ValueError(f"invalid supervision flag {key}")
        if label.get("direction") not in {"q1", "q2"}:
            raise ValueError("invalid pair direction")
        if not isinstance(label.get("issue_reasons"), list):
            raise TypeError("missing issue_reasons")
        if (
            label["preferred_chunk_id"] == label["other_chunk_id"]
            or label["preferred_passage_id"] == label["other_passage_id"]
        ):
            raise ValueError("preference targets must be distinct")
        pairs[label["pair_id"]].append(label)
        if label["official_label_available"]:
            key = (
                query_by_id[qid]["query"],
                tuple(sorted((label["preferred_chunk_id"], label["other_chunk_id"]))),
            )
            comparisons[key].append(label)
    for rows in pairs.values():
        if len(rows) != 2 or {r["direction"] for r in rows} != {"q1", "q2"}:
            raise ValueError("each official pair requires two planned query directions")
        a, b = rows
        if (
            a["source_group_id"] != b["source_group_id"]
            or a["preferred_chunk_id"] != b["other_chunk_id"]
            or a["other_chunk_id"] != b["preferred_chunk_id"]
            or a["preferred_passage_id"] != b["other_passage_id"]
            or a["other_passage_id"] != b["preferred_passage_id"]
        ):
            raise ValueError("inconsistent official pair identity")
    conflicts = {qid for qid, r in labels.items() if r["structural_conflict"]}
    for rows in comparisons.values():
        if len({r["preferred_chunk_id"] for r in rows}) > 1 or any(
            r["structural_conflict"] for r in rows
        ):
            conflicts.update(r["source_query_id"] for r in rows)
    return conflicts


def prepare_pairwise_dataset(
    *,
    role: str,
    queries: list[dict[str, Any]],
    supervision: list[dict[str, Any]],
    inputs: list[dict[str, Any]],
    feature_version: str = FEATURE_VERSION,
    background_negative_count: int = 0,
) -> PairwiseDataset:
    """Compute full-pool features, then select judged and optional background rows."""
    rules_version(feature_version)
    if role not in {"train", "development"}:
        raise ValueError("training accepts only train and development roles")
    if type(background_negative_count) is not int or background_negative_count < 0:
        raise ValueError("background negative count must be a non-negative integer")
    if role != "train" and background_negative_count:
        raise ValueError("background negatives are only allowed in the training loss")
    query_by_id, labels, input_by_id = map(_indexed, (queries, supervision, inputs))
    for row in queries:
        _text(row, "query")
    if set(input_by_id) - set(query_by_id):
        raise ValueError("unexpected candidate query")
    conflicts = _check_supervision(role, query_by_id, labels)
    prepared = []
    feature_compute_seconds = 0.0
    seen_training: dict[tuple[str, str, str], list[PreparedQuery]] = defaultdict(list)
    for qid, planned in query_by_id.items():
        label = dict(labels[qid])
        label["structural_conflict"] = qid in conflicts
        item = PreparedQuery(query_id=qid, query=planned["query"], supervision=label)
        prepared.append(item)
        if not label["official_label_available"]:
            item.exclusion_reasons.append("official_label_unavailable")
        if role == "train" and qid in conflicts:
            item.exclusion_reasons.append("structural_conflict")
        row = input_by_id.get(qid)
        if row is None:
            item.exclusion_reasons.append("input_not_executed")
            continue
        try:
            item.method_view = _method_view(row, item.query)
            feature_started = time.perf_counter()
            item.chunk_ids, item.features = build_online_features(**item.method_view, feature_version=feature_version)
            feature_compute_seconds += time.perf_counter() - feature_started
            if (
                item.features.shape != (len(item.chunk_ids), len(FEATURE_NAMES))
                or not np.isfinite(item.features).all()
            ):
                raise ValueError("invalid feature matrix")
            passage_ids = {r["chunk_id"]: r["source_passage_id"] for r in row["candidate_rows"]}
            for prefix in ("preferred", "other"):
                cid = label[f"{prefix}_chunk_id"]
                if cid in passage_ids and passage_ids[cid] != label[f"{prefix}_passage_id"]:
                    raise ValueError("supervision passage mapping mismatch")
        except (KeyError, TypeError, ValueError, OverflowError):
            item.method_view, item.features, item.chunk_ids = None, None, []
            item.exclusion_reasons.append("invalid_or_incomplete_input")
            continue
        targets = {label["preferred_chunk_id"], label["other_chunk_id"]}
        item.selected_indices = [i for i, cid in enumerate(item.chunk_ids) if cid in targets]
        if len(item.selected_indices) != 2:
            item.exclusion_reasons.append("targets_not_jointly_recalled")
        elif background_negative_count:
            background = [i for i, cid in enumerate(item.chunk_ids) if cid not in targets]
            if len(background) < background_negative_count:
                item.exclusion_reasons.append("insufficient_background_candidates")
            else:
                seed = int.from_bytes(
                    hashlib.sha256(f"{SEED}:{qid}".encode()).digest()[:8], "big"
                )
                sampled = random.Random(seed).sample(background, background_negative_count)
                item.loss_indices = [*item.selected_indices, *sorted(sampled)]
        else:
            item.loss_indices = list(item.selected_indices)
        if role == "train" and not item.exclusion_reasons:
            key = (item.query, label["preferred_chunk_id"], label["other_chunk_id"])
            for previous in seen_training[key]:
                if previous.method_view == item.method_view:
                    if previous.supervision["source_group_id"] != label["source_group_id"]:
                        raise ValueError("duplicate supervision crosses source groups")
                    item.duplicate_of = previous.query_id
                    item.exclusion_reasons.append("duplicate_supervision")
                    break
            seen_training[key].append(item)
    blocks = [q for q in prepared if not q.exclusion_reasons]
    x = (
        np.concatenate([q.features[q.loss_indices] for q in blocks])
        if blocks
        else np.empty((0, len(FEATURE_NAMES)), dtype=np.float32)
    )
    if background_negative_count:
        y = np.asarray(
            [
                2
                if q.chunk_ids[i] == q.supervision["preferred_chunk_id"]
                else 1
                if q.chunk_ids[i] == q.supervision["other_chunk_id"]
                else 0
                for q in blocks
                for i in q.loss_indices
            ],
            dtype=np.int32,
        )
    else:
        y = np.asarray(
            [
                int(q.chunk_ids[i] == q.supervision["preferred_chunk_id"])
                for q in blocks
                for i in q.loss_indices
            ],
            dtype=np.int32,
        )
    counts = Counter(q.supervision["source_group_id"] for q in blocks)
    weights = np.asarray(
        [
            len(blocks) / (len(counts) * counts[q.supervision["source_group_id"]])
            for q in blocks
            for _ in q.loss_indices
        ],
        dtype=np.float64,
    )
    all_sources = sorted({q.supervision["source_group_id"] for q in prepared})
    summary = {
        "role": role,
        "planned_query_count": len(prepared),
        "planned_pair_count": len({q.supervision["pair_id"] for q in prepared}),
        "source_group_ids": all_sources,
        "planned_source_count": len(all_sources),
        "input_row_count": len(inputs),
        "eligible_query_count": len(blocks),
        "eligible_source_count": len(counts),
        "eligible_source_group_ids": sorted(counts),
        "ranking_group_count": len(blocks),
        "loss_row_count": len(x) if role == "train" else 0,
        "background_negative_count": background_negative_count,
        "background_negative_sampling": (
            "sha256(seed:source_query_id), sampled without replacement from non-target full-pool candidates"
            if background_negative_count
            else "disabled"
        ),
        "loss_labels": (
            {"preferred": 2, "other_designated": 1, "background": 0}
            if background_negative_count
            else {"preferred": 1, "other_designated": 0}
        ),
        "full_pool_ready_query_count": sum(q.features is not None for q in prepared),
        "jointly_recalled_query_count": sum(len(q.selected_indices) == 2 for q in prepared),
        "exclusion_counts": dict(
            sorted(Counter(r for q in prepared for r in q.exclusion_reasons).items())
        ),
        "structural_conflict_query_ids": sorted(conflicts),
        "semantic_uncertain_query_count": sum(
            q.supervision["semantic_uncertain"] for q in prepared
        ),
        "query_order": list(query_by_id),
        "weighting": "N_queries / (N_sources * queries_in_source); equal weight for all rows",
    }
    summary.update(feature_version=feature_version, feature_rules_version=rules_version(feature_version))
    summary["feature_compute_seconds"] = feature_compute_seconds
    return PairwiseDataset(
        role,
        prepared,
        blocks,
        x,
        y,
        [len(q.loss_indices) for q in blocks],
        weights,
        summary,
        feature_version,
    )


def assert_disjoint_roles(train: PairwiseDataset, development: PairwiseDataset) -> None:
    if train.role != "train" or development.role != "development":
        raise ValueError("expected train and development datasets")
    for key in ("source_group_id", "pair_id"):
        left = {q.supervision[key] for q in train.queries}
        right = {q.supervision[key] for q in development.queries}
        if left & right:
            raise ValueError(f"train/development {key} overlap")
    if {q.query_id for q in train.queries} & {q.query_id for q in development.queries}:
        raise ValueError("train/development query ID overlap")
    if {q.query for q in train.queries} & {q.query for q in development.queries}:
        raise ValueError("train/development exact query overlap")


@dataclass
class _MetricLayout:
    y: np.ndarray
    sources: list[str]
    pairs: list[str]
    directions: list[str]


def _layout(dataset: PairwiseDataset) -> _MetricLayout:
    return _MetricLayout(
        dataset.y,
        [q.supervision["source_group_id"] for q in dataset.blocks],
        [q.supervision["pair_id"] for q in dataset.blocks],
        [q.supervision["direction"] for q in dataset.blocks],
    )


def _metric_values(layout: _MetricLayout, scores: Any) -> dict[str, Any]:
    values = np.asarray(scores, dtype=np.float64)
    n = len(layout.sources)
    if not n:
        raise ValueError("no eligible development preferences")
    if values.shape != (2 * n,) or not np.isfinite(values).all():
        raise ValueError("invalid or non-finite development scores; denominator is fixed")
    labels = layout.y.reshape(-1, 2)
    if labels.shape != (n, 2) or not np.all(np.sort(labels, axis=1) == [0, 1]):
        raise ValueError("invalid pair labels")
    delta = (values.reshape(-1, 2) * (2 * labels - 1)).sum(axis=1)
    correct = delta > 0
    per_source: dict[str, list[bool]] = defaultdict(list)
    pairs: dict[str, list[int]] = defaultdict(list)
    for index, (source, pair) in enumerate(zip(layout.sources, layout.pairs, strict=True)):
        per_source[source].append(bool(correct[index]))
        pairs[pair].append(index)
    paired_source: dict[str, list[bool]] = defaultdict(list)
    for indices in pairs.values():
        if len(indices) == 2 and {layout.directions[i] for i in indices} == {"q1", "q2"}:
            if len({layout.sources[i] for i in indices}) != 1:
                raise ValueError("pair spans source groups")
            paired_source[layout.sources[indices[0]]].append(bool(correct[indices].all()))
    pair_count = sum(map(len, paired_source.values()))
    return {
        PRIMARY_METRIC: math.fsum(
            sum(per_source[s]) / len(per_source[s]) for s in sorted(per_source)
        )
        / len(per_source),
        "source_macro_pair_accuracy": (
            math.fsum(sum(paired_source[s]) / len(paired_source[s]) for s in sorted(paired_source))
            / len(paired_source)
            if paired_source
            else None
        ),
        "query_micro_accuracy": int(correct.sum()) / n,
        "query_count": n,
        "source_count": len(per_source),
        "correct": int(correct.sum()),
        "wrong": int((delta < 0).sum()),
        "tie": int((delta == 0).sum()),
        "pair_count": pair_count,
        "pair_correct": sum(sum(v) for v in paired_source.values()),
    }


def development_metrics(dataset: PairwiseDataset, scores: Any) -> dict[str, Any]:
    return _metric_values(_layout(dataset), scores)


def _evaluation_function(layout: _MetricLayout) -> Callable[..., tuple[str, float, bool]]:
    def evaluate(y_true, y_pred, weight, group):
        if not np.array_equal(y_true, layout.y) or not np.array_equal(
            group, [2] * len(layout.sources)
        ):
            raise ValueError("development labels or group order mismatch")
        if weight is not None:
            raise ValueError("development macro metric must not be weighted twice")
        return PRIMARY_METRIC, _metric_values(layout, y_pred)[PRIMARY_METRIC], True

    return evaluate


def make_development_metric(dataset: PairwiseDataset) -> Callable[..., tuple[str, float, bool]]:
    return _evaluation_function(_layout(dataset))


def select_best_candidate(reports: list[dict[str, Any]]) -> dict[str, Any]:
    if not reports or any(r.get("status") != "complete" for r in reports):
        raise ValueError("cannot select from an incomplete grid")
    if len(reports) != len(GRID) or {r.get("config_id") for r in reports} != {
        config["config_id"] for config in GRID
    }:
        raise ValueError("selection requires exactly one report for each of c1-c6")
    denominators = {
        (r["dev_metrics"]["query_count"], r["dev_metrics"]["pair_count"]) for r in reports
    }
    if len(denominators) != 1:
        raise ValueError("candidate development denominators differ")

    def key(row):
        metrics = row["dev_metrics"]
        primary, paired = metrics[PRIMARY_METRIC], metrics["source_macro_pair_accuracy"]
        if not math.isfinite(primary) or (paired is not None and not math.isfinite(paired)):
            raise ValueError("non-finite candidate selection metric")
        return (
            -primary,
            -(paired if paired is not None else 0),
            row["actual_trees"],
            row["num_leaves"],
            -row["reg_lambda"],
            row["config_id"],
        )

    return min(reports, key=key)


def training_parameters(
    config: dict[str, Any], *, background_negative_count: int = 0
) -> dict[str, Any]:
    return {
        "objective": "lambdarank",
        "boosting_type": "gbdt",
        "metric": "None",
        "n_estimators": MAX_ITERATIONS,
        "learning_rate": 0.03,
        "num_leaves": config["num_leaves"],
        "max_depth": config["max_depth"],
        "reg_lambda": config["reg_lambda"],
        "reg_alpha": 0.0,
        "min_child_samples": 20,
        "min_child_weight": 0.001,
        "min_split_gain": 0.0,
        "colsample_bytree": 0.8,
        "feature_fraction_bynode": 1.0,
        "subsample": 1.0,
        "subsample_freq": 0,
        "label_gain": [0, 1, 2] if background_negative_count else [0, 1],
        "sigmoid": 1.0,
        "lambdarank_norm": True,
        "lambdarank_truncation_level": 2,
        "max_bin": 255,
        "zero_as_missing": False,
        "use_missing": True,
        "n_jobs": 1,
        "deterministic": True,
        "force_col_wise": True,
        "random_state": SEED,
        "feature_fraction_seed": SEED,
        "bagging_seed": SEED,
        "data_random_seed": SEED,
        "verbosity": -1,
    }


def _fit_candidate(
    train_x,
    train_y,
    train_groups,
    train_weights,
    dev_x,
    layout: _MetricLayout,
    params: dict[str, Any],
    feature_names: Sequence[str] | None = None,
    *,
    progress: Callable[[dict[str, Any]], None],
) -> tuple[str, dict[str, Any]]:
    """One fit only; the returned model string contains the chosen prefix."""
    import lightgbm as lgb

    started = time.monotonic()
    names = list(FEATURE_NAMES if feature_names is None else feature_names)
    if (len(set(names)) != len(names) or train_x.shape[1] != len(names)
            or dev_x.shape[1] != len(names)):
        raise ValueError("training feature names/width mismatch")

    def on_iteration(env):
        if len(env.evaluation_result_list) != 1:
            raise ValueError("expected exactly one development metric")
        result = env.evaluation_result_list[0]
        if result[1] != PRIMARY_METRIC:
            raise ValueError("unexpected early stopping metric")
        progress(
            {
                "iteration": env.iteration + 1,
                PRIMARY_METRIC: float(result[2]),
                "elapsed_seconds": time.monotonic() - started,
            }
        )

    on_iteration.order = 25
    on_iteration.before_iteration = False
    ranker = lgb.LGBMRanker(**params)
    ranker.fit(
        train_x,
        train_y,
        group=train_groups,
        sample_weight=train_weights,
        eval_set=[(dev_x, layout.y)],
        eval_group=[[2] * len(layout.sources)],
        eval_names=["development"],
        eval_metric=_evaluation_function(layout),
        feature_name=names,
        callbacks=[
            on_iteration,
            lgb.early_stopping(PATIENCE, first_metric_only=True, min_delta=0.0, verbose=False),
        ],
    )
    iteration = int(ranker.best_iteration_)
    if iteration <= 0:
        raise ValueError("missing best iteration")
    prefix = ranker.booster_.model_to_string(num_iteration=iteration)
    saved = lgb.Booster(model_str=prefix)
    scores = saved.predict(dev_x, num_threads=1)
    return prefix, {
        "best_iteration": iteration,
        "actual_trees": saved.num_trees(),
        "dev_metrics": _metric_values(layout, scores),
        "booster_params": dict(ranker.booster_.params),
        "elapsed_seconds": time.monotonic() - started,
    }


def _fit_worker(connection, args) -> None:
    try:
        model, result = _fit_candidate(
            *args, progress=lambda row: connection.send(("iteration", row))
        )
        connection.send(("complete", (model, result)))
    except Exception as exc:  # noqa: BLE001 — Record only the exception type, never source text.
        connection.send(("failed", {"error_type": type(exc).__name__}))
    finally:
        connection.close()


def _bounded_fit(
    args, *, timeout_seconds: float, progress: Callable, total_deadline: float | None = None
) -> tuple[str, dict[str, Any]]:
    """A process boundary enforces the limit even inside a native boosting call."""
    deadline = time.monotonic() + timeout_seconds
    if total_deadline is not None:
        deadline = min(deadline, total_deadline)
    if deadline <= time.monotonic():
        raise TimeoutError("fixed training time budget exhausted")
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_fit_worker, args=(sender, args))
    process.start()
    sender.close()
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("fixed training time budget exhausted")
            if receiver.poll(min(remaining, 0.2)):
                try:
                    kind, payload = receiver.recv()
                except EOFError as exc:
                    raise RuntimeError("training worker exited without a result") from exc
                if kind == "iteration":
                    progress(payload)
                elif kind == "complete":
                    if time.monotonic() >= deadline:
                        raise TimeoutError("training result arrived after the fixed deadline")
                    return payload
                else:
                    raise RuntimeError(f"training worker failed: {payload['error_type']}")
            # Child exit is not a completion signal: it may follow a successful
            # send between poll() and an is_alive() check. Drain the pipe until
            # complete or EOF instead; native crashes also close the child end.
    finally:
        receiver.close()
        process.join(timeout=0.2)
        if process.is_alive():
            process.terminate()
            process.join(timeout=1)
        if process.is_alive():
            process.kill()
            process.join(timeout=1)
        process.close()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("JSONL rows must be objects")
    return rows


def load_dataset(
    *,
    role: str,
    queries: Path,
    supervision: Path,
    inputs: Path,
    feature_version: str = FEATURE_VERSION,
    background_negative_count: int = 0,
) -> PairwiseDataset:
    labels = _read_jsonl(supervision)
    if role not in {"train", "development"} or any(r.get("role") != role for r in labels):
        raise ValueError("supervision role mismatch before reading queries or candidates")
    return prepare_pairwise_dataset(
        role=role,
        queries=_read_jsonl(queries),
        supervision=labels,
        inputs=_read_jsonl(inputs),
        feature_version=feature_version,
        background_negative_count=background_negative_count,
    )


def _write_selection(path: Path, selection: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(selection, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _code_version() -> dict[str, str]:
    root = Path(__file__).resolve().parents[4]
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    )
    return {
        "head": result.stdout.strip(),
        "implementation": "pairwise_training.py; working-tree changes may be uncommitted",
    }


def _development_predictions(dataset: PairwiseDataset, booster) -> list[dict[str, Any]]:
    results = []
    for item in dataset.queries:
        row = {
            "source_query_id": item.query_id,
            "source_group_id": item.supervision["source_group_id"],
            "pair_id": item.supervision["pair_id"],
            "direction": item.supervision["direction"],
            "official_label_available": item.supervision["official_label_available"],
            "structural_conflict": item.supervision["structural_conflict"],
            "semantic_uncertain": item.supervision["semantic_uncertain"],
            "semantic_review_status": item.supervision.get(
                "semantic_review_status", "not_provided"
            ),
            "exclusion_reasons": item.exclusion_reasons,
            "candidate_count": len(item.chunk_ids),
            "preference_relation": "unavailable",
            "scores": None,
            "order": None,
        }
        if item.features is not None and len(item.chunk_ids):
            scores = np.asarray(booster.predict(item.features, num_threads=1), dtype=np.float64)
            if scores.shape != (len(item.chunk_ids),) or not np.isfinite(scores).all():
                raise ValueError("invalid complete-pool development prediction")
            row["scores"] = [
                {"chunk_id": cid, "score": float(score)}
                for cid, score in zip(item.chunk_ids, scores, strict=True)
            ]
            row["order"] = [
                cid
                for cid, score in sorted(
                    zip(item.chunk_ids, scores, strict=True),
                    key=lambda pair: (-float(pair[1]), pair[0]),
                )
            ]
            if not item.exclusion_reasons:
                by_id = dict(zip(item.chunk_ids, scores, strict=True))
                delta = float(
                    by_id[item.supervision["preferred_chunk_id"]]
                    - by_id[item.supervision["other_chunk_id"]]
                )
                row["score_difference"] = delta
                row["preference_relation"] = (
                    "correct" if delta > 0 else "wrong" if delta < 0 else "tie"
                )
        results.append(row)
    return results


def train_and_select(
    train: PairwiseDataset,
    development: PairwiseDataset,
    *,
    out_dir: Path,
    policy_source: Path,
    input_paths: dict[str, str],
    model_version: str,
    config_id: str | None = None,
) -> dict[str, Any]:
    """Use the historical grid, or one explicitly selected existing configuration; no refit."""
    import lightgbm as lgb

    from linkrag_eval.retrieval.learning_to_rank.online import (
        LambdaMartOnlineRanker,
        export_trained_booster,
    )

    assert_disjoint_roles(train, development)
    if train.feature_version != development.feature_version:
        raise ValueError("train/development feature versions differ")
    rules_version(train.feature_version)
    grid = GRID if config_id is None else tuple(c for c in GRID if c["config_id"] == config_id)
    if not grid:
        raise ValueError("unknown fixed training configuration")
    if train.feature_version != FEATURE_VERSION and config_id is None:
        raise ValueError("English experiment requires one explicit configuration")
    if not train.blocks or not development.blocks:
        raise ValueError("train and development require eligible preferences")
    baseline = LambdaMartOnlineRanker(policy_source)
    manifest = asdict(baseline.manifest)
    if baseline.short_fallback is None:
        raise ValueError("A must supply its frozen short-query fallback")
    short = asdict(baseline.short_fallback)
    if (
        manifest["model_version"] != "candidate-difference-v3-20260728-final33"
        or manifest["feature_names"] != FEATURE_NAMES
        or manifest["feature_version"] != FEATURE_VERSION
        or manifest["lightgbm_version"] != lgb.__version__
        or manifest["alias_enabled"] is not False
        or manifest["fallback_policy"] != "hybrid"
    ):
        raise ValueError("A policy source feature/runtime contract mismatch")
    out_dir.mkdir(parents=True, exist_ok=False)
    selection_path = out_dir / "selection.json"
    selection = {
        "status": "running",
        "feature_version": train.feature_version,
        "feature_rules_version": rules_version(train.feature_version),
        "feature_names": FEATURE_NAMES,
        "code": _code_version(),
        "versions": {
            name: importlib.metadata.version(name) for name in ("lightgbm", "numpy", "scikit-learn")
        },
        "input_paths": input_paths,
        "policy_source": str(policy_source.resolve()),
        "policy": {
            "model_version": manifest["model_version"],
            "short_fallback": short,
            "latency_budget_ms": manifest["latency_budget_ms"],
            "timeout_ms": manifest["timeout_ms"],
        },
        "train": train.summary,
        "development": development.summary,
        "seed": SEED,
        "maximum_fits": len(grid),
        "maximum_iterations_per_fit": MAX_ITERATIONS,
        "patience": PATIENCE,
        "candidate_timeout_seconds": CANDIDATE_TIMEOUT_SECONDS,
        "total_timeout_seconds": TOTAL_TIMEOUT_SECONDS,
        "selection_order": [
            PRIMARY_METRIC,
            "source_macro_pair_accuracy",
            "fewer_actual_trees",
            "fewer_num_leaves",
            "larger_reg_lambda",
            "config_id",
        ],
        "primary_metric_scope": "eligible jointly recalled queries, mean within source then across sources",
        "final_evaluation_distinction": "confirmation query micro-average is separate and is not consumed here",
        "refit": False,
        "grid": [
            {
                **config,
                "status": "not_started",
                "params": training_parameters(
                    config,
                    background_negative_count=train.summary["background_negative_count"],
                ),
                "history": [],
            }
            for config in grid
        ],
        "selected_config_id": None,
    }
    _write_selection(selection_path, selection)
    started = time.monotonic()
    total_deadline = started + TOTAL_TIMEOUT_SECONDS
    models = {}
    try:
        for report in selection["grid"]:
            remaining = TOTAL_TIMEOUT_SECONDS - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("total fixed training budget exhausted")
            report["status"] = "running"
            _write_selection(selection_path, selection)

            def progress(row, report=report):
                report["history"].append(row)
                _write_selection(selection_path, selection)

            args = (
                train.x,
                train.y,
                train.groups,
                train.weights,
                development.x,
                _layout(development),
                report["params"],
            )
            try:
                model, result = _bounded_fit(
                    args,
                    timeout_seconds=min(remaining, CANDIDATE_TIMEOUT_SECONDS),
                    progress=progress,
                    total_deadline=total_deadline,
                )
            except (Exception, KeyboardInterrupt) as exc:
                report["status"] = "timeout" if isinstance(exc, TimeoutError) else "failed"
                report["error_type"] = type(exc).__name__
                raise
            report.update(result, status="complete")
            report["stop_reason"] = (
                "maximum_iterations"
                if len(report["history"]) == MAX_ITERATIONS
                else "early_stopping"
            )
            models[report["config_id"]] = model
            _write_selection(selection_path, selection)
        winner = select_best_candidate(selection["grid"]) if config_id is None else selection["grid"][0]
        booster = lgb.Booster(model_str=models[winner["config_id"]])
        prediction_started = time.perf_counter()
        predictions = _development_predictions(development, booster)
        selection["development_prediction_and_order_seconds"] = time.perf_counter() - prediction_started
        exported = export_trained_booster(
            booster,
            out_dir=out_dir / "model-b",
            model_version=model_version,
            num_iteration=booster.num_trees(),
            training_params=winner["params"],
            short_fallback_config=short,
            latency_budget_ms=manifest["latency_budget_ms"],
            timeout_ms=manifest["timeout_ms"],
            feature_version=train.feature_version,
        )
        with (out_dir / "dev-predictions.jsonl").open("x", encoding="utf-8") as stream:
            for row in predictions:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        selection.update(
            status="complete",
            selected_config_id=winner["config_id"],
            model_version=exported.model_version,
            actual_trees=exported.n_estimators,
            model_path=str((out_dir / "model-b").resolve()),
            selection_reason=("lexicographic predeclared development metrics and complexity; no refit"
                              if config_id is None else "fixed configuration; earliest best development iteration; no refit"),
            elapsed_seconds=time.monotonic() - started,
        )
        _write_selection(selection_path, selection)
        return selection
    except (Exception, KeyboardInterrupt) as exc:
        selection.update(
            status="timeout" if isinstance(exc, TimeoutError) else "failed",
            error_type=type(exc).__name__,
            elapsed_seconds=time.monotonic() - started,
        )
        _write_selection(selection_path, selection)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for role in ("train", "development"):
        for kind in ("queries", "supervision", "inputs"):
            parser.add_argument(f"--{role}-{kind}", required=True, type=Path)
    parser.add_argument("--policy-source", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--feature-version", choices=FEATURE_VERSIONS, default=FEATURE_VERSION)
    parser.add_argument("--config-id", choices=[c["config_id"] for c in GRID])
    parser.add_argument(
        "--background-negatives",
        type=int,
        default=0,
        help="deterministically sample N background candidates per training query (default: 0)",
    )
    args = parser.parse_args(argv)
    paths = {
        f"{role}_{kind}": str(getattr(args, f"{role}_{kind}").resolve())
        for role in ("train", "development")
        for kind in ("queries", "supervision", "inputs")
    }
    datasets = [
        load_dataset(
            role=role,
            feature_version=args.feature_version,
            background_negative_count=args.background_negatives if role == "train" else 0,
            **{
                kind: getattr(args, f"{role}_{kind}")
                for kind in ("queries", "supervision", "inputs")
            },
        )
        for role in ("train", "development")
    ]
    result = train_and_select(
        *datasets,
        out_dir=args.out_dir,
        policy_source=args.policy_source,
        input_paths=paths,
        model_version=args.model_version,
        config_id=args.config_id,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "selected_config_id": result["selected_config_id"],
                "model_path": result["model_path"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
