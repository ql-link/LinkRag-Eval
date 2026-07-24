#!/usr/bin/env python3
"""Select an exposure-isolated, scenario-balanced Blind v2 from judged candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from linkrag_eval.retrieval.candidate_routing import has_exact_identifier


SCENARIOS = (
    "similar_docs",
    "multi_constraint",
    "number_time",
    "alias",
    "dense_paraphrase",
    "short_keyword",
    "exact_identifier",
)
QUESTION_TYPES = {
    "similar_docs": "paraphrase",
    "multi_constraint": "longtail",
    "number_time": "keyword",
    "alias": "paraphrase",
    "dense_paraphrase": "paraphrase",
    "short_keyword": "keyword",
    "exact_identifier": "keyword",
}
DATASET_IDS = [992000, 992001, 992002, 992003]


def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _stable(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round-dir", type=Path, required=True)
    parser.add_argument("--exposed-references", type=Path, required=True)
    parser.add_argument("--exposed-queries", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--per-scenario", type=int, default=40)
    parser.add_argument(
        "--scenario",
        action="append",
        choices=SCENARIOS,
        default=[],
        help="limit frozen output to selected scenarios; repeat as needed",
    )
    parser.add_argument("--output-name", default="blind_v2.jsonl")
    parser.add_argument("--blind-version", default="blind-v2")
    args = parser.parse_args()
    selected_scenarios = tuple(args.scenario or SCENARIOS)

    targets = {row["query_id"]: row for row in _read(args.round_dir / "targets.jsonl")}
    queries = {row["query_id"]: row for row in _read(args.round_dir / "generated_queries.jsonl")}
    pools = {
        row["query_id"]: row for row in _read(args.round_dir / "validation" / "blinded_pools.jsonl")
    }
    decisions = {
        row["query_id"]: row
        for path in sorted((args.round_dir / "validation" / "decisions").glob("pool_*.jsonl"))
        for row in _read(path)
    }
    if not (set(targets) == set(queries) == set(pools) == set(decisions)):
        raise SystemExit("generation and judgment coverage mismatch")

    exposed_chunks = {
        str(chunk_id)
        for row in _read(args.exposed_references)
        for chunk_id in row.get("expected_chunk_ids", [])
    }
    exposed_queries = {str(row["query"]).strip() for row in _read(args.exposed_queries)}
    accepted: dict[str, list[dict]] = {scenario: [] for scenario in selected_scenarios}
    rejected = Counter()
    used_chunks: set[str] = set()
    used_queries: set[str] = set()
    judge_models = Counter()

    for query_id in sorted(decisions, key=_stable):
        decision = decisions[query_id]
        judge_models[str(decision.get("judge_model") or "unknown")] += 1
        selected = decision.get("relevant_chunk_id")
        if selected is None:
            rejected["judge_null"] += 1
            continue
        selected = str(selected)
        if selected in exposed_chunks:
            rejected["historically_exposed_evidence"] += 1
            continue
        candidate = next(
            (row for row in pools[query_id]["candidates"] if str(row["chunk_id"]) == selected),
            None,
        )
        if candidate is None:
            raise SystemExit(f"selected candidate missing: {query_id}")
        query = str(queries[query_id]["query"]).strip()
        if query in exposed_queries:
            rejected["historically_exposed_query"] += 1
            continue
        if query in used_queries:
            rejected["duplicate_query"] += 1
            continue
        if selected in used_chunks:
            rejected["duplicate_evidence"] += 1
            continue
        scenario = str(targets[query_id]["type_hint"])
        if scenario not in accepted:
            rejected["scenario_not_selected"] += 1
            continue
        if scenario == "exact_identifier" and not has_exact_identifier(query):
            rejected["invalid_exact_identifier"] += 1
            continue
        used_queries.add(query)
        used_chunks.add(selected)
        accepted[scenario].append(
            {
                "id": query_id,
                "query": query,
                "user_id": 990001,
                "dataset_ids": DATASET_IDS,
                "expected_chunk_ids": [selected],
                "expected_doc_ids": [int(candidate["doc_id"])],
                "golden_answer": None,
                "type": QUESTION_TYPES[scenario],
                "note": (
                    f"role=blind; source={queries[query_id].get('generator_model')}-{args.blind_version}; "
                    f"type_hint={scenario}; independently_validated=true; "
                    f"judge_model={decision.get('judge_model')}; exposure_isolated=true"
                ),
                "relevance_grades": {selected: 3},
            }
        )

    selected_rows = []
    available = {}
    for scenario in selected_scenarios:
        rows = sorted(accepted[scenario], key=lambda row: _stable(row["id"]))
        available[scenario] = len(rows)
        if len(rows) < args.per_scenario:
            raise SystemExit(f"insufficient validated {scenario}: {len(rows)}/{args.per_scenario}")
        selected_rows.extend(rows[: args.per_scenario])
    selected_rows.sort(key=lambda row: _stable(row["id"]))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    output = args.out_dir / args.output_name
    output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected_rows),
        encoding="utf-8",
    )
    report = {
        "status": "frozen",
        "samples": len(selected_rows),
        "per_scenario": args.per_scenario,
        "selected_scenarios": list(selected_scenarios),
        "blind_version": args.blind_version,
        "scenario_counts": dict(
            Counter(row["note"].split("type_hint=", 1)[1].split(";", 1)[0] for row in selected_rows)
        ),
        "validated_available": available,
        "rejected": dict(rejected),
        "judge_models": dict(judge_models),
        "chunk_only": all(len(row["expected_chunk_ids"]) == 1 for row in selected_rows),
        "query_unique": len({row["query"] for row in selected_rows}) == len(selected_rows),
        "evidence_unique": len({row["expected_chunk_ids"][0] for row in selected_rows})
        == len(selected_rows),
        "evidence_overlap_with_history": len(
            {row["expected_chunk_ids"][0] for row in selected_rows} & exposed_chunks
        ),
        "query_overlap_with_history": len(
            {row["query"] for row in selected_rows} & exposed_queries
        ),
        "output": str(output),
    }
    (args.out_dir / "build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
