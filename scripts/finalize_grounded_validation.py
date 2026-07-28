#!/usr/bin/env python3
"""Merge blinded canonical decisions and build accepted chunk-level samples."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=Path, required=True)
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--decisions-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--spark-log-dir", type=Path, required=True)
    args = parser.parse_args()

    seeds = {row["query_id"]: row for row in _read_jsonl(args.seeds)}
    pools = {row["query_id"]: row for row in _read_jsonl(args.pool)}
    decisions: list[dict[str, Any]] = []
    for path in sorted(args.decisions_dir.glob("decisions_[0-9][0-9][0-9].jsonl")):
        batch = path.stem.removeprefix("decisions_")
        fallback_log = args.spark_log_dir / f"pool_{batch}_mini.log"
        actual_model = "gpt-5.4-mini" if fallback_log.exists() else "gpt-5.3-codex-spark"
        for row in _read_jsonl(path):
            row["judge_model"] = actual_model
            decisions.append(row)

    decision_ids = [row["query_id"] for row in decisions]
    if len(decisions) != len(pools) or set(decision_ids) != set(pools):
        raise SystemExit(
            f"decision coverage mismatch: expected={len(pools)} actual={len(decisions)}"
        )
    if len(set(decision_ids)) != len(decision_ids):
        raise SystemExit("duplicate query decisions")

    accepted: list[dict[str, Any]] = []
    target_matches = 0
    model_counts: dict[str, int] = {}
    for decision in decisions:
        query_id = decision["query_id"]
        selected = decision.get("relevant_chunk_id")
        model = decision["judge_model"]
        model_counts[model] = model_counts.get(model, 0) + 1
        if selected is None:
            continue
        candidate = next(
            (
                item
                for item in pools[query_id]["candidates"]
                if str(item["chunk_id"]) == str(selected)
            ),
            None,
        )
        if candidate is None:
            raise SystemExit(f"selected chunk is not in blinded pool: {query_id} {selected}")
        seed = seeds[query_id]
        target_matches += int(str(selected) == str(seed["target_chunk_id"]))
        accepted.append(
            {
                "query_id": query_id,
                "query": seed["query"],
                "role": seed.get("role", "realistic"),
                "source": seed.get("source"),
                "type_hint": seed["type_hint"],
                "hard_reason": seed.get("hard_reason"),
                "dataset_ids": [candidate["dataset_id"]],
                "expected_chunk_ids": [str(selected)],
                "expected_doc_ids": [str(candidate["doc_id"])],
                "evidence_span": decision.get("evidence_span", ""),
                "label_reason": decision.get("reason", ""),
                "judge_model": model,
                "generation_target_match": str(selected) == str(seed["target_chunk_id"]),
            }
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "decisions_merged.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in decisions),
        encoding="utf-8",
    )
    (args.out_dir / "accepted_samples.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in accepted),
        encoding="utf-8",
    )
    report = {
        "queries": len(pools),
        "accepted": len(accepted),
        "unresolved": len(pools) - len(accepted),
        "acceptance_rate": len(accepted) / len(pools) if pools else 0.0,
        "generation_target_matches": target_matches,
        "alternate_canonical_chunks": len(accepted) - target_matches,
        "judge_models": model_counts,
        "labeling_rule": "blinded candidate comparison; generated target metadata hidden",
        "reference_granularity": "chunk",
    }
    (args.out_dir / "validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
