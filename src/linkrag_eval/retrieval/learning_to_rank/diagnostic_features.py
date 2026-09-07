"""Offline provenance for the existing 38 features; never a scoring implementation.

Offsets are half-open Python Unicode-code-point offsets, not bytes or graphemes.
Location recovery is a diagnostic side channel. Only features.build_online_features
produces the authoritative matrix, and no diagnostic value is fed back into it.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

import numpy as np

from linkrag_eval.retrieval.learning_to_rank import english_rules as en
from linkrag_eval.retrieval.learning_to_rank import features as core

SEMANTIC_STATUS = "unknown_pending_human_review"
_SENTENCE_SPLIT = re.compile(r"[.!?。！？\n]+")


def feature_dependencies(feature_version: str = core.FEATURE_VERSION) -> list[dict[str, Any]]:
    """Return all columns in model order, including the two normalization contexts."""
    rules: dict[str, tuple[list[str], str, str]] = {}

    def add(name, dependencies, rule, trace):
        rules[name] = (dependencies, rule, trace)

    for source in core.ROUTES:
        route = ["route_return_list", "candidate_identity"]
        score_name = f"{source}_score" if source == "dense" else f"{source}_log_score"
        add(
            score_name,
            route,
            "raw score" if source == "dense" else "log1p(max(0, raw))",
            f"route_trace.{source}",
        )
        add(
            f"{source}_norm",
            route,
            "min-max over the original full route; constant -> 1",
            f"pool_summary.routes.{source}",
        )
        add(
            f"{source}_rr",
            route,
            "1 / one-based list position; supplied rank field unused",
            f"route_trace.{source}",
        )
        add(f"{source}_missing", route, "1 if absent from route else 0", f"route_trace.{source}")
        add(
            f"{source}_top12_margin",
            ["route_return_list"],
            "max(0, transformed[0]-transformed[1]) / max(abs(transformed[0]),1e-9); <2 -> 0",
            f"pool_summary.routes.{source}",
        )
    for name, rule in (
        ("route_count", "number of routes containing candidate"),
        ("all_routes", "candidate appears in all three routes"),
    ):
        add(name, ["route_return_list", "candidate_identity"], rule, "route_trace")
    for a, b in (("dense", "sparse"), ("dense", "bm25"), ("sparse", "bm25")):
        add(
            f"{a}_{b}_overlap",
            ["route_return_list", "candidate_identity"],
            "both route-presence flags true",
            "route_trace",
        )
        add(
            f"{a}_{b}_rr_gap",
            ["route_return_list", "candidate_identity"],
            "absolute difference of reciprocal list positions; absent -> 0",
            "route_trace",
        )
    add(
        "baseline_score",
        ["route_return_list", "candidate_identity"],
        "threshold each route, renormalize within retained route, fuse active-route weights",
        "baseline_trace",
    )
    add(
        "baseline_rr",
        ["route_return_list", "candidate_identity"],
        "1/(zero-based fused rank+1); absent after thresholds -> 0; score ties by chunk_id",
        "baseline_trace",
    )
    add(
        "query_length",
        ["query"],
        "len(original query), including whitespace/punctuation",
        "query_trace.raw_length",
    )
    add(
        "query_has_digit",
        ["query"],
        "any original character.isdigit()",
        "query_trace.digit_occurrences",
    )
    for prefix in ("identifier", "number"):
        add(
            f"{prefix}_exact_coverage",
            ["query", "single_candidate_text"],
            "unique regex-extracted query strings found anywhere in content.lower / unique strings",
            f"text_features.{prefix}_exact_coverage",
        )
    add(
        "negation_overlap_coverage",
        ["query", "single_candidate_text"],
        "set intersection of literal Chinese negation substrings / query negation set size",
        "text_features.negation_overlap_coverage",
    )
    add(
        "negation_mismatch",
        ["query", "single_candidate_text"],
        "different set-emptiness OR nonempty query set with empty intersection",
        "text_features.negation_mismatch",
    )
    for size in ("bigram", "trigram"):
        add(
            f"query_{size}_coverage",
            ["query", "single_candidate_text"],
            "unique normalized-character ngram intersection / query set size; empty -> 0",
            f"text_features.query_{size}_coverage",
        )
    add(
        "condition_coverage",
        ["query", "single_candidate_text"],
        "actual regex query clauses with >=0.5 unique-bigram coverage / retained clauses; <=1 -> 0",
        "text_features.condition_coverage",
    )
    add(
        "distinctive_query_bigram_coverage",
        ["query", "full_candidate_pool", "candidate_texts"],
        "matched query bigrams with candidate-document-frequency <= max(1,ceil(pool_size*.1))"
        " / all query bigrams",
        "text_features.distinctive_query_bigram_coverage",
    )
    add(
        "same_doc_candidate_count",
        ["full_candidate_pool", "legal_metadata.doc_id"],
        "candidate count sharing doc_id minus 1; dataset_id is not part of grouping",
        "text_features.same_doc",
    )
    add(
        "same_doc_max_bigram_similarity",
        ["full_candidate_pool", "legal_metadata.doc_id", "candidate_texts"],
        "maximum unique-bigram Jaccard with another same-doc candidate; no peers -> 0",
        "text_features.same_doc",
    )
    add(
        "content_length_log",
        ["single_candidate_text"],
        "log1p(len(original content))",
        "text_features.content_length_log",
    )
    core.rules_version(feature_version)
    if feature_version == core.ENGLISH_FEATURE_VERSION:
        for prefix in ("identifier", "number"):
            add(f"{prefix}_exact_coverage", ["query", "single_candidate_text"],
                "intersection of canonical extracted token sets / query set size; not substring coverage",
                f"text_features.{prefix}_exact_coverage")
        add("negation_overlap_coverage", ["query", "single_candidate_text"],
            "intersection of word-bounded canonical English negators / query negation set size",
            "text_features.negation_overlap_coverage")
        add("condition_coverage", ["query", "single_candidate_text"],
            "English surface clauses with numeric/abbreviation protection; same >=0.5 bigram rule",
            "text_features.condition_coverage")
    if set(rules) != set(core.FEATURE_NAMES):
        raise ValueError("feature schema changed; provenance requires review")
    return [
        {
            "index": index,
            "name": name,
            "dependencies": rules[name][0],
            "rule": rules[name][1],
            "trace_path": rules[name][2],
            "semantic_classification": SEMANTIC_STATUS,
        }
        for index, name in enumerate(core.FEATURE_NAMES)
    ]


def _span(text: str, start: int, end: int) -> dict[str, Any]:
    return {"start": start, "end": end, "quote": text[start:end]}


def _segments(text: str, splitter: re.Pattern) -> tuple[list[dict], list[dict]]:
    parts, delimiters = [], []
    start = 0
    for match in splitter.finditer(text):
        parts.append(_span(text, start, match.start()))
        delimiters.append(_span(text, *match.span()))
        start = match.end()
    parts.append(_span(text, start, len(text)))
    return parts, delimiters


def _lower_map(text: str, raw_positions: list[int]) -> tuple[str, list[dict]]:
    """Map lower() expansions to source ranges, without inventing a one-to-one map."""
    selected = "".join(text[i] for i in raw_positions)
    lowered = selected.lower()
    mapping = []
    for raw_index in raw_positions:
        expansion = text[raw_index].lower()
        for _ in expansion:
            mapping.append(
                {
                    "raw_start": raw_index,
                    "raw_end": raw_index + 1,
                    "mapping": "one_to_one" if len(expansion) == 1 else "lowercase_expansion",
                }
            )
    if len(mapping) != len(lowered):
        # Preserve a conservative range if Unicode casing becomes context-length-sensitive.
        start, end = (raw_positions[0], raw_positions[-1] + 1) if raw_positions else (0, 0)
        mapping = [
            {"raw_start": start, "raw_end": end, "mapping": "ambiguous_range"} for _ in lowered
        ]
    return lowered, mapping


def _occurrence(
    text: str,
    mapping: list[dict],
    start: int,
    end: int,
    sentences: list[dict],
    clauses: list[dict] | None,
) -> dict[str, Any]:
    entries = mapping[start:end]
    source_ranges = sorted({(row["raw_start"], row["raw_end"]) for row in entries})
    merged = []
    for left, right in source_ranges:
        if merged and left <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], right)
        else:
            merged.append([left, right])
    raw_start, raw_end = source_ranges[0][0], source_ranges[-1][1]

    def overlapping_ids(rows):
        return [
            i
            for i, row in enumerate(rows)
            if any(a < row["end"] and b > row["start"] for a, b in source_ranges)
        ]

    return {
        "processed_start": start,
        "processed_end": end,
        "raw_span": _span(text, raw_start, raw_end),
        "raw_segments": merged,
        "mapping": "one_to_one"
        if all(e["mapping"] == "one_to_one" for e in entries)
        else "source_range_not_one_to_one",
        "joins_removed_characters": len(merged) > 1,
        "diagnostic_sentence_ids": overlapping_ids(sentences),
        "actual_query_clause_ids": overlapping_ids(clauses) if clauses is not None else None,
    }


def _find_all(text: str, needle: str) -> list[tuple[int, int]]:
    matches, start = [], 0
    while needle and (index := text.find(needle, start)) >= 0:
        matches.append((index, index + len(needle)))
        start = index + 1
    return matches


def _english_segments(text: str) -> tuple[list[dict], list[dict]]:
    """Recover offsets alongside the frozen rule; the retained strings are checked below."""
    protected = set()
    for pattern in (en._GROUPED_NUMBER_RE, en._ABBREVIATION_RE, en._INITIAL_RE):
        for match in pattern.finditer(text):
            protected.update(i for i in range(*match.span()) if text[i] in ".,")
    protected.update(i for i in range(1, len(text) - 1)
                     if text[i] == "." and text[i-1].isdigit() and text[i+1].isdigit())
    boundaries = sorted({m.span() for pattern in (core._CLAUSE_SPLIT_RE, en._ENGLISH_SEPARATOR_RE)
                         for m in pattern.finditer(text) if m.start() not in protected})
    parts, separators, start = [], [], 0
    for left, right in boundaries:
        if left < start:
            continue
        parts.append(_span(text, start, left))
        separators.append(_span(text, left, right))
        start = right
    parts.append(_span(text, start, len(text)))
    return parts, separators


def _english_regex_trace(text: str, *, is_query: bool) -> dict:
    # The identifier rule removes grouped-number commas before regex extraction.
    # Keep a map back to the original characters; do not invent normalized offsets.
    removed = {i for m in en._GROUPED_NUMBER_RE.finditer(text)
               for i in range(*m.span()) if text[i] == ","}
    positions = [i for i in range(len(text)) if i not in removed]
    normalized = "".join(text[i] for i in positions)
    identifiers = []
    for match in core._IDENTIFIER_RE.finditer(normalized):
        retained = match.group().rstrip("._-")
        end = match.start() + len(retained)
        identifiers.append({**_span(text, positions[match.start()], positions[end-1] + 1),
                            "needle": retained.lower()})
    numbers = [{**_span(text, *m.span()), "needle": m.group().replace(",", "")}
               for m in en._NUMBER_RE.finditer(text)]
    result = {}
    for name, matches, expected in (
        ("identifier", identifiers, en.identifiers(text, core._IDENTIFIER_RE)),
        ("number", numbers, en.numbers(text)),
    ):
        actual = {m["needle"] for m in matches}
        if actual != expected:
            raise ValueError(f"English {name} trace differs from frozen rules")
        result[name] = {"pattern": (core._IDENTIFIER_RE if name == "identifier" else en._NUMBER_RE).pattern,
                        "matches": matches, "unique_set": sorted(actual),
                        "used_as_query_needles": is_query,
                        "content_regex_matches_used_by_coverage": True,
                        "rules_version": en.RULES_VERSION}
    return result


def _text_trace(text: str, *, is_query: bool,
                feature_version: str = core.FEATURE_VERSION) -> dict[str, Any]:
    english = feature_version == core.ENGLISH_FEATURE_VERSION
    parts, separators = (_english_segments(text) if english else _segments(text, core._CLAUSE_SPLIT_RE))
    clauses = []
    for part in parts:
        stripped = part["quote"].strip()
        offset = len(part["quote"]) - len(part["quote"].lstrip())
        part["trimmed_span"] = _span(
            text, part["start"] + offset, part["start"] + offset + len(stripped)
        )
        part["retained"] = len(stripped) >= 2
        if part["retained"]:
            clauses.append(part["trimmed_span"])
    if english and [p["quote"] for p in clauses] != en.clauses(text, core._CLAUSE_SPLIT_RE):
        raise ValueError("English clause trace differs from frozen rules")
    sentences, _ = _segments(text, _SENTENCE_SPLIT)
    sentences = [part for part in sentences if part["quote"]]
    kept = [i for i, char in enumerate(text) if not core._TEXT_CLEAN_RE.fullmatch(char)]
    normalized, mapping = _lower_map(text, kept)
    if normalized != core._normalized_text(text):
        raise ValueError("diagnostic normalization differs from feature helper")
    ngrams = {}
    for size in (2, 3):
        occurrences: dict[str, list[dict]] = defaultdict(list)
        for start in range(max(0, len(normalized) - size + 1)):
            gram = normalized[start : start + size]
            occurrences[gram].append(
                _occurrence(
                    text, mapping, start, start + size, sentences, clauses if is_query else None
                )
            )
        if set(occurrences) != core._ngrams(text, size):
            raise ValueError("diagnostic ngram set differs from feature helper")
        ngrams[str(size)] = {
            "size": size,
            "unique_set": sorted(occurrences),
            "unique_count": len(occurrences),
            "occurrence_count": sum(map(len, occurrences.values())),
            "by_gram": {
                gram: {"count": len(occurrences[gram]), "occurrences": occurrences[gram]}
                for gram in sorted(occurrences)
            },
            "aggregation": "whole-text set; multiplicity, positions and sentences discarded",
        }
    regex_trace = {}
    for name, pattern in (("identifier", core._IDENTIFIER_RE), ("number", core._NUMBER_RE)):
        matches = [
            {**_span(text, *m.span()), "needle": m.group(0).lower()} for m in pattern.finditer(text)
        ]
        regex_trace[name] = {
            "pattern": pattern.pattern,
            "matches": matches,
            "unique_set": sorted({m["needle"] for m in matches}),
            "used_as_query_needles": is_query,
            "content_regex_matches_used_by_coverage": False,
        }
    negations = {
        token: [_span(text, a, b) for a, b in _find_all(text, token)]
        for token in core._NEGATIONS
        if token in text
    }
    if english:
        regex_trace = _english_regex_trace(text, is_query=is_query)
        negations = defaultdict(list)
        for match in en._NEGATION_RE.finditer(text.translate(en.APOSTROPHES)):
            token = match.group().lower()
            canonical = "not" if token == "cannot" or token in en.NEGATIVE_CONTRACTIONS else token
            negations[canonical].append(_span(text, *match.span()))
        if set(negations) != en.negations(text):
            raise ValueError("English negation trace differs from frozen rules")
    return {
        "raw_text": text,
        "raw_length": len(text),
        "normalized_text": normalized,
        "normalization_rule": core._TEXT_CLEAN_RE.pattern,
        "normalization_order": "delete regex matches, then str.lower; no whitespace boundary",
        "normalized_character_map": mapping,
        "normalized_character_map_index": "list index is normalized Unicode code point offset",
        "removed_spans": [_span(text, *m.span()) for m in core._TEXT_CLEAN_RE.finditer(text)],
        "diagnostic_sentences": sentences,
        "diagnostic_sentence_rule": _SENTENCE_SPLIT.pattern,
        "diagnostic_sentences_used_by_features": False,
        "condition_split": {
            "pattern": (f"{en.RULES_VERSION}: {core._CLAUSE_SPLIT_RE.pattern} + {en._ENGLISH_SEPARATOR_RE.pattern}; protected punctuation"
                        if english else core._CLAUSE_SPLIT_RE.pattern),
            "applied_by_feature": is_query,
            "parts": parts,
            "separators": separators,
            "retained_clauses": clauses,
            "gate_open": is_query and len(clauses) > 1,
        },
        "regex_extraction": regex_trace,
        "literal_negations": {
            "dictionary": list((*en.NEGATORS, "cannot", *en.NEGATIVE_CONTRACTIONS) if english else core._NEGATIONS),
            "unique_set": sorted(negations),
            "occurrences": negations,
            "matching": ("word-bounded, case-insensitive; apostrophe normalization; cannot/declared n't -> not"
                         if english else "literal substring, no word boundary"),
        },
        "digit_occurrences": [
            _span(text, i, i + 1) for i, char in enumerate(text) if char.isdigit()
        ],
        "ngrams": ngrams,
    }


def _set_coverage(query_grams: set[str], content_grams: set[str]) -> dict[str, Any]:
    matched = sorted(query_grams & content_grams)
    return {
        "matched_set": matched,
        "numerator": len(matched),
        "denominator": len(query_grams),
        "precast_value": len(matched) / len(query_grams) if query_grams else 0.0,
        "aggregation": "unique-set union across all positions; no co-location requirement",
    }


def _substring_coverage(needles: set[str], content: str, trace: dict) -> dict[str, Any]:
    lowered, mapping = _lower_map(content, list(range(len(content))))
    by_needle = {
        needle: [
            _occurrence(content, mapping, a, b, trace["diagnostic_sentences"], None)
            for a, b in _find_all(lowered, needle.lower())
        ]
        for needle in sorted(needles)
    }
    matched = [needle for needle, occurrences in by_needle.items() if occurrences]
    return {
        "needles": sorted(needles),
        "matched_set": matched,
        "numerator": len(matched),
        "denominator": len(needles),
        "precast_value": core._coverage(needles, content),
        "content_lowered": lowered,
        "occurrences_by_needle": by_needle,
        "aggregation": "substring anywhere in lowercased raw content; no word boundary",
    }


def _pool_summary(routes: dict, chunk_ids: list[str], contents: dict[str, str]) -> dict[str, Any]:
    route_hits = {source: core._route_hits({"routes": routes}, source) for source in core.ROUTES}
    filtered = core._baseline_hits(route_hits)
    active = [source for source in core.ROUTES if filtered[source]]
    weight_sum = sum(core.BASELINE_WEIGHTS[source] for source in active)
    route_summary, doc_by_chunk = {}, {}
    for source, hits in route_hits.items():
        normalized = core._normalized(hits, source)
        baseline_norm = core._normalized(filtered[source], source)
        transformed = [
            hit.score if source == "dense" else math.log1p(max(0, hit.score)) for hit in hits
        ]
        rows = []
        for index, (hit, score) in enumerate(zip(hits, transformed, strict=True)):
            doc_by_chunk.setdefault(hit.chunk_id, hit.doc_id)
            rows.append(
                {
                    "chunk_id": hit.chunk_id,
                    "doc_id": hit.doc_id,
                    "dataset_id": hit.dataset_id,
                    "raw_score": hit.score,
                    "supplied_rank": routes[source][index].get("rank"),
                    "effective_rank_one_based": index + 1,
                    "transformed_score": score,
                    "normalized": normalized[hit.chunk_id],
                    "passes_baseline_threshold": hit.chunk_id in baseline_norm,
                    "baseline_normalized": baseline_norm.get(hit.chunk_id, 0.0),
                }
            )
        route_summary[source] = {
            "hits": rows,
            "candidate_count": len(hits),
            "transformed_min": min(transformed) if transformed else None,
            "transformed_max": max(transformed) if transformed else None,
            "constant_score_rule": "all present candidates -> 1.0",
            "top12_margin": core._top12_margin(hits, source),
            "baseline_threshold": core.BASELINE_THRESHOLDS[source],
            "baseline_active_weight": core.BASELINE_WEIGHTS[source] / weight_sum
            if source in active
            else 0.0,
            "baseline_retained_ids": [hit.chunk_id for hit in filtered[source]],
        }
    baseline = core.weighted_score_fuse(
        filtered, final_top_k=sum(map(len, route_hits.values())), weights=core.BASELINE_WEIGHTS
    )
    gram_members: dict[str, list[str]] = defaultdict(list)
    doc_groups: dict[str, list[str]] = defaultdict(list)
    for cid in chunk_ids:
        doc_groups[str(doc_by_chunk[cid])].append(cid)
        for gram in sorted(core._ngrams(contents[cid], 2)):
            gram_members[gram].append(cid)
    return {
        "candidate_count": len(chunk_ids),
        "candidate_ids": chunk_ids,
        "content_lengths": {cid: len(contents[cid]) for cid in chunk_ids},
        "routes": route_summary,
        "baseline_order": [
            {"chunk_id": h.chunk_id, "score": h.score, "rank_zero_based": h.rank} for h in baseline
        ],
        "baseline_absence_rule": "no hit surviving any route threshold -> score 0 and rr 0",
        "baseline_tie_rule": "descending fused score, then ascending chunk_id",
        "bigram_document_frequency": {gram: len(ids) for gram, ids in sorted(gram_members.items())},
        "bigram_candidate_ids": dict(sorted(gram_members.items())),
        "bigram_frequency_counts_presence_once_per_candidate": True,
        "distinctive_limit": max(1, math.ceil(len(chunk_ids) * 0.10)),
        "doc_id_by_candidate": doc_by_chunk,
        "same_doc_groups": dict(sorted(doc_groups.items())),
        "same_doc_identity_rule": "first route hit doc_id; dataset_id not part of grouping",
    }


def _target_trace(
    cid: str,
    values: np.ndarray,
    query_trace: dict,
    content: str,
    contents: dict[str, str],
    pool: dict,
    feature_version: str = core.FEATURE_VERSION,
) -> dict[str, Any]:
    trace = _text_trace(content, is_query=False, feature_version=feature_version)
    text_features = {}
    for prefix in ("identifier", "number"):
        needles = set(query_trace["regex_extraction"][prefix]["unique_set"])
        if feature_version == core.ENGLISH_FEATURE_VERSION:
            extracted = trace["regex_extraction"][prefix]
            coverage = _set_coverage(needles, set(extracted["unique_set"]))
            coverage.update(needles=sorted(needles), occurrences_by_needle={
                token: [m for m in extracted["matches"] if m["needle"] == token] for token in sorted(needles)},
                aggregation="exact canonical extracted-token intersection; not substring coverage")
        else:
            coverage = _substring_coverage(needles, content, trace)
        text_features[f"{prefix}_exact_coverage"] = coverage
    query_neg = set(query_trace["literal_negations"]["unique_set"])
    content_neg = set(trace["literal_negations"]["unique_set"])
    text_features["negation_overlap_coverage"] = _set_coverage(query_neg, content_neg)
    text_features["negation_mismatch"] = {
        "query_set": sorted(query_neg),
        "content_set": sorted(content_neg),
        "intersection": sorted(query_neg & content_neg),
        "precast_value": float(
            bool(query_neg) != bool(content_neg)
            or (bool(query_neg) and not query_neg & content_neg)
        ),
    }
    for size, name in ((2, "bigram"), (3, "trigram")):
        text_features[f"query_{name}_coverage"] = _set_coverage(
            set(query_trace["ngrams"][str(size)]["unique_set"]),
            set(trace["ngrams"][str(size)]["unique_set"]),
        )
    content_bigrams = set(trace["ngrams"]["2"]["unique_set"])
    clauses = []
    for clause in query_trace["condition_split"]["retained_clauses"]:
        coverage = _set_coverage(core._ngrams(clause["quote"], 2), content_bigrams)
        clauses.append(
            {
                "query_span": clause,
                **coverage,
                "matched": bool(coverage["denominator"]) and coverage["precast_value"] >= 0.5,
            }
        )
    gate = len(clauses) > 1
    text_features["condition_coverage"] = {
        "clauses": clauses,
        "gate_open": gate,
        "numerator": sum(c["matched"] for c in clauses) if gate else 0,
        "denominator": len(clauses),
        "denominator_used": len(clauses) if gate else None,
        "precast_value": core._condition_coverage(query_trace["raw_text"], content, feature_version=feature_version),
        "aggregation": "per-query-clause bigram set matched anywhere in full content",
    }
    all_query_bigrams = set(query_trace["ngrams"]["2"]["unique_set"])
    matched = all_query_bigrams & content_bigrams
    distinctive = {
        gram
        for gram in matched
        if pool["bigram_document_frequency"][gram] <= pool["distinctive_limit"]
    }
    text_features["distinctive_query_bigram_coverage"] = {
        **_set_coverage(all_query_bigrams, distinctive),
        "distinctive_limit": pool["distinctive_limit"],
        "matched_gram_pool_counts": {
            gram: pool["bigram_document_frequency"][gram] for gram in sorted(matched)
        },
        "rejected_matched_set": sorted(matched - distinctive),
        "aggregation": "candidate-presence frequency, not within-candidate occurrence count",
    }
    doc_id = pool["doc_id_by_candidate"][cid]
    peers = []
    for peer in pool["same_doc_groups"][str(doc_id)]:
        if peer != cid:
            grams = core._ngrams(contents[peer], 2)
            intersection, union = content_bigrams & grams, content_bigrams | grams
            peers.append(
                {
                    "chunk_id": peer,
                    "intersection_count": len(intersection),
                    "union_count": len(union),
                    "jaccard": len(intersection) / len(union) if union else 0.0,
                }
            )
    text_features["same_doc"] = {
        "doc_id": doc_id,
        "peers": peers,
        "candidate_count_minus_self": len(peers),
        "max_similarity": max((p["jaccard"] for p in peers), default=0.0),
    }
    text_features["content_length_log"] = {
        "raw_length": len(content),
        "precast_value": math.log1p(len(content)),
    }
    final = dict(zip(core.FEATURE_NAMES, map(float, values), strict=True))
    same_doc = text_features["same_doc"]
    for name, value in (
        ("same_doc_candidate_count", same_doc["candidate_count_minus_self"]),
        ("same_doc_max_bigram_similarity", same_doc["max_similarity"]),
    ):
        same_doc[name] = final[name]
        if float(np.float32(value)) != final[name]:
            raise ValueError(f"pool trace does not reproduce feature {name}")
    for name, entry in text_features.items():
        if name in final:
            entry["model_input_value"] = final[name]
            if float(np.float32(entry["precast_value"])) != final[name]:
                raise ValueError(f"text trace does not reproduce feature {name}")
    route_trace = {
        source: next(
            (row for row in pool["routes"][source]["hits"] if row["chunk_id"] == cid),
            {"present": False, "raw_score": None, "effective_rank_one_based": 0},
        )
        for source in core.ROUTES
    }
    baseline = next((row for row in pool["baseline_order"] if row["chunk_id"] == cid), None)
    return {
        "status": "present",
        "semantic_classification": SEMANTIC_STATUS,
        "feature_values": final,
        "text_trace": trace,
        "text_features": text_features,
        "route_trace": route_trace,
        "baseline_trace": baseline,
        "text_value_check": "float32(precast_value) exactly equals original model input;"
        " float64 mathematical values are not claimed identical before casting",
        "aggregation_location_note": "matched_set members refer to ngrams.by_gram occurrences;"
        " matches may be contributed by different raw positions or diagnostic sentences",
    }


def trace_features(
    *,
    query: str,
    routes: dict[str, list[dict[str, Any]]],
    candidate_contents: dict[str, str],
    target_chunk_ids: Sequence[str],
    reference_ids: Sequence[str],
    reference_features: np.ndarray,
    feature_version: str = core.FEATURE_VERSION,
) -> dict[str, Any]:
    """Trace a full-pool replay; report mismatch without interpreting target rows.

    Missing target IDs are recorded and never injected. A reference mismatch leaves
    targets untraced so the caller cannot mistake provenance for verified model input.
    Input and reference arrays are never modified. No models, files or network are read.
    """
    ids, matrix = core.build_online_features(
        query=query, routes=routes, candidate_contents=candidate_contents, feature_version=feature_version
    )
    reference = np.asarray(reference_features)
    same_shape = reference.shape == matrix.shape
    finite = bool(np.isfinite(matrix).all())
    reference_finite = bool(np.isfinite(reference).all())
    same_values = same_shape and bool(np.array_equal(reference, matrix))
    same_ids, same_dtype = list(reference_ids) == ids, reference.dtype == matrix.dtype
    verified = same_ids and same_dtype and same_values and finite and reference_finite
    verification = {
        "passed": verified,
        "verified": verified,
        "ids_equal": same_ids,
        "shape_equal": same_shape,
        "dtype_equal": same_dtype,
        "values_exact_equal": same_values,
        "recomputed_finite": finite,
        "reference_finite": reference_finite,
        "recomputed_shape": list(matrix.shape),
        "reference_shape": list(reference.shape),
        "recomputed_dtype": str(matrix.dtype),
        "reference_dtype": str(reference.dtype),
        "max_abs_difference": float(
            np.max(np.abs(matrix.astype(np.float64) - reference.astype(np.float64)), initial=0.0)
        )
        if same_shape and finite and reference_finite
        else None,
        "comparison": "exact; no tolerance or rounding used",
    }
    result = {
        "schema_version": "nevir_feature_trace_v1",
        "feature_version": feature_version,
        "semantic_classification": SEMANTIC_STATUS,
        "offset_convention": "half-open Python Unicode code points",
        "verification": verification,
        "feature_dependencies": feature_dependencies(feature_version),
        "query_trace": None,
        "pool_summary": None,
        "targets": {},
    }
    if not verified:
        result["targets"] = {
            cid: {"status": "blocked_reference_mismatch"} for cid in target_chunk_ids
        }
        return result
    query_trace = _text_trace(query, is_query=True, feature_version=feature_version)
    pool = _pool_summary(routes, ids, candidate_contents)
    result.update(query_trace=query_trace, pool_summary=pool)
    by_id = {cid: row for cid, row in zip(ids, matrix, strict=True)}
    for cid in target_chunk_ids:
        result["targets"][cid] = (
            _target_trace(
                cid, by_id[cid], query_trace, candidate_contents[cid], candidate_contents, pool, feature_version
            )
            if cid in by_id
            else {"status": "missing_from_pool", "semantic_classification": SEMANTIC_STATUS}
        )
    return result
