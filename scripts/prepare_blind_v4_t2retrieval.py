#!/usr/bin/env python3
"""从固定 revision 的 T2Retrieval 构造真实 Query Tune/Blind v4 候选集。"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq

from linkrag_eval.golden.provenance import QueryProvenance
from linkrag_eval.store.ids import content_hash, eval_chunk_id


DATASET_REVISION = "8731a845f1bf500a4f111cf1070785c793d10e64"
QRELS_REVISION = "1c83b8d1544e529875e3f6930f3a1fcf749a8e97"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--dataset-id", type=int, default=993100)
    parser.add_argument("--doc-id-base", type=int, default=99310000001)
    parser.add_argument("--tune-count", type=int, default=300)
    parser.add_argument("--blind-count", type=int, default=500)
    parser.add_argument("--corpus-count", type=int, default=20000)
    parser.add_argument("--max-content-chars", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260724)
    args = parser.parse_args()
    source = Path(args.source_dir)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    corpus_path = next(source.glob("corpus-*.parquet"))
    queries_path = next(source.glob("queries-*.parquet"))
    qrels_path = next(source.glob("dev-*.parquet"))
    corpus_table = pq.read_table(corpus_path)
    queries_table = pq.read_table(queries_path)
    qrels_table = pq.read_table(qrels_path)
    corpus = dict(zip(corpus_table["id"].to_pylist(), corpus_table["text"].to_pylist()))
    queries = dict(zip(queries_table["id"].to_pylist(), queries_table["text"].to_pylist()))
    qrels: dict[str, dict[str, int]] = defaultdict(dict)
    for qid, pid, score in zip(
        qrels_table["qid"].to_pylist(),
        qrels_table["pid"].to_pylist(),
        qrels_table["score"].to_pylist(),
    ):
        if int(score) > 0 and pid in corpus and qid in queries:
            qrels[str(qid)][str(pid)] = int(score)

    safe_pids = {pid for pid, text in corpus.items() if len(str(text)) <= args.max_content_chars}
    qrels = {
        qid: {pid: score for pid, score in judged.items() if pid in safe_pids}
        for qid, judged in qrels.items()
    }
    qrels = {qid: judged for qid, judged in qrels.items() if judged}
    eligible = sorted(qrels, key=lambda qid: (_stable_hash(qid), qid))
    needed = args.tune_count + args.blind_count
    if len(eligible) < needed:
        raise ValueError(f"eligible queries {len(eligible)} < {needed}")
    selected = eligible[:needed]
    tune_qids = selected[: args.tune_count]
    blind_qids = selected[args.tune_count :]
    positive_pids = {pid for qid in selected for pid in qrels[qid]}
    remaining = sorted(safe_pids - positive_pids)
    random.Random(args.seed).shuffle(remaining)
    corpus_pids = sorted(positive_pids) + remaining[: max(0, args.corpus_count - len(positive_pids))]
    if len(corpus_pids) < len(positive_pids):
        raise ValueError("corpus_count 小于正例 passage 数")
    doc_by_pid = {pid: args.doc_id_base + index for index, pid in enumerate(corpus_pids)}
    chunk_by_pid = {
        pid: eval_chunk_id(args.dataset_id, doc_by_pid[pid], 0) for pid in corpus_pids
    }
    chunks = [
        {
            "dataset_id": args.dataset_id,
            "doc_id": doc_by_pid[pid],
            "ordinal": 0,
            "content": corpus[pid],
            "content_hash": content_hash(corpus[pid]),
            "chunk_id": chunk_by_pid[pid],
            "metadata": {
                "source_type": "opensource",
                "source_name": "C-MTEB/T2Retrieval",
                "source_record_id": pid,
                "source_revision": DATASET_REVISION,
                "license": "Apache-2.0",
            },
        }
        for pid in corpus_pids
    ]

    def golden(qid: str, split: str) -> dict:
        query = str(queries[qid]).strip()
        pids = sorted(qrels[qid])
        provenance = QueryProvenance(
            source_kind="opensource",
            source_name="C-MTEB/T2Retrieval",
            source_record_id=qid,
            domain="general_web_search",
            scenario="real_search_query",
            canonical_query=query,
            dataset_version=f"{DATASET_REVISION}+qrels:{QRELS_REVISION}",
            license="Apache-2.0",
        )
        return {
            "id": f"t2retrieval-{split}-{qid}",
            "query": query,
            "user_id": 990001,
            "dataset_ids": [args.dataset_id],
            "expected_chunk_ids": [chunk_by_pid[pid] for pid in pids],
            "expected_doc_ids": [doc_by_pid[pid] for pid in pids],
            "golden_answer": None,
            "type": "keyword",
            "note": f"opensource:T2Retrieval;split={split};official_qrels",
            "relevance_grades": {chunk_by_pid[pid]: qrels[qid][pid] for pid in pids},
            "provenance": provenance.to_dict(),
            "scenario": "real_search_query",
        }

    tune = [golden(qid, "tune") for qid in tune_qids]
    blind = [golden(qid, "blind_v4") for qid in blind_qids]
    seeds = [
        {
            "seed_id": row["id"],
            "query": row["query"],
            "source": "C-MTEB/T2Retrieval",
            "domain": "general_web_search",
            "type_hint": "short_keyword",
            "dataset_ids": [args.dataset_id],
            "provenance": row["provenance"],
        }
        for row in [*tune, *blind]
    ]
    _write_jsonl(out / "chunk_records.jsonl", chunks)
    _write_jsonl(out / "tune_300.jsonl", tune)
    _write_jsonl(out / "blind_v4_candidate_500.jsonl", blind)
    _write_jsonl(out / "query_seeds_800.jsonl", seeds)
    (out / "candidate_contents.json").write_text(
        json.dumps({row["chunk_id"]: row["content"] for row in chunks}, ensure_ascii=False),
        encoding="utf-8",
    )
    manifest = {
        "source": "C-MTEB/T2Retrieval",
        "dataset_revision": DATASET_REVISION,
        "qrels_revision": QRELS_REVISION,
        "license": "Apache-2.0",
        "dataset_id": args.dataset_id,
        "corpus_count": len(chunks),
        "max_content_chars": args.max_content_chars,
        "tune_count": len(tune),
        "blind_count": len(blind),
        "positive_qrels": sum(len(row["expected_chunk_ids"]) for row in [*tune, *blind]),
        "multi_positive_queries": sum(len(row["expected_chunk_ids"]) > 1 for row in [*tune, *blind]),
        "artifacts": {
            name: hashlib.sha256((out / name).read_bytes()).hexdigest()
            for name in (
                "chunk_records.jsonl",
                "tune_300.jsonl",
                "blind_v4_candidate_500.jsonl",
                "query_seeds_800.jsonl",
            )
        },
        "candidate_contents_sha256": hashlib.sha256(
            (out / "candidate_contents.json").read_bytes()
        ).hexdigest(),
    }
    (out / "source_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def _stable_hash(value: str) -> str:
    return hashlib.sha256(f"blind-v4-split\n{value}".encode("utf-8")).hexdigest()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
