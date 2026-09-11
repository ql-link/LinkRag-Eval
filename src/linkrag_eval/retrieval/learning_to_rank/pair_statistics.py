"""Paired strict outcomes: source-group percentile CIs and exact sign tests.

Differences are a minus b. Unavailable outcomes are excluded from both methods;
thus estimates are conditional on joint availability, with exclusions reported.
The strict unit is a directional query/pair comparison; the bidirectional unit
is one complete q1/q2 pair. Neither metric averages source-group accuracies.
"""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from .nevir_evaluation import _bootstrap_delta

RELATIONS = frozenset({"strict_correct", "reverse", "model_tie", "unavailable"})


def _available(rows, ranker_a, ranker_b):
    kept, dropped = [], 0
    for row in rows:
        for ranker in (ranker_a, ranker_b):
            if row.get(ranker) not in RELATIONS:
                raise ValueError(f"missing or invalid relation for {ranker}")
        if "unavailable" in (row[ranker_a], row[ranker_b]):
            dropped += 1
        else:
            kept.append(row)
    return kept, dropped


def _delta(row, a, b):
    return int(row[a] == "strict_correct") - int(row[b] == "strict_correct")


def _ci(groups, differences, *, seed, repeats, alpha):
    """Reuse N04's side-effect-free helper for 95% intervals.

    For other confidence levels only, reproduce its seeded draws to change
    the percentile endpoints; sorted groups, sums/sizes and micro means match.
    """
    if type(repeats) is not int or repeats < 1:
        raise ValueError("repeats must be a positive integer")
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between zero and one")
    if any(not isinstance(g, str) or not g for g in groups):
        raise ValueError("source group IDs must be nonempty strings")
    result = _bootstrap_delta(groups, differences, seed=seed, repeats=repeats)
    if alpha != 0.05 and result["interval"] is not None:
        grouped = defaultdict(list)
        for group, value in zip(groups, differences, strict=True):
            grouped[group].append(value)
        keys = sorted(grouped)
        sizes = np.asarray([len(grouped[k]) for k in keys], dtype=np.int64)
        sums = np.asarray([sum(grouped[k]) for k in keys], dtype=np.float64)
        draws = np.random.default_rng(seed).integers(0, len(keys), (repeats, len(keys)))
        estimates = sums[draws].sum(axis=1) / sizes[draws].sum(axis=1)
        result["interval"] = np.quantile(
            estimates, [alpha / 2, 1 - alpha / 2], method="linear"
        ).tolist()
    return dict(
        result,
        estimate=sum(differences) / len(differences) if differences else None,
        n=len(differences),
        alpha=alpha,
        confidence=1 - alpha,
    )


def strict_delta_ci(
    rows,
    ranker_a,
    ranker_b,
    *,
    group_key="source_group_id",
    seed=20260910,
    repeats=2000,
    alpha=0.05,
):
    """Micro strict-accuracy difference on jointly available directional rows."""
    rows = list(rows)
    kept, dropped = _available(rows, ranker_a, ranker_b)
    result = _ci(
        [r.get(group_key) for r in kept],
        [_delta(r, ranker_a, ranker_b) for r in kept],
        seed=seed,
        repeats=repeats,
        alpha=alpha,
    )
    return dict(
        result,
        total_rows=len(rows),
        dropped_unavailable=dropped,
        unit="directional_query",
        group_key=group_key,
    )


def paired_sign_test(rows, ranker_a, ranker_b):
    """Exact two-sided Binomial(n_discordant, .5) test; no cluster adjustment.

    Ties include both-correct and both-not-correct. No discordance yields p=1;
    no available observations yields p=None. P-values are not multiplicity adjusted.
    """
    kept, dropped = _available(rows, ranker_a, ranker_b)
    differences = [_delta(r, ranker_a, ranker_b) for r in kept]
    a_only, b_only = differences.count(1), differences.count(-1)
    n = a_only + b_only
    numerator = 2 * sum(math.comb(n, k) for k in range(min(a_only, b_only) + 1))
    p = min(1.0, numerator / (1 << n)) if kept else None
    return {
        "a_correct_b_not": a_only,
        "b_correct_a_not": b_only,
        "ties": len(kept) - n,
        "discordant": n,
        "n": len(kept),
        "dropped_unavailable": dropped,
        "p_value": p,
        "method": "exact_two_sided_binomial",
        "unit": "directional_query",
    }


def bidirectional_delta_ci(
    rows,
    ranker_a,
    ranker_b,
    *,
    group_key="source_group_id",
    seed=20260910,
    repeats=2000,
    alpha=0.05,
):
    """Bootstrap complete q1/q2 pairs, excluding any pair with unavailable data.

    Duplicate directions and pairs spanning groups are malformed input, not
    exclusions. Incomplete pairs are counted separately from unavailable pairs.
    """
    rows = list(rows)
    _, unavailable_rows = _available(rows, ranker_a, ranker_b)
    pairs = defaultdict(list)
    for row in rows:
        if not row.get("pair_id") or row.get("direction") not in {"q1", "q2"}:
            raise ValueError("pair_id and q1/q2 direction are required")
        pairs[row["pair_id"]].append(row)
    groups, differences = [], []
    incomplete = unavailable = 0
    for pair in pairs.values():
        if len({r.get(group_key) for r in pair}) != 1:
            raise ValueError("pair spans source groups")
        if len({r["direction"] for r in pair}) != len(pair):
            raise ValueError("duplicate pair direction")
        if len(pair) != 2:
            incomplete += 1
            continue
        if any(r[k] == "unavailable" for r in pair for k in (ranker_a, ranker_b)):
            unavailable += 1
            continue
        groups.append(pair[0].get(group_key))
        differences.append(
            int(all(r[ranker_a] == "strict_correct" for r in pair))
            - int(all(r[ranker_b] == "strict_correct" for r in pair))
        )
    result = _ci(groups, differences, seed=seed, repeats=repeats, alpha=alpha)
    return dict(
        result,
        total_pairs=len(pairs),
        dropped_incomplete_pairs=incomplete,
        dropped_unavailable_pairs=unavailable,
        unavailable_rows=unavailable_rows,
        unit="bidirectional_pair",
        group_key=group_key,
    )


def comparison_table(rows, comparisons: list[tuple[str, str]], **kw):
    """Return JSON-ready comparison rows including both metrics and sign counts."""
    rows = list(rows)
    return [
        {
            "ranker_a": a,
            "ranker_b": b,
            "strict": strict_delta_ci(rows, a, b, **kw),
            "bidirectional": bidirectional_delta_ci(rows, a, b, **kw),
            "sign_test": paired_sign_test(rows, a, b),
        }
        for a, b in comparisons
    ]
