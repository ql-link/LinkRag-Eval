"""One-shot aggregate evaluation of the frozen Issue #23 rankers on NevIR Test."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

import lightgbm as lgb

from linkrag_eval.retrieval.learning_to_rank.features import (
    ENGLISH_FEATURE_VERSION,
    FEATURE_NAMES,
    build_online_features,
)
from linkrag_eval.retrieval.learning_to_rank.pairwise_training import _method_view

ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / "runs/post_recall/nevir-test-final-20260911"
SNAPSHOT = ROOT / "runs/post_recall/nevir-test-candidates-20260910/snapshot"
MODELS = ROOT / "runs/post_recall/list-collapse-20260910"


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def indexed(rows: list[dict]) -> dict[str, dict]:
    result = {row["source_query_id"]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError("duplicate source_query_id")
    return result


def wilson(successes: int, total: int) -> list[float]:
    if total == 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [center - radius, center + radius]


def exact_mcnemar(left: list[bool], right: list[bool]) -> dict:
    improved = sum(not a and b for a, b in zip(left, right, strict=True))
    regressed = sum(a and not b for a, b in zip(left, right, strict=True))
    discordant = improved + regressed
    tail = min(improved, regressed)
    p_value = min(
        1.0,
        2 * sum(math.comb(discordant, k) for k in range(tail + 1)) / (2**discordant),
    ) if discordant else 1.0
    return {
        "e0_wrong_n8_correct": improved,
        "e0_correct_n8_wrong": regressed,
        "discordant": discordant,
        "exact_two_sided_p": p_value,
    }


def metrics(
    labels: dict[str, dict],
    rankings: dict[str, list[str]],
    scores: dict[str, dict[str, float]],
    population: list[str],
) -> tuple[dict, list[bool]]:
    correct_flags: list[bool] = []
    preferred_ranks: list[int] = []
    other_ranks: list[int] = []
    strict_wrong = 0
    strict_tie = 0
    both_top10 = 0
    for qid in population:
        positions = {chunk_id: rank for rank, chunk_id in enumerate(rankings[qid], 1)}
        preferred_rank = positions[labels[qid]["preferred_chunk_id"]]
        other_rank = positions[labels[qid]["other_chunk_id"]]
        delta = scores[qid][labels[qid]["preferred_chunk_id"]] - scores[qid][
            labels[qid]["other_chunk_id"]
        ]
        is_correct = delta > 0
        correct_flags.append(is_correct)
        strict_wrong += delta < 0
        strict_tie += delta == 0
        preferred_ranks.append(preferred_rank)
        other_ranks.append(other_rank)
        both_top10 += max(preferred_rank, other_rank) <= 10

    by_pair: dict[str, list[bool]] = defaultdict(list)
    for qid, correct in zip(population, correct_flags, strict=True):
        by_pair[labels[qid]["pair_id"]].append(correct)
    complete_pairs = [values for values in by_pair.values() if len(values) == 2]
    strict_correct = sum(correct_flags)
    designated = preferred_ranks + other_ranks
    return {
        "queries": len(population),
        "strict_correct": strict_correct,
        "strict_wrong": strict_wrong,
        "strict_tie": strict_tie,
        "strict_accuracy": strict_correct / len(population),
        "strict_accuracy_wilson_95ci": wilson(strict_correct, len(population)),
        "complete_pairs": len(complete_pairs),
        "both_directions_correct": sum(all(values) for values in complete_pairs),
        "both_directions_accuracy": sum(all(values) for values in complete_pairs) / len(complete_pairs),
        "preferred_at_1": sum(rank == 1 for rank in preferred_ranks) / len(population),
        "preferred_at_3": sum(rank <= 3 for rank in preferred_ranks) / len(population),
        "preferred_mrr": statistics.fmean(1 / rank for rank in preferred_ranks),
        "preferred_mean_rank": statistics.fmean(preferred_ranks),
        "other_mean_rank": statistics.fmean(other_ranks),
        "designated_median_rank": statistics.median(designated),
        "both_designated_in_top10": both_top10,
    }, correct_flags


def main() -> None:
    if (RUN / "results.json").exists():
        raise FileExistsError("received Test results already exist; refusing to overwrite or rescore")
    frozen = json.loads((RUN / "frozen-config.json").read_text(encoding="utf-8"))
    ingestion = json.loads((SNAPSHOT / "ingestion/state.json").read_text(encoding="utf-8"))
    candidate_state = json.loads(
        (SNAPSHOT / "candidates/test/state.json").read_text(encoding="utf-8")
    )
    if ingestion.get("status") != "completed" or candidate_state.get("status") != "completed":
        raise ValueError("Test candidate snapshot is not complete")

    paths = {
        "E0": MODELS / "baseline-disabled-replay/model-b/model.txt",
        "background_n8": MODELS / "background-n8-training/model-b/model.txt",
    }
    for name, path in paths.items():
        if sha256(path) != frozen["rankers"][name]["sha256"]:
            raise ValueError(f"frozen model hash mismatch: {name}")
    boosters = {name: lgb.Booster(model_file=str(path)) for name, path in paths.items()}

    queries = indexed(read_jsonl(SNAPSHOT / "prepared/test/queries.jsonl"))
    labels = indexed(read_jsonl(SNAPSHOT / "prepared/test/supervision.jsonl"))
    inputs = read_jsonl(SNAPSHOT / "candidates/test/inputs.jsonl")
    if len(queries) != 2766 or len(labels) != 2766 or len(inputs) != 2766:
        raise ValueError("official Test denominator changed")

    rankings: dict[str, dict[str, list[str]]] = {
        "E0": {},
        "fusion": {},
        "background_n8": {},
    }
    scores: dict[str, dict[str, dict[str, float]]] = {
        "E0": {},
        "fusion": {},
        "background_n8": {},
    }
    covered: list[str] = []
    fusion_top20_covered: list[str] = []
    baseline_index = FEATURE_NAMES.index("baseline_score")
    for row in inputs:
        qid = row["source_query_id"]
        chunk_ids, features = build_online_features(
            **_method_view(row, queries[qid]["query"]),
            feature_version=ENGLISH_FEATURE_VERSION,
        )
        score_vectors = {
            "E0": boosters["E0"].predict(features, num_threads=1),
            "fusion": features[:, baseline_index],
            "background_n8": boosters["background_n8"].predict(features, num_threads=1),
        }
        for name, values in score_vectors.items():
            if len(values) != len(chunk_ids) or not all(math.isfinite(float(x)) for x in values):
                raise ValueError(f"invalid scores: {name}")
            scores[name][qid] = {
                chunk_id: float(value)
                for chunk_id, value in zip(chunk_ids, values, strict=True)
            }
            rankings[name][qid] = [
                chunk_id
                for chunk_id, _ in sorted(
                    zip(chunk_ids, values, strict=True),
                    key=lambda item: (-float(item[1]), item[0]),
                )
            ]
        wanted = {labels[qid]["preferred_chunk_id"], labels[qid]["other_chunk_id"]}
        if wanted <= set(chunk_ids):
            covered.append(qid)
        if wanted <= set(rankings["fusion"][qid][:20]):
            fusion_top20_covered.append(qid)

    official = [qid for qid in covered if labels[qid]["official_label_available"]]
    primary = [qid for qid in official if not labels[qid]["structural_conflict"]]
    sensitivity = official
    populations = {"primary_no_structural_conflict": primary, "including_conflict": sensitivity}
    results: dict[str, dict] = {}
    correctness: dict[str, dict[str, list[bool]]] = {}
    for population_name, population in populations.items():
        results[population_name] = {}
        correctness[population_name] = {}
        for ranker, ranker_rows in rankings.items():
            result, flags = metrics(labels, ranker_rows, scores[ranker], population)
            results[population_name][ranker] = result
            correctness[population_name][ranker] = flags

    output = {
        "experiment": frozen["experiment"],
        "dataset": frozen["dataset"],
        "candidate_inputs_sha256": sha256(SNAPSHOT / "candidates/test/inputs.jsonl"),
        "supervision_sha256": sha256(SNAPSHOT / "prepared/test/supervision.jsonl"),
        "coverage": {
            "all_queries": len(labels),
            "both_designated_in_candidate_union": len(covered),
            "both_designated_in_fusion_top20": len(fusion_top20_covered),
            "official_and_covered": len(official),
            "primary_no_structural_conflict": len(primary),
        },
        "results": results,
        "mcnemar_primary_e0_vs_background_n8": exact_mcnemar(
            correctness["primary_no_structural_conflict"]["E0"],
            correctness["primary_no_structural_conflict"]["background_n8"],
        ),
        "test_tuning_or_retraining": False,
    }
    (RUN / "results.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "coverage": output["coverage"],
                "primary": output["results"]["primary_no_structural_conflict"],
                "mcnemar": output["mcnemar_primary_e0_vs_background_n8"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
