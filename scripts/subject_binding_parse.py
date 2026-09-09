#!/usr/bin/env python3
"""Parse explicit plaintext records in the isolated spaCy environment, with full text caching."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import resource
import time
from pathlib import Path

from linkrag_eval.retrieval.learning_to_rank.subject_binding import (
    PARSER_MODEL,
    PARSER_VERSION,
    SPACY_VERSION,
    cache_key,
    extract,
    parser_contract,
    serialize_doc,
    text_hash,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--texts", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError("refuse to overwrite parse run")
    args.out.mkdir(parents=True)
    args.cache.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    import spacy
    if spacy.__version__ != SPACY_VERSION or importlib.metadata.version(PARSER_MODEL) != PARSER_VERSION:
        raise ValueError("fixed parser version mismatch")
    nlp = spacy.load(PARSER_MODEL, exclude=["ner"])
    initialization = time.perf_counter() - started
    nlp.config.to_disk(args.out / "parser-config.cfg")
    rows = [json.loads(x) for x in args.texts.read_text().splitlines() if x.strip()]
    if any(set(r) != {"text", "kind"} or r["kind"] not in {"query", "paragraph"} for r in rows):
        raise ValueError("parser only accepts plaintext and text role; no IDs or labels")
    nlp.max_length = max(nlp.max_length, max((len(r["text"]) for r in rows), default=0) + 1)
    stats = {"contract": parser_contract(), "initialization_seconds": initialization,
             "threads": 1, "excluded_components": ["ner"], "input_records": len(rows),
             "max_length": nlp.max_length, "cache_hits": 0, "cache_misses": 0,
             "parse_seconds": {"query": 0.0, "paragraph": 0.0},
             "extraction_seconds": {"query": 0.0, "paragraph": 0.0}, "failures": []}
    with (args.out / "results.jsonl").open("x", encoding="utf-8") as results:
        for index, row in enumerate(rows):
            text, kind = row["text"], row["kind"]
            key = cache_key(text)
            path = args.cache / f"{key}.json"
            try:
                if path.exists():
                    parsed = json.loads(path.read_text())
                    stats["cache_hits"] += 1
                else:
                    t = time.perf_counter()
                    parsed = serialize_doc(nlp(text))
                    stats["parse_seconds"][kind] += time.perf_counter() - t
                    path.write_text(json.dumps(parsed, ensure_ascii=False) + "\n")
                    stats["cache_misses"] += 1
                t = time.perf_counter()
                extracted = extract(text, parsed, query=kind == "query")
                stats["extraction_seconds"][kind] += time.perf_counter() - t
                output = {"text_sha256": text_hash(text), "cache_key": key, "kind": kind,
                          "extracted": extracted, "program_status": "ok"}
            except Exception as error:  # noqa: BLE001 — batch boundary records failure, then exits nonzero
                output = {"text_sha256": text_hash(text), "cache_key": key, "kind": kind,
                          "program_status": "failed", "error_type": type(error).__name__, "error": str(error)}
                stats["failures"].append({"record_index": index, **output})
            results.write(json.dumps(output, ensure_ascii=False) + "\n")
            if index % 100 == 0:
                print(f"Parsed {index + 1}/{len(rows)}; failures={len(stats['failures'])}", flush=True)
    stats.update(elapsed_seconds=time.perf_counter() - started,
                 peak_rss_platform_units=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                 unique_text_count=len({text_hash(r["text"]) for r in rows}),
                 unique_query_texts=len({r["text"] for r in rows if r["kind"] == "query"}),
                 unique_paragraph_texts=len({r["text"] for r in rows if r["kind"] == "paragraph"}),
                 cache_bytes=sum(p.stat().st_size for p in args.cache.glob('*.json')))
    (args.out / "summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: stats[k] for k in ("input_records", "cache_hits", "cache_misses", "elapsed_seconds")}), flush=True)
    if stats["failures"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
