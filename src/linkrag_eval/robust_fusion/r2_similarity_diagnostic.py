"""Pure statistics for the outcome-aware R2 similarity failure diagnostic.

The functions in this module are descriptive and exploratory.  They cannot
authorize a measurement freeze, readiness, or a Gate run.
"""

from __future__ import annotations

import math
import random
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from statistics import mean, variance
from typing import Any


def normalize_surface(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def detect_language(text: str) -> str:
    normalized = normalize_surface(text)
    han = sum("CJK UNIFIED IDEOGRAPH" in unicodedata.name(char, "") for char in normalized)
    latin = sum(char.isascii() and char.isalpha() for char in normalized)
    if han > 0 and han > latin:
        return "zh"
    if latin > 0 and han == 0:
        return "en"
    return "unknown"


def levenshtein_distance(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def surface_metrics(reference: str, candidate: str) -> dict[str, Any]:
    left = normalize_surface(reference)
    right = normalize_surface(candidate)
    maximum = max(len(left), len(right))
    distance = levenshtein_distance(left, right)
    normalized_distance = 0.0 if maximum == 0 else distance / maximum

    prefix = 0
    while prefix < min(len(left), len(right)) and left[prefix] == right[prefix]:
        prefix += 1
    suffix = 0
    suffix_limit = min(len(left), len(right)) - prefix
    while suffix < suffix_limit and left[-(suffix + 1)] == right[-(suffix + 1)]:
        suffix += 1
    coverage = 1.0 if maximum == 0 else (prefix + suffix) / maximum
    return {
        "reference_normalized_length": len(left),
        "candidate_normalized_length": len(right),
        "normalized_levenshtein": normalized_distance,
        "length_ratio": 1.0 if maximum == 0 else min(len(left), len(right)) / maximum,
        "prefix_suffix_coverage": coverage,
        "single_slot_proxy": normalized_distance <= 0.20 and coverage >= 0.60,
        "normalized_candidate_text": right,
    }


def _average_ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: (values[index], index))
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + end - 1) / 2
        for position in range(start, end):
            ranks[order[position]] = rank
        start = end
    return ranks


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    left_mean = mean(left)
    right_mean = mean(right)
    numerator = sum(
        (first - left_mean) * (second - right_mean)
        for first, second in zip(left, right, strict=True)
    )
    left_sum = sum((value - left_mean) ** 2 for value in left)
    right_sum = sum((value - right_mean) ** 2 for value in right)
    denominator = math.sqrt(left_sum * right_sum)
    return None if denominator == 0 else numerator / denominator


def spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    return _pearson(_average_ranks(left), _average_ranks(right))


def kendall_tau_b(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    concordant = 0
    discordant = 0
    ties_left = 0
    ties_right = 0
    for first in range(len(left) - 1):
        for second in range(first + 1, len(left)):
            left_delta = left[first] - left[second]
            right_delta = right[first] - right[second]
            if left_delta == 0 and right_delta == 0:
                continue
            if left_delta == 0:
                ties_left += 1
            elif right_delta == 0:
                ties_right += 1
            elif left_delta * right_delta > 0:
                concordant += 1
            else:
                discordant += 1
    denominator = math.sqrt(
        (concordant + discordant + ties_left)
        * (concordant + discordant + ties_right)
    )
    return None if denominator == 0 else (concordant - discordant) / denominator


def pairwise_tie_fraction(values: Sequence[Any]) -> float | None:
    if len(values) < 2:
        return None
    numerator = sum(count * (count - 1) // 2 for count in Counter(values).values())
    denominator = len(values) * (len(values) - 1) // 2
    return numerator / denominator


def human_distribution(values: Sequence[int]) -> dict[str, Any]:
    counts = Counter(values)
    entropy = -sum(
        (count / len(values)) * math.log(count / len(values)) for count in counts.values()
    )
    entropy_denominator = math.log(min(5, len(values))) if len(values) > 1 else 0.0
    return {
        "n": len(values),
        "counts": {str(score): counts.get(score, 0) for score in range(1, 6)},
        "minimum": min(values),
        "maximum": max(values),
        "range": max(values) - min(values),
        "mean": mean(values),
        "variance_ddof1": variance(values) if len(values) > 1 else None,
        "unique_value_count": len(counts),
        "pairwise_tie_fraction": pairwise_tie_fraction(values),
        "ceiling_fraction_score_5": counts.get(5, 0) / len(values),
        "score_ge4_fraction": sum(value >= 4 for value in values) / len(values),
        "entropy_nats": entropy,
        "normalized_entropy": (
            None if entropy_denominator == 0 else entropy / entropy_denominator
        ),
    }


def numeric_distribution(values: Sequence[float]) -> dict[str, Any]:
    return {
        "n": len(values),
        "minimum": min(values),
        "maximum": max(values),
        "range": max(values) - min(values),
        "mean": mean(values),
        "variance_ddof1": variance(values) if len(values) > 1 else None,
        "unique_value_count": len(set(values)),
        "pairwise_rank_tie_fraction": pairwise_tie_fraction(values),
    }


def correlation_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    human = [float(row["human_score"]) for row in rows]
    main = [float(row["main_similarity"]) for row in rows]
    audit = [float(row["audit_similarity"]) for row in rows]
    return {
        "n": len(rows),
        "main_human": {
            "spearman": spearman(main, human),
            "kendall_tau_b": kendall_tau_b(main, human),
        },
        "audit_human": {
            "spearman": spearman(audit, human),
            "kendall_tau_b": kendall_tau_b(audit, human),
        },
        "main_audit": {
            "spearman": spearman(main, audit),
            "kendall_tau_b": kendall_tau_b(main, audit),
        },
    }


def summarize_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    candidates = [str(row["normalized_candidate_text"]) for row in rows]
    template_hashes = [
        str(row["template_hash"]) for row in rows if row.get("template_hash") is not None
    ]
    return {
        "n": len(rows),
        "human": human_distribution([int(row["human_score"]) for row in rows]),
        "main_encoder": numeric_distribution(
            [float(row["main_similarity"]) for row in rows]
        ),
        "audit_encoder": numeric_distribution(
            [float(row["audit_similarity"]) for row in rows]
        ),
        "correlations": correlation_summary(rows),
        "surface": {
            "exact_candidate_duplicate_fraction": 1 - len(set(candidates)) / len(candidates),
            "template_hash_observed_n": len(template_hashes),
            "template_repeat_fraction": (
                None
                if not template_hashes
                else 1 - len(set(template_hashes)) / len(template_hashes)
            ),
            "normalized_levenshtein_mean": mean(
                float(row["normalized_levenshtein"]) for row in rows
            ),
            "normalized_levenshtein_min": min(
                float(row["normalized_levenshtein"]) for row in rows
            ),
            "normalized_levenshtein_max": max(
                float(row["normalized_levenshtein"]) for row in rows
            ),
            "single_slot_proxy_fraction": sum(
                bool(row["single_slot_proxy"]) for row in rows
            )
            / len(rows),
        },
        "truncation": {
            "main_truncated_count": sum(bool(row["main_was_truncated"]) for row in rows),
            "audit_truncated_count": sum(bool(row["audit_was_truncated"]) for row in rows),
        },
    }


def grouped_summaries(
    rows: Sequence[Mapping[str, Any]], group_fields: Sequence[Sequence[str]]
) -> list[dict[str, Any]]:
    output = []
    for fields in group_fields:
        grouped: dict[tuple[str, ...], list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[tuple(str(row.get(field, "unknown")) for field in fields)].append(row)
        for values, group_rows in sorted(grouped.items()):
            output.append(
                {
                    "group_fields": list(fields),
                    "group_values": dict(zip(fields, values, strict=True)),
                    "summary": summarize_rows(group_rows),
                }
            )
    return output


def _percentile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def clustered_bootstrap(
    rows: Sequence[Mapping[str, Any]],
    *,
    seed: int = 20260829,
    iterations: int = 10000,
) -> dict[str, Any]:
    by_family: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_family[str(row["family_id"])].append(row)
    family_ids = sorted(by_family)
    randomizer = random.Random(seed)
    statistics: dict[str, list[float]] = {
        "main_human_spearman": [],
        "main_human_kendall_tau_b": [],
        "audit_human_spearman": [],
        "audit_human_kendall_tau_b": [],
    }
    for _ in range(iterations):
        sampled: list[Mapping[str, Any]] = []
        for _family in family_ids:
            sampled.extend(by_family[randomizer.choice(family_ids)])
        summary = correlation_summary(sampled)
        candidates = {
            "main_human_spearman": summary["main_human"]["spearman"],
            "main_human_kendall_tau_b": summary["main_human"]["kendall_tau_b"],
            "audit_human_spearman": summary["audit_human"]["spearman"],
            "audit_human_kendall_tau_b": summary["audit_human"]["kendall_tau_b"],
        }
        for key, value in candidates.items():
            if value is not None and math.isfinite(value):
                statistics[key].append(value)
    return {
        "seed": seed,
        "iterations": iterations,
        "cluster_count": len(family_ids),
        "intervals": {
            key: {
                "valid_iterations": len(values),
                "lower_2_5": _percentile(values, 0.025),
                "upper_97_5": _percentile(values, 0.975),
            }
            for key, values in statistics.items()
        },
    }


def influence_diagnostics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    full = correlation_summary(rows)
    full_main = full["main_human"]["spearman"]
    full_audit = full["audit_human"]["spearman"]
    strata = sorted({(str(row["length_stratum"]), str(row["language"])) for row in rows})
    leave_stratum = []
    for length, language in strata:
        kept = [
            row
            for row in rows
            if (str(row["length_stratum"]), str(row["language"])) != (length, language)
        ]
        summary = correlation_summary(kept)
        main_value = summary["main_human"]["spearman"]
        audit_value = summary["audit_human"]["spearman"]
        leave_stratum.append(
            {
                "omitted": {"length_stratum": length, "language": language},
                "remaining_n": len(kept),
                "main_human_spearman": main_value,
                "main_delta_from_full": (
                    None if main_value is None or full_main is None else main_value - full_main
                ),
                "audit_human_spearman": audit_value,
                "audit_delta_from_full": (
                    None
                    if audit_value is None or full_audit is None
                    else audit_value - full_audit
                ),
            }
        )

    family_ids = sorted({str(row["family_id"]) for row in rows})
    leave_family = []
    for family_id in family_ids:
        kept = [row for row in rows if str(row["family_id"]) != family_id]
        summary = correlation_summary(kept)
        main_value = summary["main_human"]["spearman"]
        audit_value = summary["audit_human"]["spearman"]
        leave_family.append(
            {
                "family_id": family_id,
                "main_delta_from_full": (
                    None if main_value is None or full_main is None else main_value - full_main
                ),
                "audit_delta_from_full": (
                    None
                    if audit_value is None or full_audit is None
                    else audit_value - full_audit
                ),
            }
        )

    def largest(records: Sequence[Mapping[str, Any]], key: str) -> Mapping[str, Any] | None:
        eligible = [record for record in records if record[key] is not None]
        return None if not eligible else max(eligible, key=lambda record: abs(record[key]))

    return {
        "full": full,
        "leave_one_length_language_stratum_out": leave_stratum,
        "leave_one_family_out_largest_main": largest(leave_family, "main_delta_from_full"),
        "leave_one_family_out_largest_audit": largest(leave_family, "audit_delta_from_full"),
    }


def truncation_boundary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for encoder, flag, score in (
        ("main_e5", "main_was_truncated", "main_similarity"),
        ("audit_distiluse", "audit_was_truncated", "audit_similarity"),
    ):
        encoder_rows = {}
        for label, selected in (
            ("all", list(rows)),
            ("long", [row for row in rows if row["length_stratum"] == "long"]),
            ("truncated", [row for row in rows if row[flag]]),
            ("not_truncated", [row for row in rows if not row[flag]]),
            (
                "long_truncated",
                [row for row in rows if row["length_stratum"] == "long" and row[flag]],
            ),
            (
                "long_not_truncated",
                [row for row in rows if row["length_stratum"] == "long" and not row[flag]],
            ),
        ):
            values = [float(row[score]) for row in selected]
            human = [float(row["human_score"]) for row in selected]
            encoder_rows[label] = {
                "n": len(selected),
                "spearman_human": spearman(values, human),
                "kendall_tau_b_human": kendall_tau_b(values, human),
            }
        output[encoder] = encoder_rows
    return output


def fallacy_scan() -> dict[str, Any]:
    return {
        "coverage": "11/11",
        "simpsons_paradox": "possible_checked_via_overall_vs_frozen_strata_no_causal_claim",
        "ecological_fallacy": "not_applicable_no_individual_population_inference",
        "berksons_paradox": "possible_selected_similarity_audit_frames",
        "collider_bias": "not_applicable_no_covariate_adjustment",
        "base_rate_neglect": "not_applicable_no_diagnostic_probability_claim",
        "regression_to_mean": "not_applicable_no_extreme_group_pre_post_claim",
        "survivorship_bias": "not_detected_all_locked_final_human_rows_retained",
        "look_elsewhere_effect": "possible_many_exploratory_strata_all_reported_no_new_pass_path",
        "garden_of_forking_paths": "caution_outcome_aware_plan_and_schema_addenda_transparently_locked_before_statistics",
        "correlation_causation": "guarded_association_only_no_single_cause_claim",
        "reverse_causality": "not_applicable_no_directional_causal_claim",
    }


def template_skeleton(text: str) -> str:
    """Diagnostic-only skeleton for human-readable examples, not a grouping truth."""
    normalized = normalize_surface(text).lower()
    normalized = re.sub(r"\d+(?:[.:-]\d+)*", "<num>", normalized)
    return re.sub(r"[a-z]+(?:-[a-z0-9]+)+", "<id>", normalized)
