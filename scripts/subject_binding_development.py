#!/usr/bin/env python3
"""Explicit development-only replay, parser-input preparation and binding coverage; no fits."""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np

from linkrag_eval.retrieval.learning_to_rank.features import (
    ENGLISH_FEATURE_VERSION,
    FEATURE_VERSION,
)
from linkrag_eval.retrieval.learning_to_rank.online import validate_production_bundle
from linkrag_eval.retrieval.learning_to_rank.pairwise_training import (
    _development_predictions,
    load_dataset,
)
from linkrag_eval.retrieval.learning_to_rank.subject_binding import (
    RULE_VERSION,
    cache_key,
    extract,
    score_conditions,
    text_hash,
    training_signal_gate,
    validate_rules_version,
)


def read_json(path):
    return json.loads(Path(path).read_text())


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def rules_from_config(config):
    version = validate_rules_version(config.get("rules_version", RULE_VERSION))
    frozen = read_json(config["extraction_spec"])
    if frozen.get("rules_version", frozen["parser_contract"]["extraction_rules"]) != version:
        raise ValueError("configured extraction rules differ from execution spec")
    if frozen["extraction_source_sha256"] != text_hash(Path(frozen["extraction_source"]).read_text()):
        raise ValueError("frozen extraction source changed")
    return version


def distribution(values):
    return {str(k): v for k, v in sorted(Counter(values).items(), key=lambda kv: str(kv[0]))}


def check_summary(dataset, historical):
    for k, value in historical.items():
        if k not in {"feature_compute_seconds", "feature_version", "feature_rules_version"} and dataset.summary[k] != value:
            raise ValueError(f"historical dataset mismatch: {dataset.role}/{k}")


def development(config):
    paths = config["inputs"]["development"]
    dataset = load_dataset(role="development", feature_version=ENGLISH_FEATURE_VERSION,
                           **{k: Path(v) for k, v in paths.items()})
    historical = read_json(config["english_selection"])
    check_summary(dataset, historical["development"])
    if (len(dataset.queries), len(dataset.blocks), sum(len(q.chunk_ids) for q in dataset.queries)) != (76, 74, 10465):
        raise ValueError("fixed development scope changed")
    return dataset


def prepare(config, out):
    import lightgbm as lgb
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    dev = development(config)
    cache = np.load(config["english_dev_features"])
    if set(cache.files) != {q.query_id for q in dev.queries}:
        raise ValueError("historical feature cache query IDs differ")
    for q in dev.queries:
        if not np.array_equal(q.features, cache[q.query_id]):
            raise ValueError("historical English feature values differ")
    versions = {"B": FEATURE_VERSION, "english": ENGLISH_FEATURE_VERSION}
    replay = {}
    for name, version in versions.items():
        dataset = dev if name == "english" else load_dataset(
            role="development", feature_version=version,
            **{k: Path(v) for k, v in config["inputs"]["development"].items()})
        bundle = Path(config["history"][name]["model"])
        validation = validate_production_bundle(bundle)
        # Historical model dimensions/version are validated before direct offline prediction.
        booster = lgb.Booster(model_file=str(bundle / "model.txt"))
        predicted = _development_predictions(dataset, booster)
        old = read_rows(config["history"][name]["predictions"])
        if predicted != old:
            raise ValueError(f"historical {name} full-pool predictions/order differ")
        with (out / f"{name}-predictions.jsonl").open("x") as f:
            f.writelines(json.dumps(r) + "\n" for r in predicted)
        replay[name] = {"bundle": validation, "full_predictions_exact": True,
                        "relations": distribution(r["preference_relation"] for r in predicted)}
    records = {}
    for q in dev.queries:
        records[("query", q.query)] = {"kind": "query", "text": q.query}
        for text in q.method_view["candidate_contents"].values():
            records[("paragraph", text)] = {"kind": "paragraph", "text": text}
    with (out / "texts.jsonl").open("x", encoding="utf-8") as f:
        f.writelines(json.dumps(v, ensure_ascii=False) + "\n" for v in records.values())
    write_json(out / "preparation.json", {"status": "complete", "roles_read": ["development"],
               "dataset": dev.summary, "candidate_rows": 10465, "replay": replay,
               "historical_english_features_exact": True, "elapsed_seconds": time.perf_counter() - started,
               "text_lengths": {kind: {"count": len(values), "min": min(values), "max": max(values),
                                       "median": float(np.median(values)), "p95": float(np.percentile(values, 95))}
                   for kind in ("query", "paragraph")
                   for values in [[len(t) for k, t in records if k == kind]]}})
    print(json.dumps({"replay": {k: v["relations"] for k, v in replay.items()}, "parser_inputs": len(records)}))


def analyze(config, cache, out):
    version = rules_from_config(config)
    out.mkdir(parents=True, exist_ok=False)
    dev = development(config)
    records, queries, paragraphs = [], {}, {}
    timings = []
    for q in dev.queries:
        started = time.perf_counter()
        qhash = text_hash(q.query)
        if qhash not in queries:
            queries[qhash] = extract(q.query, read_json(cache / f"{cache_key(q.query)}.json"), query=True, rules_version=version)
        parsed_query = queries[qhash]
        for cid in q.chunk_ids:
            text = q.method_view["candidate_contents"][cid]
            phash = text_hash(text)
            if phash not in paragraphs:
                paragraphs[phash] = extract(text, read_json(cache / f"{cache_key(text)}.json"), rules_version=version)
            parsed = paragraphs[phash]
            records.append({"source_query_id": q.query_id, "chunk_id": cid,
                            "query_text_sha256": qhash, "paragraph_text_sha256": phash,
                            "scores": score_conditions(parsed_query, parsed)})
        timings.append({"query_id": q.query_id, "full_pool_records": len(q.chunk_ids),
                        "load_extract_match_seconds": time.perf_counter() - started})
    by_id = {(r["source_query_id"], r["chunk_id"]): r["scores"] for r in records}
    query_stats = []
    for q in dev.queries:
        parsed = queries[text_hash(q.query)]
        pairs = [by_id.get((q.query_id, q.supervision[k])) for k in ("preferred_chunk_id", "other_chunk_id")]
        query_stats.append({"source_query_id": q.query_id, "source_group_id": q.supervision["source_group_id"],
                            "pair_id": q.supervision["pair_id"], "condition_count": parsed["condition_count"],
                            "query_structure_supported": parsed["query_structure_supported"],
                            "issues": parsed["issues"], "jointly_covered": not q.exclusion_reasons,
                            "target_scores": pairs,
                            "direct_difference": {name: None if any(p is None or p[name] is None for p in pairs)
                                                   else pairs[0][name] - pairs[1][name]
                                                  for name in ("loose", "sentence", "entity")}})
    support = sum(q["query_structure_supported"] for q in query_stats)
    counts = {name: distribution(r["scores"][name] for r in records)
              for name in ("query_structure_supported", "extraction_incomplete", "loose", "sentence", "entity")}
    gate = training_signal_gate({q.query_id: [by_id[q.query_id, cid] for cid in q.chunk_ids]
                                 for q in dev.queries})
    summary = {"stage": "A", "status": "complete", "scheduled_queries": 76, "candidate_rows": len(records),
               "eligible_queries": 74, "covered_pairs": 37, "sources": 19,
               "supported_queries": support, "query_condition_counts": distribution(q["condition_count"] for q in query_stats),
               "unsupported_reasons": dict(Counter(i["reason"] for q in query_stats for i in q["issues"])),
               "score_distributions": counts, "candidate_availability": distribution(r["scores"]["availability"] for r in records),
               "target_direct_difference_counts": {n: distribution(q["direct_difference"][n] for q in query_stats) for n in ("loose", "sentence", "entity")},
               "unique_paragraphs": len(paragraphs), "paragraph_status": distribution(p["status"] for p in paragraphs.values()),
               "paragraph_issue_counts": dict(Counter(i["reason"] for p in paragraphs.values() for i in p["issues"])),
               "rules_version": version, "training_signal_gate": gate,
               "stage_b_allowed": gate["allowed"], "stage_b_stop_reason": gate["stop_reason"],
               "semantic_accuracy": "not measured by this mechanical extraction check",
               "load_extract_match_seconds": sum(t["load_extract_match_seconds"] for t in timings)}
    for filename, rows in (("full-pool-scores.jsonl", records), ("query-coverage.jsonl", query_stats), ("timings.jsonl", timings),
                           ("query-structures.jsonl", list(queries.values())), ("paragraph-facts.jsonl", list(paragraphs.values()))):
        with (out / filename).open("x") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    write_json(out / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["prepare", "analyze"])
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--cache", type=Path)
    args = p.parse_args()
    config = read_json(args.config)
    rules_from_config(config)
    if args.action == "prepare":
        prepare(config, args.out)
    else:
        if args.cache is None:
            p.error("analyze requires --cache")
        analyze(config, args.cache, args.out)


if __name__ == "__main__":
    main()
