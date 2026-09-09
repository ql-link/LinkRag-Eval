#!/usr/bin/env python3
"""Receive original N05 human exports or prepare neutral disagreements; never adjudicate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from linkrag_eval.retrieval.learning_to_rank.review_handoff import (
    REVIEWERS,
    disagreement_material,
    receive_submission,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    receive = sub.add_parser("receive")
    receive.add_argument("--reviewer", choices=REVIEWERS, required=True)
    receive.add_argument("--submission", type=Path, required=True)
    receive.add_argument("--out", type=Path, required=True)
    align = sub.add_parser("disagreements")
    align.add_argument("--reviewer-1-intake", type=Path, required=True)
    align.add_argument("--reviewer-2-intake", type=Path, required=True)
    align.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "receive":
        result = receive_submission(args.submission, args.manifest, args.reviewer, args.out)
    else:
        result = disagreement_material(args.manifest, args.reviewer_1_intake, args.reviewer_2_intake, args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("errors"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
