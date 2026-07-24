"""LightGBM LambdaMART cross-validation for three-route fusion."""

from __future__ import annotations

import hashlib
import html
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from linkrag_eval.retrieval.tuning import RouteHit, weighted_score_fuse


ROUTES = ("dense", "sparse", "bm25")
BASELINE_WEIGHTS = {"dense": 0.70, "sparse": 0.15, "bm25": 0.15}
BASELINE_THRESHOLDS = {"dense": 0.30, "sparse": 0.20, "bm25": 0.0}
FEATURE_VERSION = "candidate_difference_v2"
FEATURE_NAMES = [
    "dense_score",
    "sparse_log_score",
    "bm25_log_score",
    "dense_norm",
    "sparse_norm",
    "bm25_norm",
    "dense_rr",
    "sparse_rr",
    "bm25_rr",
    "dense_missing",
    "sparse_missing",
    "bm25_missing",
    "route_count",
    "all_routes",
    "dense_sparse_overlap",
    "dense_bm25_overlap",
    "sparse_bm25_overlap",
    "dense_sparse_rr_gap",
    "dense_bm25_rr_gap",
    "sparse_bm25_rr_gap",
    "dense_top12_margin",
    "sparse_top12_margin",
    "bm25_top12_margin",
    "baseline_score",
    "baseline_rr",
    "query_length",
    "query_has_digit",
    "scenario_short",
    "scenario_exact",
    "scenario_long",
    "scenario_dense",
    "scenario_similar_docs",
    "scenario_multi_constraint",
    "scenario_number_time",
    "scenario_alias",
    "identifier_exact_coverage",
    "number_exact_coverage",
    "negation_overlap_coverage",
    "negation_mismatch",
    "query_bigram_coverage",
    "query_trigram_coverage",
    "condition_coverage",
    "distinctive_query_bigram_coverage",
    "same_doc_candidate_count",
    "same_doc_max_bigram_similarity",
    "content_length_log",
]
_IDENTIFIER_RE = re.compile(
    r"(?i)(?:v(?:ersion)?\s*)?\d+(?:\.\d+){1,3}|"
    r"\d{4}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?|"
    r"[a-z]{1,12}[-_]?[a-z0-9]*\d[a-z0-9._-]*|\d{4,}"
)
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_NEGATIONS = ("尚未", "不得", "禁止", "不能", "不会", "无需", "未", "不", "无", "否", "非")
_CLAUSE_SPLIT_RE = re.compile(r"[，,。；;？?！!]|并且|同时|以及|如果|但是|但|仍然|仍|而且")
_TEXT_CLEAN_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+", re.IGNORECASE)


def _read_rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _route_hits(row: dict[str, Any], source: str) -> list[RouteHit]:
    return [
        RouteHit(
            chunk_id=str(hit["chunk_id"]),
            doc_id=int(hit["doc_id"]),
            dataset_id=int(hit["dataset_id"]),
            score=float(hit["score"]),
            source=source,
        )
        for hit in row["routes"].get(source, [])
    ]


def _normalized(hits: list[RouteHit], source: str) -> dict[str, float]:
    if not hits:
        return {}
    transformed = [
        hit.score if source == "dense" else math.log1p(max(0.0, hit.score)) for hit in hits
    ]
    low, high = min(transformed), max(transformed)
    if high == low:
        return {hit.chunk_id: 1.0 for hit in hits}
    return {hit.chunk_id: (score - low) / (high - low) for hit, score in zip(hits, transformed)}


def _baseline_hits(route_hits: dict[str, list[RouteHit]]) -> dict[str, list[RouteHit]]:
    return {
        source: [hit for hit in hits if hit.score >= BASELINE_THRESHOLDS[source]]
        for source, hits in route_hits.items()
    }


def _load_candidate_contents(path: Path | None) -> dict[str, str] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    contents = (
        payload.get("contents") if isinstance(payload, dict) and "contents" in payload else payload
    )
    if not isinstance(contents, dict):
        raise ValueError(f"candidate content sidecar must be a JSON object: {path}")
    return {
        str(chunk_id): str(content)
        for chunk_id, content in contents.items()
        if isinstance(content, str) and content.strip()
    }


def _normalized_text(value: str) -> str:
    return _TEXT_CLEAN_RE.sub("", value).lower()


def _ngrams(value: str, size: int) -> set[str]:
    text = _normalized_text(value)
    return {text[index : index + size] for index in range(max(0, len(text) - size + 1))}


def _coverage(needles: set[str], content: str) -> float:
    if not needles:
        return 0.0
    lowered = content.lower()
    return sum(needle.lower() in lowered for needle in needles) / len(needles)


def _condition_coverage(query: str, content: str) -> float:
    clauses = [part.strip() for part in _CLAUSE_SPLIT_RE.split(query) if len(part.strip()) >= 2]
    if len(clauses) <= 1:
        return 0.0
    content_bigrams = _ngrams(content, 2)
    matched = 0
    for clause in clauses:
        grams = _ngrams(clause, 2)
        if grams and len(grams.intersection(content_bigrams)) / len(grams) >= 0.5:
            matched += 1
    return matched / len(clauses)


def _top12_margin(hits: list[RouteHit], source: str) -> float:
    if len(hits) < 2:
        return 0.0
    values = [
        hit.score if source == "dense" else math.log1p(max(0.0, hit.score)) for hit in hits[:2]
    ]
    return max(0.0, values[0] - values[1]) / max(abs(values[0]), 1e-9)


def _candidate_features(
    row: dict[str, Any],
    candidate_contents: dict[str, str] | None = None,
) -> tuple[list[str], np.ndarray, np.ndarray]:
    route_hits = {source: _route_hits(row, source) for source in ROUTES}
    by_source = {source: {hit.chunk_id: hit for hit in hits} for source, hits in route_hits.items()}
    rank_by_source = {
        source: {hit.chunk_id: rank for rank, hit in enumerate(hits, 1)}
        for source, hits in route_hits.items()
    }
    norms = {source: _normalized(hits, source) for source, hits in route_hits.items()}
    baseline = weighted_score_fuse(
        _baseline_hits(route_hits),
        final_top_k=sum(len(hits) for hits in route_hits.values()),
        weights=BASELINE_WEIGHTS,
    )
    baseline_by_id = {hit.chunk_id: hit for hit in baseline}
    chunk_ids = sorted(
        {hit.chunk_id for hits in route_hits.values() for hit in hits},
        key=lambda chunk_id: (
            baseline_by_id.get(chunk_id).rank if chunk_id in baseline_by_id else 10**9,
            chunk_id,
        ),
    )
    scenario = str(row.get("scenario") or "")
    query = str(row["query"])
    expected = set(str(value) for value in row["expected_chunk_ids"])
    if candidate_contents is None:
        raise ValueError("candidate_difference_v2 requires --candidate-contents")
    missing_contents = [chunk_id for chunk_id in chunk_ids if chunk_id not in candidate_contents]
    if missing_contents:
        raise ValueError(
            f"missing candidate contents for sample {row['sample_id']}: "
            f"{missing_contents[:3]} ({len(missing_contents)} total)"
        )

    query_identifiers = {match.group(0).lower() for match in _IDENTIFIER_RE.finditer(query)}
    query_numbers = {match.group(0).lower() for match in _NUMBER_RE.finditer(query)}
    query_negations = {token for token in _NEGATIONS if token in query}
    query_bigrams = _ngrams(query, 2)
    query_trigrams = _ngrams(query, 3)
    candidate_bigrams = {
        chunk_id: _ngrams(candidate_contents[chunk_id], 2) for chunk_id in chunk_ids
    }
    bigram_frequency = Counter(gram for grams in candidate_bigrams.values() for gram in grams)
    distinctive_limit = max(1, math.ceil(len(chunk_ids) * 0.10))
    doc_by_chunk: dict[str, int] = {}
    for source in ROUTES:
        for hit in route_hits[source]:
            doc_by_chunk.setdefault(hit.chunk_id, hit.doc_id)
    chunks_by_doc: dict[int, list[str]] = defaultdict(list)
    for chunk_id in chunk_ids:
        chunks_by_doc[doc_by_chunk[chunk_id]].append(chunk_id)
    top12_margins = {source: _top12_margin(route_hits[source], source) for source in ROUTES}
    features: list[list[float]] = []
    labels: list[int] = []
    for chunk_id in chunk_ids:
        hits = {source: by_source[source].get(chunk_id) for source in ROUTES}
        ranks = {source: rank_by_source[source].get(chunk_id, 0) for source in ROUTES}
        reciprocal_ranks = {
            source: 1.0 / ranks[source] if ranks[source] else 0.0 for source in ROUTES
        }
        baseline_hit = baseline_by_id.get(chunk_id)
        content = candidate_contents[chunk_id]
        content_negations = {token for token in _NEGATIONS if token in content}
        same_doc_chunks = chunks_by_doc[doc_by_chunk[chunk_id]]
        same_doc_similarities = []
        for peer_id in same_doc_chunks:
            if peer_id == chunk_id:
                continue
            union = candidate_bigrams[chunk_id].union(candidate_bigrams[peer_id])
            same_doc_similarities.append(
                len(candidate_bigrams[chunk_id].intersection(candidate_bigrams[peer_id]))
                / len(union)
                if union
                else 0.0
            )
        distinctive_query_grams = {
            gram
            for gram in query_bigrams.intersection(candidate_bigrams[chunk_id])
            if bigram_frequency[gram] <= distinctive_limit
        }
        values = [
            hits["dense"].score if hits["dense"] else 0.0,
            math.log1p(max(0.0, hits["sparse"].score)) if hits["sparse"] else 0.0,
            math.log1p(max(0.0, hits["bm25"].score)) if hits["bm25"] else 0.0,
            norms["dense"].get(chunk_id, 0.0),
            norms["sparse"].get(chunk_id, 0.0),
            norms["bm25"].get(chunk_id, 0.0),
            reciprocal_ranks["dense"],
            reciprocal_ranks["sparse"],
            reciprocal_ranks["bm25"],
            0.0 if hits["dense"] else 1.0,
            0.0 if hits["sparse"] else 1.0,
            0.0 if hits["bm25"] else 1.0,
            float(sum(hit is not None for hit in hits.values())),
            float(all(hit is not None for hit in hits.values())),
            float(hits["dense"] is not None and hits["sparse"] is not None),
            float(hits["dense"] is not None and hits["bm25"] is not None),
            float(hits["sparse"] is not None and hits["bm25"] is not None),
            abs(reciprocal_ranks["dense"] - reciprocal_ranks["sparse"]),
            abs(reciprocal_ranks["dense"] - reciprocal_ranks["bm25"]),
            abs(reciprocal_ranks["sparse"] - reciprocal_ranks["bm25"]),
            top12_margins["dense"],
            top12_margins["sparse"],
            top12_margins["bm25"],
            baseline_hit.score if baseline_hit else 0.0,
            1.0 / (baseline_hit.rank + 1) if baseline_hit else 0.0,
            float(len(query)),
            float(any(char.isdigit() for char in query)),
            float(scenario == "short_keyword"),
            float(scenario == "exact_identifier"),
            float(scenario == "long_sparse"),
            float(scenario == "dense_paraphrase"),
            float(scenario == "similar_docs"),
            float(scenario == "multi_constraint"),
            float(scenario == "number_time"),
            float(scenario == "alias"),
            _coverage(query_identifiers, content),
            _coverage(query_numbers, content),
            (
                len(query_negations.intersection(content_negations)) / len(query_negations)
                if query_negations
                else 0.0
            ),
            float(
                bool(query_negations) != bool(content_negations)
                or (bool(query_negations) and not query_negations.intersection(content_negations))
            ),
            (
                len(query_bigrams.intersection(candidate_bigrams[chunk_id])) / len(query_bigrams)
                if query_bigrams
                else 0.0
            ),
            (
                len(query_trigrams.intersection(_ngrams(content, 3))) / len(query_trigrams)
                if query_trigrams
                else 0.0
            ),
            _condition_coverage(query, content),
            len(distinctive_query_grams) / len(query_bigrams) if query_bigrams else 0.0,
            float(len(same_doc_chunks) - 1),
            max(same_doc_similarities, default=0.0),
            math.log1p(len(content)),
        ]
        features.append(values)
        labels.append(1 if chunk_id in expected else 0)
    return chunk_ids, np.asarray(features, dtype=np.float32), np.asarray(labels, dtype=np.int32)


def _fold(row: dict[str, Any], folds: int) -> int:
    doc_ids = row.get("expected_doc_ids") or []
    value = ",".join(str(item) for item in doc_ids) or str(row["sample_id"])
    return int(hashlib.sha256(value.encode()).hexdigest()[:8], 16) % folds


def _metrics(ranked: list[str], expected: set[str], k: int = 10) -> tuple[float, float]:
    top = ranked[:k]
    first = next((index for index, chunk_id in enumerate(top, 1) if chunk_id in expected), None)
    return (1.0 if first else 0.0, 1.0 / first if first else 0.0)


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    low, high = min(values), max(values)
    if high == low:
        return [1.0] * len(values)
    return [(value - low) / (high - low) for value in values]


def rank_with_hybrid_protection(
    chunk_ids: list[str],
    ltr_scores: list[float],
    baseline_scores: list[float],
    baseline_reciprocal_ranks: list[float],
    *,
    blend_alpha: float,
    protect_baseline_top_k: int,
) -> list[str]:
    """Blend normalized LTR/Hybrid scores and optionally reserve Hybrid TopK."""
    if not 0.0 <= blend_alpha <= 1.0:
        raise ValueError("blend_alpha must be in [0, 1]")
    if protect_baseline_top_k < 0:
        raise ValueError("protect_baseline_top_k must be >= 0")
    if not (
        len(chunk_ids) == len(ltr_scores) == len(baseline_scores) == len(baseline_reciprocal_ranks)
    ):
        raise ValueError("candidate postprocessing arrays must have equal length")

    ltr_normalized = _minmax([float(value) for value in ltr_scores])
    blended = {
        chunk_id: blend_alpha * ltr_score + (1.0 - blend_alpha) * float(baseline_score)
        for chunk_id, ltr_score, baseline_score in zip(chunk_ids, ltr_normalized, baseline_scores)
    }
    baseline_order = [
        chunk_id
        for chunk_id, reciprocal_rank in sorted(
            zip(chunk_ids, baseline_reciprocal_ranks),
            key=lambda item: (-float(item[1]), item[0]),
        )
        if reciprocal_rank > 0
    ]
    protected = baseline_order[:protect_baseline_top_k]
    protected_set = set(protected)
    remaining = sorted(
        (chunk_id for chunk_id in chunk_ids if chunk_id not in protected_set),
        key=lambda chunk_id: (-blended[chunk_id], chunk_id),
    )
    return [*protected, *remaining]


def tune_hybrid_protection(
    predictions: list[dict[str, Any]],
    *,
    blend_alphas: tuple[float, ...] = (0.25, 0.5, 0.75, 1.0),
    protect_top_ks: tuple[int, ...] = (0, 1, 2, 3, 4),
) -> dict[str, Any]:
    """Select postprocessing only from out-of-fold Tune predictions."""
    results: list[dict[str, Any]] = []
    for alpha in blend_alphas:
        for protect_top_k in protect_top_ks:
            hit_sum = mrr_sum = 0.0
            transitions: Counter[str] = Counter()
            for prediction in predictions:
                ranked = rank_with_hybrid_protection(
                    prediction["candidate_chunk_ids"],
                    prediction["candidate_ltr_scores"],
                    prediction["candidate_baseline_scores"],
                    prediction["candidate_baseline_rr"],
                    blend_alpha=alpha,
                    protect_baseline_top_k=protect_top_k,
                )
                hit, mrr = _metrics(ranked, set(prediction["expected_chunk_ids"]))
                baseline_hit = float(prediction["baseline_hit_at_10"])
                transition = (
                    "gained"
                    if not baseline_hit and hit
                    else "lost"
                    if baseline_hit and not hit
                    else "kept_hit"
                    if baseline_hit
                    else "kept_miss"
                )
                transitions[transition] += 1
                hit_sum += hit
                mrr_sum += mrr
            n = len(predictions)
            results.append(
                {
                    "blend_alpha": alpha,
                    "protect_baseline_top_k": protect_top_k,
                    "hit_at_10": hit_sum / n,
                    "mrr": mrr_sum / n,
                    "delta_hit_at_10": hit_sum / n
                    - sum(float(row["baseline_hit_at_10"]) for row in predictions) / n,
                    "delta_mrr": mrr_sum / n
                    - sum(float(row["baseline_mrr"]) for row in predictions) / n,
                    "transitions": dict(transitions),
                }
            )
    results.sort(
        key=lambda row: (
            -row["hit_at_10"],
            -row["mrr"],
            row["transitions"].get("lost", 0),
            row["protect_baseline_top_k"],
        )
    )
    return {"best": results[0], "results": results}


def _matrix(
    rows: list[dict[str, Any]],
    prepared: dict[str, tuple[list[str], np.ndarray, np.ndarray]],
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    arrays = [prepared[row["sample_id"]] for row in rows]
    return (
        np.concatenate([item[1] for item in arrays]),
        np.concatenate([item[2] for item in arrays]),
        [len(item[0]) for item in arrays],
    )


def run_ltr_cross_validation(
    cache_path: Path,
    *,
    out_dir: Path,
    candidate_contents_path: Path | None = None,
    folds: int = 5,
    seed: int = 20260716,
) -> dict[str, Any]:
    try:
        from lightgbm import LGBMRanker, early_stopping, log_evaluation
    except ImportError as exc:
        raise RuntimeError("LTR实验需要安装可选依赖: pip install -e '.[ltr]'") from exc

    rows = [row for row in _read_rows(cache_path) if not row.get("failed_sources")]
    if len(rows) < folds * 10:
        raise ValueError(f"clean LTR samples too few:{len(rows)}")
    candidate_contents = _load_candidate_contents(candidate_contents_path)
    feature_names = FEATURE_NAMES
    prepared = {row["sample_id"]: _candidate_features(row, candidate_contents) for row in rows}
    fold_reports: list[dict[str, Any]] = []
    all_predictions: list[dict[str, Any]] = []
    feature_importance = np.zeros(len(feature_names), dtype=np.float64)

    for fold_index in range(folds):
        train_rows = [row for row in rows if _fold(row, folds) != fold_index]
        valid_rows = [row for row in rows if _fold(row, folds) == fold_index]

        train_x, train_y, train_groups = _matrix(train_rows, prepared)
        valid_x, valid_y, valid_groups = _matrix(valid_rows, prepared)
        model = LGBMRanker(
            objective="lambdarank",
            metric="ndcg",
            n_estimators=300,
            learning_rate=0.03,
            num_leaves=15,
            max_depth=4,
            min_child_samples=20,
            feature_fraction=0.8,
            reg_lambda=1.0,
            random_state=seed + fold_index,
            verbosity=-1,
        )
        model.fit(
            train_x,
            train_y,
            group=train_groups,
            eval_set=[(valid_x, valid_y)],
            eval_group=[valid_groups],
            eval_at=[10],
            callbacks=[early_stopping(30, verbose=False), log_evaluation(0)],
        )
        feature_importance += model.feature_importances_

        baseline_hit = baseline_mrr = ltr_hit = ltr_mrr = 0.0
        scenario_values: dict[str, list[tuple[float, float, float, float]]] = defaultdict(list)
        valid_scores = model.booster_.predict(
            valid_x,
            num_iteration=model.best_iteration_,
        )
        valid_offset = 0
        for row in valid_rows:
            chunk_ids, features, _labels = prepared[row["sample_id"]]
            scores = valid_scores[valid_offset : valid_offset + len(features)]
            valid_offset += len(features)
            ltr_ranked = [
                chunk_id
                for chunk_id, _score in sorted(
                    zip(chunk_ids, scores), key=lambda item: (-float(item[1]), item[0])
                )
            ]
            route_hits = {source: _route_hits(row, source) for source in ROUTES}
            baseline_ranked = [
                hit.chunk_id
                for hit in weighted_score_fuse(
                    _baseline_hits(route_hits),
                    final_top_k=10,
                    weights=BASELINE_WEIGHTS,
                )
            ]
            expected = set(str(value) for value in row["expected_chunk_ids"])
            bh, bm = _metrics(baseline_ranked, expected)
            lh, lm = _metrics(ltr_ranked, expected)
            baseline_hit += bh
            baseline_mrr += bm
            ltr_hit += lh
            ltr_mrr += lm
            scenario_values[str(row["scenario"])].append((bh, bm, lh, lm))
            all_predictions.append(
                {
                    "fold": fold_index,
                    "sample_id": row["sample_id"],
                    "scenario": row["scenario"],
                    "baseline_hit_at_10": bh,
                    "baseline_mrr": bm,
                    "ltr_hit_at_10": lh,
                    "ltr_mrr": lm,
                    "candidate_union_hit": float(bool(expected.intersection(chunk_ids))),
                    "expected_chunk_ids": sorted(expected),
                    "candidate_chunk_ids": chunk_ids,
                    "candidate_ltr_scores": [float(value) for value in scores],
                    "candidate_baseline_scores": [
                        float(value) for value in features[:, feature_names.index("baseline_score")]
                    ],
                    "candidate_baseline_rr": [
                        float(value) for value in features[:, feature_names.index("baseline_rr")]
                    ],
                }
            )
        n = len(valid_rows)
        fold_reports.append(
            {
                "fold": fold_index,
                "train_queries": len(train_rows),
                "valid_queries": n,
                "best_iteration": model.best_iteration_,
                "baseline_hit_at_10": baseline_hit / n,
                "baseline_mrr": baseline_mrr / n,
                "ltr_hit_at_10": ltr_hit / n,
                "ltr_mrr": ltr_mrr / n,
                "delta_hit_at_10": (ltr_hit - baseline_hit) / n,
                "delta_mrr": (ltr_mrr - baseline_mrr) / n,
                "scenarios": {
                    scenario: {
                        "n": len(values),
                        "baseline_hit_at_10": sum(value[0] for value in values) / len(values),
                        "ltr_hit_at_10": sum(value[2] for value in values) / len(values),
                    }
                    for scenario, values in sorted(scenario_values.items())
                },
            }
        )

    n_all = len(all_predictions)
    overall = {
        "n": n_all,
        "baseline_hit_at_10": sum(row["baseline_hit_at_10"] for row in all_predictions) / n_all,
        "baseline_mrr": sum(row["baseline_mrr"] for row in all_predictions) / n_all,
        "ltr_hit_at_10": sum(row["ltr_hit_at_10"] for row in all_predictions) / n_all,
        "ltr_mrr": sum(row["ltr_mrr"] for row in all_predictions) / n_all,
    }
    overall["delta_hit_at_10"] = overall["ltr_hit_at_10"] - overall["baseline_hit_at_10"]
    overall["delta_mrr"] = overall["ltr_mrr"] - overall["baseline_mrr"]
    overall["candidate_union_coverage"] = (
        sum(row["candidate_union_hit"] for row in all_predictions) / n_all
    )
    scenario_predictions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for prediction in all_predictions:
        scenario_predictions[str(prediction["scenario"])].append(prediction)
    scenario_overall = {
        scenario: {
            "n": len(values),
            "baseline_hit_at_10": sum(row["baseline_hit_at_10"] for row in values) / len(values),
            "ltr_hit_at_10": sum(row["ltr_hit_at_10"] for row in values) / len(values),
            "delta_hit_at_10": sum(
                row["ltr_hit_at_10"] - row["baseline_hit_at_10"] for row in values
            )
            / len(values),
            "candidate_union_coverage": sum(row["candidate_union_hit"] for row in values)
            / len(values),
        }
        for scenario, values in sorted(scenario_predictions.items())
    }
    transitions = Counter(
        "gained"
        if not row["baseline_hit_at_10"] and row["ltr_hit_at_10"]
        else "lost"
        if row["baseline_hit_at_10"] and not row["ltr_hit_at_10"]
        else "kept_hit"
        if row["baseline_hit_at_10"]
        else "kept_miss"
        for row in all_predictions
    )
    importance = [
        {"feature": name, "importance": float(value)}
        for name, value in sorted(
            zip(feature_names, feature_importance),
            key=lambda item: -item[1],
        )
    ]
    report = {
        "cache": str(cache_path),
        "feature_version": FEATURE_VERSION,
        "candidate_contents": str(candidate_contents_path),
        "folds": folds,
        "clean_samples": len(rows),
        "baseline_thresholds": BASELINE_THRESHOLDS,
        "overall": overall,
        "scenario_overall": scenario_overall,
        "transitions": dict(transitions),
        "fold_reports": fold_reports,
        "feature_importance": importance,
        "predictions": all_predictions,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ltr_cross_validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "ltr_cross_validation.html").write_text(
        _render_html(report),
        encoding="utf-8",
    )
    return report


def run_ltr_external_evaluation(
    train_cache_path: Path,
    test_cache_path: Path,
    *,
    out_dir: Path,
    candidate_contents_path: Path | None = None,
    n_estimators: int = 24,
    seed: int = 20260716,
    historical_baseline_hit_at_10: float | None = None,
    blend_alpha: float = 1.0,
    protect_baseline_top_k: int = 0,
) -> dict[str, Any]:
    """Train on one frozen cache and evaluate once on a separate query set."""
    try:
        from lightgbm import LGBMRanker
    except ImportError as exc:
        raise RuntimeError("LTR实验需要安装可选依赖: pip install -e '.[ltr]'") from exc

    train_rows = [row for row in _read_rows(train_cache_path) if not row.get("failed_sources")]
    test_rows = [row for row in _read_rows(test_cache_path) if not row.get("failed_sources")]
    if not train_rows or not test_rows:
        raise ValueError("train/test LTR cache must contain clean rows")
    train_ids = {str(row["sample_id"]) for row in train_rows}
    test_ids = {str(row["sample_id"]) for row in test_rows}
    overlap = sorted(train_ids.intersection(test_ids))
    if overlap:
        raise ValueError(f"train/test sample overlap: {overlap[:5]}")
    train_expected_chunks = {
        str(chunk_id) for row in train_rows for chunk_id in row["expected_chunk_ids"]
    }
    evidence_overlap_sample_ids = sorted(
        str(row["sample_id"])
        for row in test_rows
        if train_expected_chunks.intersection(str(value) for value in row["expected_chunk_ids"])
    )

    candidate_contents = _load_candidate_contents(candidate_contents_path)
    feature_names = FEATURE_NAMES
    train_prepared = {
        row["sample_id"]: _candidate_features(row, candidate_contents) for row in train_rows
    }
    test_prepared = {
        row["sample_id"]: _candidate_features(row, candidate_contents) for row in test_rows
    }
    train_x, train_y, train_groups = _matrix(train_rows, train_prepared)
    model = LGBMRanker(
        objective="lambdarank",
        metric="ndcg",
        n_estimators=n_estimators,
        learning_rate=0.03,
        num_leaves=15,
        max_depth=4,
        min_child_samples=20,
        feature_fraction=0.8,
        reg_lambda=1.0,
        random_state=seed,
        verbosity=-1,
    )
    model.fit(train_x, train_y, group=train_groups)

    predictions: list[dict[str, Any]] = []
    for row in test_rows:
        chunk_ids, features, _labels = test_prepared[row["sample_id"]]
        scores = model.booster_.predict(features, num_iteration=n_estimators)
        ltr_ranked = rank_with_hybrid_protection(
            chunk_ids,
            [float(value) for value in scores],
            [float(value) for value in features[:, feature_names.index("baseline_score")]],
            [float(value) for value in features[:, feature_names.index("baseline_rr")]],
            blend_alpha=blend_alpha,
            protect_baseline_top_k=protect_baseline_top_k,
        )
        route_hits = {source: _route_hits(row, source) for source in ROUTES}
        baseline_ranked = [
            hit.chunk_id
            for hit in weighted_score_fuse(
                _baseline_hits(route_hits),
                final_top_k=10,
                weights=BASELINE_WEIGHTS,
            )
        ]
        expected = set(str(value) for value in row["expected_chunk_ids"])
        baseline_hit, baseline_mrr = _metrics(baseline_ranked, expected)
        ltr_hit, ltr_mrr = _metrics(ltr_ranked, expected)
        predictions.append(
            {
                "sample_id": row["sample_id"],
                "scenario": row["scenario"],
                "baseline_hit_at_10": baseline_hit,
                "baseline_mrr": baseline_mrr,
                "ltr_hit_at_10": ltr_hit,
                "ltr_mrr": ltr_mrr,
                "candidate_union_hit": float(bool(expected.intersection(chunk_ids))),
                "expected_chunk_ids": sorted(expected),
                "candidate_chunk_ids": chunk_ids,
                "candidate_ltr_scores": [float(value) for value in scores],
                "candidate_baseline_scores": [
                    float(value) for value in features[:, feature_names.index("baseline_score")]
                ],
                "candidate_baseline_rr": [
                    float(value) for value in features[:, feature_names.index("baseline_rr")]
                ],
            }
        )

    n = len(predictions)
    overall = {
        "n": n,
        "baseline_hit_at_10": sum(row["baseline_hit_at_10"] for row in predictions) / n,
        "baseline_mrr": sum(row["baseline_mrr"] for row in predictions) / n,
        "ltr_hit_at_10": sum(row["ltr_hit_at_10"] for row in predictions) / n,
        "ltr_mrr": sum(row["ltr_mrr"] for row in predictions) / n,
        "candidate_union_coverage": sum(row["candidate_union_hit"] for row in predictions) / n,
    }
    overall["delta_hit_at_10"] = overall["ltr_hit_at_10"] - overall["baseline_hit_at_10"]
    overall["delta_mrr"] = overall["ltr_mrr"] - overall["baseline_mrr"]
    strict_predictions = [
        row for row in predictions if row["sample_id"] not in evidence_overlap_sample_ids
    ]
    strict_n = len(strict_predictions)
    strict_no_evidence_overlap = {
        "n": strict_n,
        "baseline_hit_at_10": sum(row["baseline_hit_at_10"] for row in strict_predictions)
        / strict_n,
        "baseline_mrr": sum(row["baseline_mrr"] for row in strict_predictions) / strict_n,
        "ltr_hit_at_10": sum(row["ltr_hit_at_10"] for row in strict_predictions) / strict_n,
        "ltr_mrr": sum(row["ltr_mrr"] for row in strict_predictions) / strict_n,
        "candidate_union_coverage": sum(row["candidate_union_hit"] for row in strict_predictions)
        / strict_n,
    }
    strict_no_evidence_overlap["delta_hit_at_10"] = (
        strict_no_evidence_overlap["ltr_hit_at_10"]
        - strict_no_evidence_overlap["baseline_hit_at_10"]
    )
    strict_no_evidence_overlap["delta_mrr"] = (
        strict_no_evidence_overlap["ltr_mrr"] - strict_no_evidence_overlap["baseline_mrr"]
    )
    scenario_predictions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for prediction in predictions:
        scenario_predictions[str(prediction["scenario"])].append(prediction)
    scenario_overall = {
        scenario: {
            "n": len(values),
            "baseline_hit_at_10": sum(row["baseline_hit_at_10"] for row in values) / len(values),
            "ltr_hit_at_10": sum(row["ltr_hit_at_10"] for row in values) / len(values),
            "delta_hit_at_10": sum(
                row["ltr_hit_at_10"] - row["baseline_hit_at_10"] for row in values
            )
            / len(values),
            "candidate_union_coverage": sum(row["candidate_union_hit"] for row in values)
            / len(values),
        }
        for scenario, values in sorted(scenario_predictions.items())
    }
    transitions = Counter(
        "gained"
        if not row["baseline_hit_at_10"] and row["ltr_hit_at_10"]
        else "lost"
        if row["baseline_hit_at_10"] and not row["ltr_hit_at_10"]
        else "kept_hit"
        if row["baseline_hit_at_10"]
        else "kept_miss"
        for row in predictions
    )
    importance = [
        {"feature": name, "importance": float(value)}
        for name, value in sorted(
            zip(feature_names, model.feature_importances_),
            key=lambda item: -item[1],
        )
    ]
    report = {
        "train_cache": str(train_cache_path),
        "test_cache": str(test_cache_path),
        "feature_version": FEATURE_VERSION,
        "candidate_contents": str(candidate_contents_path),
        "train_samples": len(train_rows),
        "test_samples": len(test_rows),
        "n_estimators": n_estimators,
        "seed": seed,
        "historical_baseline_hit_at_10": historical_baseline_hit_at_10,
        "baseline_thresholds": BASELINE_THRESHOLDS,
        "baseline_weights": BASELINE_WEIGHTS,
        "postprocessing": {
            "blend_alpha": blend_alpha,
            "protect_baseline_top_k": protect_baseline_top_k,
        },
        "overall": overall,
        "evidence_overlap_test_samples": len(evidence_overlap_sample_ids),
        "evidence_overlap_sample_ids": evidence_overlap_sample_ids,
        "strict_no_evidence_overlap": strict_no_evidence_overlap,
        "scenario_overall": scenario_overall,
        "transitions": dict(transitions),
        "feature_importance": importance,
        "predictions": predictions,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ltr_external_evaluation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "ltr_external_evaluation.html").write_text(
        _render_external_html(report),
        encoding="utf-8",
    )
    return report


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _render_html(report: dict[str, Any]) -> str:
    overall = report["overall"]
    fold_rows = "".join(
        "<tr>"
        f"<td>{fold['fold'] + 1}</td><td>{fold['valid_queries']}</td>"
        f"<td>{_pct(fold['baseline_hit_at_10'])}</td>"
        f"<td>{_pct(fold['ltr_hit_at_10'])}</td>"
        f"<td>{_pct(fold['delta_hit_at_10'])}</td>"
        f"<td>{_pct(fold['baseline_mrr'])}</td>"
        f"<td>{_pct(fold['ltr_mrr'])}</td></tr>"
        for fold in report["fold_reports"]
    )
    importance_rows = "".join(
        f"<tr><td>{html.escape(row['feature'])}</td><td>{row['importance']:.0f}</td></tr>"
        for row in report["feature_importance"][:15]
    )
    scenario_labels = {
        "short_keyword": "短关键词",
        "exact_identifier": "编号/日期/版本号",
        "long_sparse": "长描述/多条件",
        "dense_paraphrase": "自然语言改写",
    }
    scenario_rows = "".join(
        "<tr>"
        f"<td>{scenario_labels.get(scenario, html.escape(scenario))}</td>"
        f"<td>{values['n']}</td>"
        f"<td>{_pct(values['baseline_hit_at_10'])}</td>"
        f"<td>{_pct(values['ltr_hit_at_10'])}</td>"
        f"<td>{_pct(values['delta_hit_at_10'])}</td>"
        f"<td>{_pct(values['candidate_union_coverage'])}</td></tr>"
        for scenario, values in report["scenario_overall"].items()
    )
    improved_folds = sum(fold["delta_hit_at_10"] > 0 for fold in report["fold_reports"])
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>LTR Fusion CV</title>
<style>body{{font:15px/1.6 system-ui;margin:0;background:#f6f8fa;color:#17212b}}
main{{max-width:1100px;margin:24px auto;background:#fff;padding:30px;border:1px solid #d0d7de}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}.card{{border:1px solid #d0d7de;padding:12px}}
strong{{display:block;font-size:24px}}table{{width:100%;border-collapse:collapse;margin:14px 0}}
th,td{{border:1px solid #d0d7de;padding:8px;text-align:left}}th{{background:#eef3f7}}
@media(max-width:760px){{main{{margin:0;border:0}}.grid{{grid-template-columns:1fr}}}}</style></head>
<body><main><h1>学习型融合 5折交叉验证</h1>
<p>仅使用 balanced tune；按证据文档分Fold，不使用已揭盲的Blind选参。</p>
<div class="grid"><div class="card">Baseline Hit@10<strong>{_pct(overall["baseline_hit_at_10"])}</strong></div>
<div class="card">LTR Hit@10<strong>{_pct(overall["ltr_hit_at_10"])}</strong></div>
<div class="card">净变化<strong>{_pct(overall["delta_hit_at_10"])}</strong></div></div>
<p>MRR：{_pct(overall["baseline_mrr"])} → {_pct(overall["ltr_mrr"])}；
新增命中 {report["transitions"].get("gained", 0)}，丢失命中 {report["transitions"].get("lost", 0)}。</p>
<p>三路完整候选池覆盖率为 {_pct(overall["candidate_union_coverage"])}；
{improved_folds}/{report["folds"]} 个 Fold 的 Hit@10 均高于固定权重 Hybrid。</p>
<h2>分场景结果</h2><table><thead><tr><th>场景</th><th>n</th><th>Baseline Hit</th>
<th>LTR Hit</th><th>变化</th><th>候选池覆盖率</th></tr></thead><tbody>{scenario_rows}</tbody></table>
<h2>各Fold</h2><table><thead><tr><th>Fold</th><th>n</th><th>Baseline Hit</th>
<th>LTR Hit</th><th>变化</th><th>Baseline MRR</th><th>LTR MRR</th></tr></thead>
<tbody>{fold_rows}</tbody></table><h2>特征重要性</h2><table><thead><tr><th>特征</th>
<th>重要性</th></tr></thead><tbody>{importance_rows}</tbody></table>
<h2>结论边界</h2>
<p>该结果证明学习型融合在 Tune 的样本外预测中具有提升价值，但不能替代新 Blind。
当前 Blind 已被查看，不应用于继续选参；生产启用前需冻结模型并在未曝光 Blind v2 上只运行一次。</p>
</main></body></html>"""


def _render_external_html(report: dict[str, Any]) -> str:
    overall = report["overall"]
    strict = report["strict_no_evidence_overlap"]
    scenario_rows = "".join(
        "<tr>"
        f"<td>{html.escape(scenario)}</td><td>{values['n']}</td>"
        f"<td>{_pct(values['baseline_hit_at_10'])}</td>"
        f"<td>{_pct(values['ltr_hit_at_10'])}</td>"
        f"<td>{_pct(values['delta_hit_at_10'])}</td>"
        f"<td>{_pct(values['candidate_union_coverage'])}</td></tr>"
        for scenario, values in report["scenario_overall"].items()
    )
    historical = report.get("historical_baseline_hit_at_10")
    historical_text = (
        f"<p>该数据集历史固定 Hybrid Recall@10：{_pct(historical)}。"
        "历史运行与本实验的候选深度和融合参数不同，仅作为背景参照。</p>"
        if historical is not None
        else ""
    )
    verdict = "提升" if overall["delta_hit_at_10"] > 0 else "下降"
    postprocessing = report.get("postprocessing") or {}
    postprocessing_text = (
        "<p><b>冻结后处理：</b>LTR 分数权重 "
        f"{float(postprocessing.get('blend_alpha', 1.0)):.2f}，保护 Hybrid Top"
        f"{int(postprocessing.get('protect_baseline_top_k', 0))}。</p>"
    )
    mrr_note = (
        "<p><b>排序质量提醒：</b>虽然 Recall@10 提升，但 MRR@10 下降，说明部分正确 "
        "Chunk 进入了 Top10，却被排在更靠后的位置。当前模型不能直接生产替换。</p>"
        if overall["delta_mrr"] < 0
        else ""
    )
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LambdaMART 跨 Query 集泛化测试</title>
<style>body{{font:15px/1.65 system-ui;margin:0;background:#f6f8fa;color:#17212b}}
main{{max-width:1080px;margin:24px auto;background:#fff;padding:30px;border:1px solid #d0d7de}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}
.card{{border:1px solid #d0d7de;padding:12px}}strong{{display:block;font-size:24px}}
table{{width:100%;border-collapse:collapse;margin:14px 0}}
th,td{{border:1px solid #d0d7de;padding:8px;text-align:left}}th{{background:#eef3f7}}
@media(max-width:760px){{main{{margin:0;border:0}}.grid{{grid-template-columns:1fr}}}}</style>
</head><body><main><h1>LambdaMART 跨 Query 集泛化测试</h1>
<p>使用 balanced Tune {report["train_samples"]} 条训练，在另一套未扩写 realistic Query
{report["test_samples"]} 条上一次性评测；测试集不参与训练和轮数选择。</p>
<div class="grid"><div class="card">同口径 Hybrid Recall@10
<strong>{_pct(overall["baseline_hit_at_10"])}</strong></div>
<div class="card">LambdaMART Recall@10<strong>{_pct(overall["ltr_hit_at_10"])}</strong></div>
<div class="card">{verdict}<strong>{_pct(overall["delta_hit_at_10"])}</strong></div></div>
{historical_text}
{postprocessing_text}
<p>MRR@10：{_pct(overall["baseline_mrr"])} → {_pct(overall["ltr_mrr"])}；
候选池覆盖率：{_pct(overall["candidate_union_coverage"])}；
新增命中 {report["transitions"].get("gained", 0)}，丢失命中
{report["transitions"].get("lost", 0)}。</p>
{mrr_note}
<h2>排除证据重叠后的严格结果</h2>
<p>测试集中有 {report["evidence_overlap_test_samples"]} 条 Query 与训练集共享正确 Chunk。
排除后剩余 {strict["n"]} 条：Hybrid {_pct(strict["baseline_hit_at_10"])}，
LambdaMART {_pct(strict["ltr_hit_at_10"])}，变化 {_pct(strict["delta_hit_at_10"])}；
MRR {_pct(strict["baseline_mrr"])} → {_pct(strict["ltr_mrr"])}。</p>
<h2>分类型结果</h2><table><thead><tr><th>类型</th><th>n</th>
<th>Hybrid</th><th>LambdaMART</th><th>变化</th><th>候选覆盖率</th></tr></thead>
<tbody>{scenario_rows}</tbody></table>
<h2>实验边界</h2><p>该测试用于判断跨 Query 分布泛化，不用于继续调参。
如果结果下降，应保留报告并分析训练分布、场景特征和保护策略，而不是根据该测试集反复修改模型。</p>
</main></body></html>"""
