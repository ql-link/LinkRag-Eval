"""Prepare the fixed official NevIR Test corpus without printing row content."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from linkrag_eval.store.ids import eval_chunk_id

DATASET_ID = 995301
DOC_ID_BASE = 9953010000000
QDRANT_PREFIX = "eval_nevir_test_20260910"
SEED = 20260907
EXPECTED_SHA256 = "5eb79ec32e82ff17ef6c2f47b75baca182013053ed74672d426bbc338af05d67"


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists() and any(args.out.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty output: {args.out}")
    raw = args.source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA256:
        raise ValueError("official Test SHA-256 differs from the frozen source")
    source = [json.loads(line) for line in raw.decode().splitlines() if line]
    if len(source) != 1383 or any(
        set(row) != {"id", "WorkerId", "q1", "q2", "doc1", "doc2"} for row in source
    ):
        raise ValueError("official Test shape differs")
    if len({row["id"] for row in source}) != len(source):
        raise ValueError("duplicate official pair ID")

    texts = list(dict.fromkeys(row[key] for row in source for key in ("doc1", "doc2")))
    if len(texts) != 2081:
        raise ValueError("official Test exact-document count differs")
    random.Random(SEED).shuffle(texts)
    corpus = []
    mapping = []
    by_text = {}
    for index, content in enumerate(texts):
        passage_id = f"tp{index:06d}"
        doc_id = DOC_ID_BASE + index
        identity = {
            "source_passage_id": passage_id,
            "dataset_id": DATASET_ID,
            "doc_id": doc_id,
            "chunk_id": eval_chunk_id(DATASET_ID, doc_id, 0),
        }
        corpus.append({"source_passage_id": passage_id, "content": content})
        mapping.append(identity)
        by_text[content] = identity

    slots = [(row, direction) for row in source for direction in ("q1", "q2")]
    random.Random(SEED + 1).shuffle(slots)
    queries = []
    supervision = []
    for index, (row, direction) in enumerate(slots):
        query_id = f"tq{index:06d}"
        preferred, other = ("doc1", "doc2") if direction == "q1" else ("doc2", "doc1")
        preferred_identity = by_text[row[preferred]]
        other_identity = by_text[row[other]]
        conflict = row["q1"] == row["q2"]
        queries.append({"source_query_id": query_id, "query": row[direction]})
        supervision.append(
            {
                "source_query_id": query_id,
                "role": "test",
                "source_group_id": f"test-source-{row['id'].rsplit('-', 1)[0]}",
                "pair_id": row["id"],
                "direction": direction,
                "preferred_chunk_id": preferred_identity["chunk_id"],
                "other_chunk_id": other_identity["chunk_id"],
                "preferred_passage_id": preferred_identity["source_passage_id"],
                "other_passage_id": other_identity["source_passage_id"],
                "official_label_available": True,
                "structural_conflict": conflict,
                "semantic_uncertain": False,
                "label_basis": "official_NevIR_q1_prefers_doc1_q2_prefers_doc2",
                "issue_reasons": ["identical_query_text_opposite_preferences_same_pair"]
                if conflict
                else [],
                "semantic_review_status": "not_semantically_reviewed",
                "semantic_issue_scope": "none_recorded",
                "prior_exposure": "official_test_unseen_by_model_selection",
                "exposure_basis": None,
                "source_split": "test",
                "source_row_index_zero_based": source.index(row),
            }
        )

    args.out.mkdir(parents=True, exist_ok=True)
    write_rows(args.out / "prepared/corpus.jsonl", corpus)
    write_rows(args.out / "prepared/passage-mapping.jsonl", mapping)
    write_rows(args.out / "prepared/test/queries.jsonl", queries)
    write_rows(args.out / "prepared/test/supervision.jsonl", supervision)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    metadata = {
        "format": "nevir-test-candidates-v1",
        "preparation_status": "complete",
        "prepared_utc": datetime.now(UTC).isoformat(),
        "code_revision": revision,
        "identity": {
            "dataset_id": DATASET_ID,
            "doc_id_base": DOC_ID_BASE,
            "qdrant_prefix": QDRANT_PREFIX,
            "corpus_count": len(corpus),
        },
        "counts": {
            "test": {
                "pair_count": len(source),
                "query_count": len(queries),
                "source_group_count": len({row["source_group_id"] for row in supervision}),
                "structural_conflict_query_count": sum(
                    row["structural_conflict"] for row in supervision
                ),
                "semantic_uncertain_query_count": 0,
                "semantic_review_status_counts": dict(
                    Counter(row["semantic_review_status"] for row in supervision)
                ),
            }
        },
        "source": {
            "repository": "orionweller/NevIR",
            "revision": "6263585072ce3b435ed09658613553fbf4e74184",
            "file": "test.jsonl",
            "sha256": EXPECTED_SHA256,
        },
        "anonymization": {
            "seed": SEED,
            "passage_order": "Random(seed).shuffle(exact unique Test bodies)",
            "query_order": "Random(seed + 1).shuffle(all Test query slots)",
        },
        "supervision_policy": {
            "official_preferences": "preserved; q1 prefers doc1; q2 prefers doc2",
            "background_candidates": "unjudged; never inferred negative",
            "test_access": "machine-only aggregate evaluation after frozen config",
        },
        "preparation_remote_requests": 0,
    }
    (args.out / "run.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "complete",
                "pair_count": len(source),
                "query_count": len(queries),
                "corpus_count": len(corpus),
                "structural_conflict_query_count": metadata["counts"]["test"][
                    "structural_conflict_query_count"
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
