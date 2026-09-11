"""Evaluate continuous BGE logits with the unchanged L1/L2 metric functions."""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

from linkrag_eval.retrieval.learning_to_rank.llm_judge import (
    check_exact,
    l2_rankers,
    read_rows,
    score_maps,
    write_json,
    write_rows,
)


def main():
    root = Path(__file__).resolve().parent
    repo = root.parents[2]
    spec = importlib.util.spec_from_file_location("judge_pilot", repo / "scripts/llm_judge_pilot.py")
    pilot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pilot)
    config = json.loads((root / "execution-config.json").read_text())
    summary = json.loads((root / "summary.json").read_text())
    inputs, raw = read_rows(root / "items.jsonl"), read_rows(root / "scores.jsonl")

    def key(row):
        return row["role"], row["source_query_id"], row["chunk_id"]

    indexed = {key(r): r for r in raw}
    if (len(indexed) != len(raw) or set(indexed) != {key(r) for r in inputs}
            or len(raw) != summary["items"] or summary["unavailable"] != 0):
        raise ValueError("BGE score scope differs from the fixed inputs")
    for row in inputs:
        score = indexed[key(row)]
        if (score["levels"] != row["levels"] or score["status"] != "available"
                or score["model"] != config["model"]["repository"]
                or score["revision"] != config["model"]["revision"]
                or type(score["score"]) not in (float, int) or not math.isfinite(score["score"])):
            raise ValueError("BGE score metadata or real-valued logit is invalid")

    comparison = {}
    for role in ("development", "confirmation"):
        baseline = read_rows(pilot.RUN / f"baseline/{role}/scores.jsonl")
        if role == "development":
            check_exact(baseline, read_rows(pilot.SAVED))
        base = score_maps(baseline)
        stage1 = score_maps(read_rows(
            pilot.RUN / f"items-stage1-top20/{role}/stage1-{role}.jsonl"))
        comparison[role] = {}
        for level in ("l1", "l2"):
            source = read_rows(repo / config["inputs"][role][level])
            scores = {}
            for item in source:
                row = indexed[(role, item["source_query_id"], item["chunk_id"])]
                scores.setdefault(item["source_query_id"], {})[item["chunk_id"]] = row["score"]
            for top_k in ([None] if level == "l1" else config["evaluation"]["l2_K"]):
                name = level if top_k is None else f"{level}-k{top_k}"
                out = root / f"{role}-{name}"
                out.mkdir(exist_ok=False)
                if top_k is None:
                    result, per_query = pilot.evaluation_report(role, baseline, scores, summary)
                else:
                    rankers, orders, trigger = l2_rankers(base, stage1, scores, top_k=top_k)
                    result, per_query = pilot.listwise_report(role, baseline, rankers, orders, summary)
                    result.update(K=top_k, trigger=trigger)
                    write_rows(out / "orders.jsonl", [{"source_query_id": qid, "orders": {
                        name: rows[qid] for name, rows in orders.items()}} for qid in base])
                result.update(model=config["model"]["repository"],
                              model_revision=config["model"]["revision"],
                              score_type="continuous raw cross-encoder logit", status="completed")
                write_json(out / "results.json", result)
                for population, rows in per_query.items():
                    write_rows(out / f"{population}-per-query.jsonl", rows)
                comparison[role][name] = {key: result[key] for key in
                                         ("official", "human_v5") if key in result}
    write_json(root / "comparison.json", comparison)
    write_json(root / "validation.json", {
        "exact_score_scope": True, "all_finite_logits": True,
        "model_revision_matches_config": True, "development_E0_exact_replay": True,
        "score_rows": len(raw), "roles": ["development", "confirmation"],
        "human_population": "unchanged frozen v5; 52 development queries",
        "evaluation_functions": ["evaluation_report", "listwise_report", "l2_rankers"],
        "llm_integer_cache_used": False, "test_used": False,
    })
    print(json.dumps({role: {name: (values["official"]["judge"]["strict_correct"] if name == "l1"
        else values["official"]["rankers"]["stage1_judge"]["pairwise"]["strict_correct"])
        for name, values in methods.items()} for role, methods in comparison.items()},
        ensure_ascii=False))


if __name__ == "__main__":
    main()
