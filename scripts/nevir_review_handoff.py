#!/usr/bin/env python3
"""Package the original N05 review forms; only explicit development inputs are read."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from linkrag_eval.retrieval.learning_to_rank.nevir_diagnostics import _review_bodies
from linkrag_eval.retrieval.learning_to_rank.nevir_evaluation import prepare_inputs
from linkrag_eval.retrieval.learning_to_rank.review_handoff import create_handoff, read_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--source-review", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    p = args.experiment_dir
    mapping = read_rows(p / "prepared/passage-mapping.jsonl")
    prepared = prepare_inputs(
        read_rows(p / "prepared/development/queries.jsonl"),
        read_rows(p / "prepared/development/supervision.jsonl"),
        read_rows(p / "candidates/development/inputs.jsonl"), mapping, role="development",
    )
    assert len(prepared) == 76
    assert sum(r["candidate_count"] for r in prepared) == 10465
    assert sum(r["coverage_state"] == "both" for r in prepared) == 74
    bodies = _review_bodies(prepared, mapping, p / "prepared/corpus.jsonl")
    result = create_handoff(args.source_review, prepared, bodies, args.out)
    print(json.dumps({"packages": {name: item["zip_path"]
                                 for name, item in result["packages"].items()},
                      "human_submissions_received": 0}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
