#!/usr/bin/env python3
"""Build the final 4x150 chunk-level balanced golden and leakage-safe splits."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


DATASET_IDS = [992000, 992001, 992002, 992003]
SCENARIOS = ("short_keyword", "exact_identifier", "long_sparse", "dense_paraphrase")
QUESTION_TYPES = {
    "short_keyword": "keyword",
    "exact_identifier": "keyword",
    "long_sparse": "longtail",
    "dense_paraphrase": "paraphrase",
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _sample_from_judgment(row: dict[str, Any]) -> dict[str, Any]:
    candidate = row["candidate"]
    chunk_id = str(candidate["chunk_id"])
    return {
        "id": row["query_id"],
        "query": row["query"],
        "user_id": 990001,
        "dataset_ids": DATASET_IDS,
        "expected_chunk_ids": [chunk_id],
        "expected_doc_ids": [candidate["doc_id"]],
        "golden_answer": None,
        "type": QUESTION_TYPES[row["type_hint"]],
        "note": (
            f"role={row.get('role', 'realistic')}; source={row.get('source', '')}; "
            f"type_hint={row['type_hint']}; hard_reason={row.get('hard_reason') or ''}"
        ),
        "relevance_grades": {chunk_id: 3},
    }


def _sample_from_validation(row: dict[str, Any]) -> dict[str, Any]:
    chunk_id = str(row["expected_chunk_ids"][0])
    return {
        "id": row["query_id"],
        "query": row["query"],
        "user_id": 990001,
        "dataset_ids": DATASET_IDS,
        "expected_chunk_ids": [chunk_id],
        "expected_doc_ids": row["expected_doc_ids"],
        "golden_answer": None,
        "type": QUESTION_TYPES[row["type_hint"]],
        "note": (
            f"role={row.get('role', 'realistic')}; source={row.get('source', '')}; "
            f"type_hint={row['type_hint']}; independently_validated=true"
        ),
        "relevance_grades": {chunk_id: 3},
    }


def _stable_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _split_by_document(samples: list[dict[str, Any]], tune_size: int) -> tuple[list, list]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        groups[str(sample["expected_doc_ids"][0])].append(sample)
    ordered = sorted(groups.items(), key=lambda item: _stable_key(item[0]))

    # Exact subset-sum keeps a source document in one split while preserving
    # the required scenario balance.
    choices: dict[int, list[int]] = {0: []}
    for index, (_, group) in enumerate(ordered):
        size = len(group)
        for total, selected in list(choices.items())[::-1]:
            next_total = total + size
            if next_total <= tune_size and next_total not in choices:
                choices[next_total] = selected + [index]
    if tune_size not in choices:
        raise SystemExit(f"cannot create document-safe tune split of {tune_size}")
    tune_indexes = set(choices[tune_size])
    tune = [sample for index in tune_indexes for sample in ordered[index][1]]
    blind = [sample for index in range(len(ordered)) if index not in tune_indexes for sample in ordered[index][1]]
    return sorted(tune, key=lambda row: row["id"]), sorted(blind, key=lambda row: row["id"])


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    base_paths = {
        "short_keyword": args.base_dir / "top50_extension_v2/short_keyword/judgments_combined.jsonl",
        "long_sparse": args.base_dir / "top50_extension_v2/long_sparse/judgments_combined.jsonl",
        "dense_paraphrase": args.base_dir / "top50_extension_v2/dense_paraphrase/judgments_combined.jsonl",
    }
    validation_paths: dict[str, list[Path]] = {
        "short_keyword": args.base_dir / "grounded_supplements/short_keyword/validation/accepted_samples.jsonl",
        "exact_identifier": [
            args.base_dir / "grounded_exact_replacement/validation/accepted_samples.jsonl",
            args.base_dir / "grounded_exact_extension/validation/accepted_samples.jsonl",
        ],
        "long_sparse": args.base_dir / "grounded_supplements/long_sparse/validation/accepted_samples.jsonl",
        "dense_paraphrase": args.base_dir / "grounded_supplements/dense_paraphrase/validation/accepted_samples.jsonl",
    }
    validation_paths = {
        scenario: paths if isinstance(paths, list) else [paths]
        for scenario, paths in validation_paths.items()
    }

    selected_by_scenario: dict[str, list[dict[str, Any]]] = {}
    source_counts: dict[str, dict[str, int]] = {}
    for scenario in SCENARIOS:
        base_samples: list[dict[str, Any]] = []
        if scenario in base_paths:
            positives = [
                row
                for row in _read_jsonl(base_paths[scenario])
                if row.get("relevant") and int(row.get("grade", 0) or 0) > 0
            ]
            if len({row["query_id"] for row in positives}) != len(positives):
                raise SystemExit(f"multiple canonical positives in base set: {scenario}")
            base_samples = [_sample_from_judgment(row) for row in positives]
        validation_samples = [
            _sample_from_validation(row)
            for path in validation_paths[scenario]
            for row in _read_jsonl(path)
        ]
        needed = 150 - len(base_samples)
        if needed < 0 or len(validation_samples) < needed:
            raise SystemExit(
                f"insufficient accepted samples for {scenario}: base={len(base_samples)} "
                f"validation={len(validation_samples)} needed={needed}"
            )
        supplement = sorted(validation_samples, key=lambda row: _stable_key(row["id"]))[:needed]
        selected = base_samples + supplement
        if len(selected) != 150 or len({row["id"] for row in selected}) != 150:
            raise SystemExit(f"invalid scenario total: {scenario}")
        selected_by_scenario[scenario] = selected
        source_counts[scenario] = {"existing": len(base_samples), "validated_new": len(supplement)}

    args.out_dir.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, Any]] = []
    tune_rows: list[dict[str, Any]] = []
    blind_rows: list[dict[str, Any]] = []
    split_counts: dict[str, dict[str, int]] = {}
    for scenario in SCENARIOS:
        rows = selected_by_scenario[scenario]
        tune, blind = _split_by_document(rows, 105)
        if len(tune) != 105 or len(blind) != 45:
            raise SystemExit(f"invalid split sizes: {scenario}")
        tune_docs = {str(row["expected_doc_ids"][0]) for row in tune}
        blind_docs = {str(row["expected_doc_ids"][0]) for row in blind}
        if tune_docs & blind_docs:
            raise SystemExit(f"document leakage between splits: {scenario}")
        _write_jsonl(args.out_dir / f"{scenario}_tune_105.jsonl", tune)
        _write_jsonl(args.out_dir / f"{scenario}_blind_45.jsonl", blind)
        all_rows.extend(rows)
        tune_rows.extend(tune)
        blind_rows.extend(blind)
        split_counts[scenario] = {"tune": len(tune), "blind": len(blind)}

    _write_jsonl(args.out_dir / "balanced_all_600.jsonl", all_rows)
    _write_jsonl(args.out_dir / "balanced_tune_420.jsonl", tune_rows)
    _write_jsonl(args.out_dir / "balanced_blind_180.jsonl", blind_rows)
    report = {
        "total": len(all_rows),
        "tune": len(tune_rows),
        "blind": len(blind_rows),
        "scenario_sources": source_counts,
        "scenario_splits": split_counts,
        "dataset_scope": DATASET_IDS,
        "reference_granularity": "chunk_only",
        "split_rule": "document-grouped deterministic 70/30 per scenario",
    }
    (args.out_dir / "build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
