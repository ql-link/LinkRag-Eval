#!/usr/bin/env python3
"""Score the fixed twelve authored probes using cached automatic parses; never fit on probes."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

from subject_binding_development import read_json, write_json

from linkrag_eval.retrieval.learning_to_rank.features import (
    ENGLISH_FEATURE_VERSION,
    _condition_coverage,
    _ngrams,
)
from linkrag_eval.retrieval.learning_to_rank.subject_binding import (
    cache_key,
    extract,
    score_conditions,
    text_hash,
)


def controls(scenes, cache):
    rows, categories = [], defaultdict(Counter)
    if len(scenes) != 12 or sorted(Counter(s["category"] for s in scenes).values()) != [4, 4, 4]:
        raise ValueError("expected exactly the frozen three categories of four scenes")
    for scene in scenes:
        paragraphs = [extract(t, read_json(cache / f"{cache_key(t)}.json")) for t in scene["paragraphs"]]
        result = {"probe_id": scene["probe_id"], "category": scene["category"], "queries": []}
        for kind in ("queries", "paraphrases"):
            for index, text in enumerate(scene[kind]):
                q = extract(text, read_json(cache / f"{cache_key(text)}.json"), query=True)
                scores = [score_conditions(q, p) for p in paragraphs]
                intended = scene["intended_entity_preferences"][index]
                a, b = scores[intended]["entity"], scores[1 - intended]["entity"]
                relation = "missing" if a is None or b is None else "intended" if a > b else "opposite" if a < b else "tie"
                character = []
                for body in scene["paragraphs"]:
                    c = {f"query_char_{n}gram_coverage": len(_ngrams(text, n) & _ngrams(body, n)) / len(_ngrams(text, n))
                         if _ngrams(text, n) else 0.0 for n in (2, 3)}
                    c["condition_coverage"] = _condition_coverage(text, body, feature_version=ENGLISH_FEATURE_VERSION)
                    character.append(c)
                result["queries"].append({"kind": kind, "index": index, "query_supported": q["query_structure_supported"],
                                          "conditions": q["conditions"], "query_issues": q["issues"], "scores": scores,
                                          "paragraph_issues": [p["issues"] for p in paragraphs], "character_features": character,
                                          "character_features_equal": character[0] == character[1], "authored_intention_relation": relation})
                if kind == "queries":
                    categories[scene["category"]][relation] += 1
        original = result["queries"][:2]
        rewrites = result["queries"][2:]
        result["rewrite_scores_unchanged"] = all(a["scores"] == b["scores"] for a, b in zip(original, rewrites, strict=True))
        rows.append(result)
    return {"scenes": rows, "summary": {"scene_count": 12, "original_queries": 24, "rewrite_queries": 24,
            "categories": {k: dict(v) for k, v in categories.items()},
            "rewrite_scores_unchanged_scenes": sum(r["rewrite_scores_unchanged"] for r in rows),
            "character_feature_equal_original_pairs": sum(q["character_features_equal"] for r in rows for q in r["queries"][:2]),
            "status": "AI-authored diagnostic intentions only; semantic correctness pending humans",
            "full_38_comparison": "not available: synthetic probes have no actual three-route recall scores"}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scenes", type=Path, required=True)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--spec", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    if args.out.exists():
        raise ValueError("refuse to overwrite control results")
    spec = read_json(args.spec)
    if text_hash(Path(spec["extraction_source"]).read_text()) != spec["extraction_source_sha256"]:
        raise ValueError("frozen extraction changed")
    result = controls(read_json(args.scenes), args.cache)
    write_json(args.out, result)
    print(result["summary"])


if __name__ == "__main__":
    main()
