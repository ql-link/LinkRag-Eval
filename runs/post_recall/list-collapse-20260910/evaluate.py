"""Verify the Issue #23 handoff using local Development/Confirmation only.

Preserve the member's results.json. Write new predictions and acceptance.json;
never train, retrieve candidates, or read official Test rows.
"""

from __future__ import annotations

import json
import math
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

import lightgbm as lgb

from linkrag_eval.retrieval.learning_to_rank.features import (
    ENGLISH_FEATURE_VERSION,
    build_online_features,
)
from linkrag_eval.retrieval.learning_to_rank.llm_judge import (
    baseline_order,
    evaluate_pairs,
    list_metrics,
    score_maps,
)
from linkrag_eval.retrieval.learning_to_rank.online import validate_production_bundle
from linkrag_eval.retrieval.learning_to_rank.pairwise_training import _method_view

RUN = Path(__file__).resolve().parent
ROOT = RUN.parents[2]
INPUT = ROOT / "runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment"
PILOT = ROOT / "runs/post_recall/llm-judge-pilot-20260910"
HISTORICAL = ROOT / "runs/post_recall/list-collapse-inputs-20260910"


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def summarize(labels: list[dict], scores: dict) -> dict:
    report, rows = evaluate_pairs(labels, scores, scores)
    label_map = {row["source_query_id"]: row for row in labels}
    orders = {qid: baseline_order(values) for qid, values in scores.items()}
    metrics = list_metrics(rows, orders, label_map)
    ranks = []
    for row in rows:
        qid = row["source_query_id"]
        positions = {cid: rank for rank, cid in enumerate(orders[qid], 1)}
        label = label_map[qid]
        ranks.append((positions[label["preferred_chunk_id"]], positions[label["other_chunk_id"]]))
    return {
        "queries": len(rows),
        "strict_correct": report["judge"]["strict_correct"],
        "strict_wrong": report["judge"]["reverse"],
        "strict_tie": report["judge"]["model_tie"],
        **metrics,
        "median_rank_designated": statistics.median(rank for pair in ranks for rank in pair),
        "both_in_top10": sum(max(pair) <= 10 for pair in ranks),
    }


def compare(actual: dict, expected: dict) -> None:
    for key, value in expected.items():
        if key == "source":
            continue
        observed = actual[key]
        if isinstance(value, float):
            assert math.isclose(observed, value, rel_tol=0, abs_tol=1e-12), key
        else:
            assert observed == value, (key, observed, value)


def main() -> None:
    started = time.monotonic()
    received = json.loads((RUN / "results.json").read_text())
    reference = json.loads((HISTORICAL / "confirmation-list-metrics-reference.json").read_text())
    models = {
        "E0": RUN / "baseline-disabled-replay/model-b",
        "background_n8": RUN / "background-n8-training/model-b",
    }
    bundles = {name: validate_production_bundle(path) for name, path in models.items()}
    boosters = {name: lgb.Booster(model_file=str(path / "model.txt")) for name, path in models.items()}
    result = {}
    for role, total, eligible in (("development", 76, 74), ("confirmation", 374, 371)):
        labels = read_rows(INPUT / f"prepared/{role}/supervision.jsonl")
        assert len(labels) == total and all(row["role"] == role for row in labels)
        queries = {row["source_query_id"]: row for row in read_rows(INPUT / f"prepared/{role}/queries.jsonl")}
        inputs = read_rows(INPUT / f"candidates/{role}/inputs.jsonl")
        assert len(inputs) == len(queries) == total
        assert {row["source_query_id"] for row in inputs} == set(queries)
        assert {row["source_query_id"] for row in labels} == set(queries)
        cached_e0 = score_maps(read_rows(PILOT / f"baseline/{role}/scores.jsonl"))
        predictions = {name: [] for name in models}
        for index, row in enumerate(inputs, 1):
            qid = row["source_query_id"]
            ids, features = build_online_features(
                **_method_view(row, queries[qid]["query"]),
                feature_version=ENGLISH_FEATURE_VERSION,
            )
            for name, booster in boosters.items():
                values = booster.predict(features, num_threads=1)
                assert len(values) == len(ids) and all(math.isfinite(float(v)) for v in values)
                scores = [{"chunk_id": cid, "score": float(v)} for cid, v in zip(ids, values, strict=True)]
                predictions[name].append({"source_query_id": qid, "scores": scores})
                if name == "E0":
                    assert {r["chunk_id"]: r["score"] for r in scores} == cached_e0[qid]
            if index % 50 == 0 or index == total:
                print(json.dumps({"role": role, "queries_scored": index, "total": total}), flush=True)
        result[role] = {}
        for name, rows in predictions.items():
            summary = summarize(labels, score_maps(rows))
            assert summary["queries"] == eligible
            compare(summary, received[role][name])
            result[role][name] = summary
            out = RUN / f"{name}-{role}-scores.jsonl"
            out.write_text("".join(json.dumps(row, allow_nan=False) + "\n" for row in rows))
        if role == "confirmation":
            sources = {
                "A": HISTORICAL / "A-confirmation-scores.jsonl",
                "B": HISTORICAL / "B-confirmation-scores.jsonl",
                "E0": PILOT / "baseline/confirmation/scores.jsonl",
                "fusion": PILOT / "items-stage1-top20/confirmation/stage1-confirmation.jsonl",
            }
            for name, path in sources.items():
                scores = score_maps(read_rows(path))
                assert set(scores) == set(cached_e0)
                assert all(set(values) == set(cached_e0[qid]) for qid, values in scores.items())
                summary = summarize(labels, scores)
                compare(summary, received[role][name])
                compare(summary, reference["rankers"][name])
                result[role][name] = summary
    acceptance = {
        "verified_at": datetime.now(UTC).isoformat(),
        "status": "passed",
        "scope": "local development/confirmation predictions and metrics; no Test rows or training",
        "versions": {"lightgbm": lgb.__version__},
        "model_bundles": bundles,
        "e0_predictions_equal_existing_cache": True,
        "integer_metrics_exact": True,
        "floating_metric_absolute_tolerance": 1e-12,
        "reported_metrics_reproduced": result,
        "elapsed_seconds": time.monotonic() - started,
        "test_results": "received aggregates only; not independently reproduced",
    }
    (RUN / "acceptance.json").write_text(json.dumps(acceptance, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "passed", "elapsed_seconds": acceptance["elapsed_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
