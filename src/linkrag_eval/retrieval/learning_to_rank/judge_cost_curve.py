"""Pure cached-score cost curves; no inference, storage writes or model loading."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .llm_judge import baseline_order, evaluate_pairs, list_metrics, resort

ROUTES = ("dense", "sparse", "bm25")


@dataclass
class RoleInputs:
    role: str
    baseline: dict
    stage1: dict
    judged: dict
    supervision: list[dict]
    candidates: list[dict]

    def __post_init__(self):
        if self.role not in {"development", "confirmation"}:
            raise ValueError("only development and confirmation are supported")
        if not self.stage1 or set(self.baseline) != set(self.stage1) or any(
            set(self.baseline[q]) != set(s) for q, s in self.stage1.items()
        ):
            raise ValueError("baseline/stage1 population mismatch")
        labels = [r["source_query_id"] for r in self.supervision]
        if len(set(labels)) != len(labels) or set(labels) != set(self.stage1):
            raise ValueError("supervision population mismatch")
        if any(r.get("source_split") != "validation"
               or r.get("role") != self.role for r in self.supervision):
            raise ValueError("only matching validation supervision is supported")
        if not set(self.judged) <= set(self.stage1) or any(
            not set(s) <= set(self.stage1[q]) for q, s in self.judged.items()
        ):
            raise ValueError("judge cache contains out-of-pool candidates")


def route_disagreement(candidate):
    """Use explicit zero-based saved ranks; absent/empty routes count as missing."""
    tops, missing = [], 0
    routes = candidate.get("routes", {})
    for route in ROUTES:
        hits = routes.get(route)
        if not hits:
            missing += 1
            continue
        ranks = [h["rank"] for h in hits]
        if any(type(r) is not int for r in ranks) or sorted(ranks) != list(range(len(hits))):
            raise ValueError("expected unique zero-based route ranks")
        tops.append(min(hits, key=lambda h: h["rank"])["chunk_id"])
    return bool(missing or len(set(tops)) > 1), missing


def fusion_margins(inputs):
    margins = {}
    for qid, scores in inputs.stage1.items():
        top = baseline_order(scores)[:2]
        # No ambiguity to resolve when fewer than two candidates are available.
        margins[qid] = scores[top[0]] - scores[top[1]] if len(top) == 2 else math.inf
    return margins


def evaluate_point(inputs, k, *, variant="always_call", threshold=None, triggers=None):
    """Count available selected cache entries, including entries in fallback queries.

    Missing/None/non-finite scores become unjudged. Exactly as in resort, one
    unjudged top-K candidate causes whole-query stage1 fallback. Requested slots
    are recorded separately; neither counter represents newly executed API calls.
    """
    if type(k) is not int or k < 0:
        raise ValueError("K must be a nonnegative integer")
    if triggers is not None and set(triggers) != set(inputs.stage1):
        raise ValueError("trigger population mismatch")
    values, orders = {}, {}
    available = missing = requested = fallback = changed = triggered = 0
    for qid, stage1 in inputs.stage1.items():
        call = k > 0 and (triggers is None or triggers[qid])
        if call:
            judged = {cid: v if v is not None and math.isfinite(v) else None
                      for cid, v in inputs.judged.get(qid, {}).items()}
            orders[qid], values[qid], stats = resort(stage1, judged, top_k=k)
            available += stats["available"]
            missing += stats["unavailable"]
            requested += stats["top_k_candidates"]
            fallback += stats["fallback"]
            changed += stats["triggered"]
            triggered += 1
        else:
            orders[qid], values[qid] = baseline_order(stage1), stage1
    report, rows = evaluate_pairs(inputs.supervision, inputs.baseline, values)
    pair = report["judge"]
    lists = list_metrics(rows, orders, {r["source_query_id"]: r for r in inputs.supervision})
    n = len(inputs.stage1)
    return {
        "role": inputs.role, "variant": variant, "K": k, "threshold": threshold,
        **{key: pair[key] for key in ("n", "strict_correct", "reverse", "model_tie",
                                     "unavailable", "strict_accuracy",
                                     "eligible_bidirectional_pairs", "both_directions_correct")},
        "preferred@1": lists["preferred@1"], "queries": n,
        "triggered_queries": triggered, "triggered_fraction": triggered / n,
        "judged_candidates": available, "mean_judged": available / n,
        "requested_candidates": requested, "mean_requested": requested / n,
        "missing_judge_candidates": missing, "fallback_queries": fallback,
        "changed_queries": changed,
        "evaluation": {"pairwise": pair, "list": lists},
    }


def curve_points(role_inputs, ks=range(1, 21)):
    return [evaluate_point(role_inputs, k) for k in ks]


def select_margin_threshold(development, *, top_k=20, target_fraction=0.95):
    """Select only on development; ties in cost use the smallest threshold."""
    if development.role != "development":
        raise ValueError("threshold selection requires development")
    if not 0 < target_fraction <= 1:
        raise ValueError("target fraction must be in (0, 1]")
    margins = fusion_margins(development)
    finite = [m for m in margins.values() if math.isfinite(m)]
    quantiles = np.linspace(0, 1, 101)
    thresholds = sorted(set(map(float, np.quantile(finite, quantiles)))) if finite else [0.0]
    # Strict '<' needs an endpoint above the maximum to include every finite margin.
    if finite:
        thresholds.append(math.nextafter(max(finite), math.inf))
    sweep = [evaluate_point(development, top_k, variant="fusion_margin", threshold=t,
                           triggers={q: m < t for q, m in margins.items()}) for t in thresholds]
    full = evaluate_point(development, top_k)
    target = target_fraction * full["strict_correct"]
    eligible = [p for p in sweep if p["strict_correct"] >= target]
    if not eligible:
        raise ValueError("no development margin threshold meets the target")
    chosen = min(eligible, key=lambda p: (p["mean_judged"], p["threshold"]))
    return {
        "threshold": chosen["threshold"], "top_k": top_k, "selection_role": "development",
        "target_fraction": target_fraction, "target_strict_correct": target,
        "full_k_strict_correct": full["strict_correct"],
        "rule": f"min(mean_judged, threshold) subject to strict_correct >= {target_fraction} * full-K; margin < threshold",
        "quantiles": quantiles.tolist(), "quantile_method": "linear",
        "endpoint": "nextafter(max finite development margin, +inf); fewer than 2 candidates do not trigger",
        "sweep": sweep,
    }


def trigger_variants(role_inputs, *, threshold, top_k=20):
    if not math.isfinite(threshold):
        raise ValueError("threshold must be finite")
    candidates = {r["source_query_id"]: r for r in role_inputs.candidates}
    if len(candidates) != len(role_inputs.candidates) or not set(candidates) <= set(role_inputs.stage1):
        raise ValueError("duplicate or foreign candidate query")
    decisions = {q: route_disagreement(candidates.get(q, {})) for q in role_inputs.stage1}
    margins = fusion_margins(role_inputs)
    points = [
        evaluate_point(role_inputs, top_k),
        evaluate_point(role_inputs, 0, variant="never_call"),
        evaluate_point(role_inputs, top_k, variant="fusion_margin", threshold=threshold,
                       triggers={q: m < threshold for q, m in margins.items()}),
        evaluate_point(role_inputs, top_k, variant="route_disagreement",
                       triggers={q: d[0] for q, d in decisions.items()}),
    ]
    for point in points:
        point.update(missing_route_queries=sum(d[1] > 0 for d in decisions.values()),
                     missing_routes=sum(d[1] for d in decisions.values()))
    return points
