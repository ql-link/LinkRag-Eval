"""Prepare the accepted NevIR LTR split without retrieval or model access."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from linkrag_eval.runners.nevir_ltr_data import prepare_nevir_ltr

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "runs/post_recall/nevir-ltr-validation-20260907/data-preparation"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "data/post_recall/nevir")
    parser.add_argument(
        "--train-development-proposal", type=Path,
        default=DATA / "split-proposal.train-development.json",
    )
    parser.add_argument(
        "--confirmation-proposal", type=Path, default=DATA / "split-proposal.confirmation.json",
    )
    parser.add_argument("--out", type=Path, default=DATA / "experiment")
    args = parser.parse_args()
    metadata = prepare_nevir_ltr(
        source_dir=args.source_dir, train_development_proposal=args.train_development_proposal,
        confirmation_proposal=args.confirmation_proposal, output_dir=args.out,
    )
    # Only aggregate counts and paths are displayed; no held-out query, body, or label examples.
    print(json.dumps({
        "preparation_status": metadata["preparation_status"], "output_dir": str(args.out.resolve()),
        "identity": metadata["identity"], "counts": metadata["counts"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
