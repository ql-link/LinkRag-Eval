#!/usr/bin/env python3
"""Build an ID/hash-only provenance peel for C-MTEB CmedqaRetrieval.

The compact C-MTEB corpus is compared by exact parsed text against both the
pinned C-MTEB DuRetrieval corpus and the pinned upstream cMedQA2 questions and
answers. The same run separately verifies the complete pinned DuRetrieval
corpus/query/qrels entity. No source text is written to the output package.

This is a provenance/exposure crosswalk, not a replacement medical corpus.
The authoritative medical input remains the pinned upstream cMedQA2 release.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

PACKAGE_VERSION = "ROBUST-FUSION-CMEDQA-PROVENANCE-PEEL-2026-08-28-v2"
CMEDQA_DATA_REVISION = "cd540c506dae1cf9e9a59c3e06f42030d54e7301"
CMEDQA_QRELS_REVISION = "279d737f36c731c8ff6e2b055f31fe02216fa23d"
DURETRIEVAL_REVISION = "a1a333e290fe30b10f3f56498e3a0d911a693ced"
DURETRIEVAL_QRELS_REVISION = "497b7bd1bbb25cb3757ff34d95a8be50a3de2279"
CMEDQA2_REVISION = "85feb9278c3ae552c591205cbf3e828368c91f8f"

INPUTS = {
    "cmedqa_corpus": {
        "relative_path": (
            "C-MTEB_CmedqaRetrieval/"
            f"{CMEDQA_DATA_REVISION}/data/"
            "corpus-00000-of-00001-a3949861f65a3226.parquet"
        ),
        "sha256": "15191de1c0568805e536d5eb4f4233e105b819390ae816d88d42102f89b5261a",
        "rows": 100_001,
    },
    "cmedqa_queries": {
        "relative_path": (
            "C-MTEB_CmedqaRetrieval/"
            f"{CMEDQA_DATA_REVISION}/data/"
            "queries-00000-of-00001-daeedab899d3c839.parquet"
        ),
        "sha256": "ffa5d51ae6fed9de058fca0842cdb30d7c7e3a252e8ccb868c9c2710a06c3f4c",
        "rows": 3_999,
    },
    "cmedqa_qrels": {
        "relative_path": (
            "C-MTEB_CmedqaRetrieval-qrels/"
            f"{CMEDQA_QRELS_REVISION}/data/"
            "dev-00000-of-00001-57fb84a4aceaa695.parquet"
        ),
        "sha256": "4d104c611091a9d366c4b279a92a6849565529761253cd91003af99e0608d387",
        "rows": 7_449,
    },
    "duretrieval_corpus": {
        "relative_path": (
            "C-MTEB_DuRetrieval/"
            f"{DURETRIEVAL_REVISION}/data/"
            "corpus-00000-of-00001-19b9e924cb33e4d5.parquet"
        ),
        "sha256": "d4b4eb51b63549ef0851a15fc63c2a61b703dce95e3727b535a08f7ba1d14424",
        "rows": 100_001,
    },
    "duretrieval_queries": {
        "relative_path": (
            "C-MTEB_DuRetrieval/"
            f"{DURETRIEVAL_REVISION}/data/"
            "queries-00000-of-00001-7c7edb40be6b560c.parquet"
        ),
        "sha256": "62ac55e764bffd4ffceb0aa51e7a536a0e5932f23c8606566906db6a9efb4b94",
        "rows": 2_000,
    },
    "duretrieval_qrels": {
        "relative_path": (
            "C-MTEB_DuRetrieval-qrels/"
            f"{DURETRIEVAL_QRELS_REVISION}/data/"
            "dev-00000-of-00001-d3c385852a7c0c9d.parquet"
        ),
        "sha256": "c87e7c16f535a98b29ee0ebf6977639c793e3bd149c04634a1810273cfd3c3e5",
        "rows": 9_839,
    },
    "cmedqa2_questions": {
        "relative_path": f"zhangsheng93_cMedQA2/{CMEDQA2_REVISION}/question.zip",
        "sha256": "df4738599e20deed824757c40f78c5a3b752b262d2c730de72d69449d95daa89",
        "rows": 120_000,
    },
    "cmedqa2_answers": {
        "relative_path": f"zhangsheng93_cMedQA2/{CMEDQA2_REVISION}/answer.zip",
        "sha256": "5fd8ba9f049e419929ff3526e7b6902aaa2caba43cf207ea086b1d7755394485",
        "rows": 226_266,
    },
    "cmedqa2_dev_candidates": {
        "relative_path": f"zhangsheng93_cMedQA2/{CMEDQA2_REVISION}/dev_candidates.zip",
        "sha256": "3301b55cddbdd512f6960fb4ed72fd27c7b00db2ed3f10e88d0c2764263a379e",
        "rows": 400_000,
    },
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_id_sort(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value)


def join_ids(values: Iterable[str]) -> str:
    return ";".join(sorted(set(values), key=stable_id_sort))


def assert_unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise RuntimeError(f"{label} contains duplicate IDs")


def read_parquet(path: Path, columns: list[str], expected_rows: int) -> dict[str, list[Any]]:
    table = pq.read_table(path, columns=columns)
    if table.num_rows != expected_rows:
        raise RuntimeError(f"unexpected row count for {path}: {table.num_rows} != {expected_rows}")
    return table.to_pydict()


def open_zip_csv(path: Path, member: str) -> tuple[zipfile.ZipFile, io.TextIOWrapper]:
    archive = zipfile.ZipFile(path)
    if archive.namelist() != [member]:
        archive.close()
        raise RuntimeError(f"unexpected members in {path}: {archive.namelist()}")
    raw = archive.open(member)
    text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
    return archive, text


def write_tsv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def classify_source(in_du: bool, in_cmedqa2: bool) -> str:
    if in_du and in_cmedqa2:
        return "both_exact"
    if in_du:
        return "duretrieval_exact_only"
    if in_cmedqa2:
        return "cmedqa2_exact_only"
    return "unresolved_neither"


def verify_inputs(public_root: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for name, spec in INPUTS.items():
        path = public_root / str(spec["relative_path"])
        if not path.is_file():
            raise FileNotFoundError(path)
        actual = sha256_file(path)
        if actual != spec["sha256"]:
            raise RuntimeError(f"SHA-256 mismatch for {name}: {actual} != {spec['sha256']}")
        paths[name] = path
    return paths


def load_upstream(
    paths: dict[str, Path],
) -> tuple[
    dict[str, list[str]],
    dict[str, list[tuple[str, str]]],
    dict[str, str],
    dict[str, str],
    set[tuple[str, str]],
    dict[str, int],
]:
    csv.field_size_limit(64 * 1024 * 1024)
    question_ids_by_hash: dict[str, list[str]] = defaultdict(list)
    question_hash_by_id: dict[str, str] = {}
    archive, text = open_zip_csv(paths["cmedqa2_questions"], "question.csv")
    try:
        for row in csv.DictReader(text):
            qid = row["question_id"]
            digest = sha256_text(row["content"])
            question_ids_by_hash[digest].append(qid)
            question_hash_by_id[qid] = digest
    finally:
        text.close()
        archive.close()
    if len(question_hash_by_id) != INPUTS["cmedqa2_questions"]["rows"]:
        raise RuntimeError("unexpected upstream question count or duplicate question ID")

    answer_rows_by_hash: dict[str, list[tuple[str, str]]] = defaultdict(list)
    answer_hash_by_id: dict[str, str] = {}
    archive, text = open_zip_csv(paths["cmedqa2_answers"], "answer.csv")
    try:
        for row in csv.DictReader(text):
            aid = row["ans_id"]
            qid = row["question_id"]
            digest = sha256_text(row["content"])
            answer_rows_by_hash[digest].append((aid, qid))
            answer_hash_by_id[aid] = digest
    finally:
        text.close()
        archive.close()
    if len(answer_hash_by_id) != INPUTS["cmedqa2_answers"]["rows"]:
        raise RuntimeError("unexpected upstream answer count or duplicate answer ID")

    positive_text_pairs: set[tuple[str, str]] = set()
    candidate_rows = 0
    positive_rows = 0
    archive, text = open_zip_csv(paths["cmedqa2_dev_candidates"], "dev_candidates.txt")
    try:
        for row in csv.DictReader(text):
            candidate_rows += 1
            if row["label"] != "1":
                continue
            positive_rows += 1
            qhash = question_hash_by_id[row["question_id"]]
            ahash = answer_hash_by_id[row["ans_id"]]
            positive_text_pairs.add((qhash, ahash))
    finally:
        text.close()
        archive.close()
    if candidate_rows != INPUTS["cmedqa2_dev_candidates"]["rows"]:
        raise RuntimeError(f"unexpected upstream Dev candidate count: {candidate_rows}")

    stats = {
        "upstream_question_rows": len(question_hash_by_id),
        "upstream_unique_question_texts": len(question_ids_by_hash),
        "upstream_answer_rows": len(answer_hash_by_id),
        "upstream_unique_answer_texts": len(answer_rows_by_hash),
        "upstream_dev_candidate_rows": candidate_rows,
        "upstream_dev_positive_rows": positive_rows,
        "upstream_dev_unique_positive_text_pairs": len(positive_text_pairs),
    }
    return (
        question_ids_by_hash,
        answer_rows_by_hash,
        question_hash_by_id,
        answer_hash_by_id,
        positive_text_pairs,
        stats,
    )


def build_package(public_root: Path, output: Path) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise RuntimeError(f"refusing to overwrite non-empty output directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    paths = verify_inputs(public_root)
    (
        upstream_question_ids_by_hash,
        upstream_answer_rows_by_hash,
        _upstream_question_hash_by_id,
        _upstream_answer_hash_by_id,
        upstream_dev_positive_text_pairs,
        upstream_stats,
    ) = load_upstream(paths)

    du = read_parquet(
        paths["duretrieval_corpus"],
        ["id", "text"],
        int(INPUTS["duretrieval_corpus"]["rows"]),
    )
    du_ids = [str(value) for value in du["id"]]
    assert_unique(du_ids, "DuRetrieval corpus")
    if any(value is None or not str(value) for value in du["text"]):
        raise RuntimeError("DuRetrieval corpus contains null or empty text")
    du_ids_by_hash: dict[str, list[str]] = defaultdict(list)
    for pid, text in zip(du_ids, du["text"]):
        du_ids_by_hash[sha256_text(str(text))].append(pid)
    if len(du_ids_by_hash) != len(du_ids):
        raise RuntimeError("DuRetrieval corpus contains duplicate exact text")

    du_queries = read_parquet(
        paths["duretrieval_queries"],
        ["id", "text"],
        int(INPUTS["duretrieval_queries"]["rows"]),
    )
    du_query_ids = [str(value) for value in du_queries["id"]]
    assert_unique(du_query_ids, "DuRetrieval queries")
    if any(value is None or not str(value) for value in du_queries["text"]):
        raise RuntimeError("DuRetrieval queries contain null or empty text")
    du_query_hashes = [sha256_text(str(value)) for value in du_queries["text"]]
    if len(set(du_query_hashes)) != len(du_query_hashes):
        raise RuntimeError("DuRetrieval queries contain duplicate exact text")

    du_qrels = read_parquet(
        paths["duretrieval_qrels"],
        ["qid", "pid", "score"],
        int(INPUTS["duretrieval_qrels"]["rows"]),
    )
    du_qrel_pairs: set[tuple[str, str]] = set()
    du_qrels_per_query: Counter[str] = Counter()
    du_scores: set[int] = set()
    du_corpus_id_set = set(du_ids)
    du_query_id_set = set(du_query_ids)
    for qid_value, pid_value, score_value in zip(
        du_qrels["qid"], du_qrels["pid"], du_qrels["score"]
    ):
        qid = str(qid_value)
        pid = str(pid_value)
        pair = (qid, pid)
        if pair in du_qrel_pairs:
            raise RuntimeError(f"duplicate DuRetrieval qrel pair: {pair}")
        if qid not in du_query_id_set or pid not in du_corpus_id_set:
            raise RuntimeError(f"DuRetrieval qrel references missing entity: {pair}")
        du_qrel_pairs.add(pair)
        du_qrels_per_query[qid] += 1
        du_scores.add(int(score_value))
    if set(du_qrels_per_query) != du_query_id_set:
        raise RuntimeError("not every DuRetrieval query has at least one qrel")
    if du_scores != {1}:
        raise RuntimeError(f"unexpected DuRetrieval qrel scores: {sorted(du_scores)}")

    duretrieval_integrity = {
        "status": "INDEPENDENT_COMPLETE_PINNED_ENTITY",
        "scope": (
            "the complete pinned C-MTEB compact revision; this does not claim that the "
            "upstream approximately eight-million-passage DuReader corpus is present"
        ),
        "corpus_rows": len(du_ids),
        "corpus_unique_ids": len(du_corpus_id_set),
        "corpus_unique_exact_texts": len(du_ids_by_hash),
        "query_rows": len(du_query_ids),
        "query_unique_ids": len(du_query_id_set),
        "query_unique_exact_texts": len(set(du_query_hashes)),
        "qrel_rows": len(du_qrel_pairs),
        "qrel_unique_pairs": len(du_qrel_pairs),
        "qrel_score_values": sorted(du_scores),
        "qrels_per_query_min": min(du_qrels_per_query.values()),
        "qrels_per_query_max": max(du_qrels_per_query.values()),
        "multi_positive_queries": sum(value > 1 for value in du_qrels_per_query.values()),
        "rows_removed": {"corpus": 0, "queries": 0, "qrels": 0},
        "overlap_based_subtraction": False,
        "cross_dataset_merge": False,
        "role": (
            "independent complete auxiliary robustness dataset outside the current "
            "mandatory six-cell Gate denominator"
        ),
        "gate_role_change_requires_new_pre_gate_protocol_version": True,
    }

    corpus = read_parquet(
        paths["cmedqa_corpus"],
        ["id", "text"],
        int(INPUTS["cmedqa_corpus"]["rows"]),
    )
    corpus_ids = [str(value) for value in corpus["id"]]
    assert_unique(corpus_ids, "C-MTEB Cmedqa corpus")
    corpus_lookup: dict[str, dict[str, Any]] = {}
    corpus_rows: list[dict[str, Any]] = []
    corpus_class_counts: Counter[str] = Counter()
    for pid, text in zip(corpus_ids, corpus["text"]):
        digest = sha256_text(str(text))
        du_matches = du_ids_by_hash.get(digest, [])
        answer_matches = upstream_answer_rows_by_hash.get(digest, [])
        source_class = classify_source(bool(du_matches), bool(answer_matches))
        answer_ids = [aid for aid, _qid in answer_matches]
        answer_qids = [qid for _aid, qid in answer_matches]
        row = {
            "cmedqa_pid": pid,
            "content_sha256": digest,
            "source_class": source_class,
            "duretrieval_pid_match_count": len(du_matches),
            "duretrieval_pid_matches": join_ids(du_matches),
            "upstream_answer_match_count": len(answer_ids),
            "upstream_answer_id_matches": join_ids(answer_ids),
            "upstream_answer_question_id_matches": join_ids(answer_qids),
        }
        corpus_rows.append(row)
        corpus_lookup[pid] = row
        corpus_class_counts[source_class] += 1

    corpus_path = output / "corpus_source_classification.tsv"
    write_tsv(
        corpus_path,
        [
            "cmedqa_pid",
            "content_sha256",
            "source_class",
            "duretrieval_pid_match_count",
            "duretrieval_pid_matches",
            "upstream_answer_match_count",
            "upstream_answer_id_matches",
            "upstream_answer_question_id_matches",
        ],
        sorted(corpus_rows, key=lambda row: stable_id_sort(str(row["cmedqa_pid"]))),
    )

    queries = read_parquet(
        paths["cmedqa_queries"],
        ["id", "text"],
        int(INPUTS["cmedqa_queries"]["rows"]),
    )
    query_ids = [str(value) for value in queries["id"]]
    assert_unique(query_ids, "C-MTEB Cmedqa queries")
    query_lookup: dict[str, dict[str, Any]] = {}
    query_rows: list[dict[str, Any]] = []
    query_mapping_counts: Counter[str] = Counter()
    for qid, text in zip(query_ids, queries["text"]):
        digest = sha256_text(str(text))
        matches = upstream_question_ids_by_hash.get(digest, [])
        status = "exact_upstream_text_match" if matches else "unresolved_exact_text"
        row = {
            "cmedqa_qid": qid,
            "query_sha256": digest,
            "mapping_status": status,
            "upstream_question_match_count": len(matches),
            "upstream_question_id_matches": join_ids(matches),
        }
        query_rows.append(row)
        query_lookup[qid] = row
        query_mapping_counts[status] += 1

    query_path = output / "query_upstream_crosswalk.tsv"
    write_tsv(
        query_path,
        [
            "cmedqa_qid",
            "query_sha256",
            "mapping_status",
            "upstream_question_match_count",
            "upstream_question_id_matches",
        ],
        sorted(query_rows, key=lambda row: stable_id_sort(str(row["cmedqa_qid"]))),
    )

    qrels = read_parquet(
        paths["cmedqa_qrels"],
        ["qid", "pid", "score"],
        int(INPUTS["cmedqa_qrels"]["rows"]),
    )
    qrel_rows: list[dict[str, Any]] = []
    qrel_pair_counts: Counter[str] = Counter()
    qrel_unique_pids: set[str] = set()
    qrel_unique_pids_with_upstream_match: set[str] = set()
    seen_qrel_pairs: set[tuple[str, str]] = set()
    for qid_value, pid_value, score in zip(qrels["qid"], qrels["pid"], qrels["score"]):
        qid = str(qid_value)
        pid = str(pid_value)
        pair = (qid, pid)
        if pair in seen_qrel_pairs:
            raise RuntimeError(f"duplicate C-MTEB qrel pair: {pair}")
        seen_qrel_pairs.add(pair)
        if qid not in query_lookup or pid not in corpus_lookup:
            raise RuntimeError(f"qrel references missing entity: {pair}")
        query_row = query_lookup[qid]
        corpus_row = corpus_lookup[pid]
        question_matches = set(str(query_row["upstream_question_id_matches"]).split(";"))
        question_matches.discard("")
        answer_matches = upstream_answer_rows_by_hash.get(str(corpus_row["content_sha256"]), [])
        compatible_answer_ids = [aid for aid, answer_qid in answer_matches if answer_qid in question_matches]
        exact_positive_text_pair = (
            str(query_row["query_sha256"]),
            str(corpus_row["content_sha256"]),
        ) in upstream_dev_positive_text_pairs
        pair_status = (
            "exact_upstream_dev_positive_text_pair"
            if exact_positive_text_pair
            else "not_exact_upstream_dev_positive_text_pair"
        )
        qrel_rows.append(
            {
                "cmedqa_qid": qid,
                "cmedqa_pid": pid,
                "score": int(score),
                "query_sha256": query_row["query_sha256"],
                "pid_content_sha256": corpus_row["content_sha256"],
                "upstream_question_id_matches": query_row["upstream_question_id_matches"],
                "upstream_answer_id_matches": corpus_row["upstream_answer_id_matches"],
                "compatible_upstream_answer_match_count": len(compatible_answer_ids),
                "compatible_upstream_answer_id_matches": join_ids(compatible_answer_ids),
                "upstream_dev_positive_text_pair_status": pair_status,
            }
        )
        qrel_pair_counts[pair_status] += 1
        qrel_unique_pids.add(pid)
        if int(corpus_row["upstream_answer_match_count"]) > 0:
            qrel_unique_pids_with_upstream_match.add(pid)

    qrel_path = output / "qrel_upstream_crosswalk.tsv"
    write_tsv(
        qrel_path,
        [
            "cmedqa_qid",
            "cmedqa_pid",
            "score",
            "query_sha256",
            "pid_content_sha256",
            "upstream_question_id_matches",
            "upstream_answer_id_matches",
            "compatible_upstream_answer_match_count",
            "compatible_upstream_answer_id_matches",
            "upstream_dev_positive_text_pair_status",
        ],
        sorted(
            qrel_rows,
            key=lambda row: (
                stable_id_sort(str(row["cmedqa_qid"])),
                stable_id_sort(str(row["cmedqa_pid"])),
            ),
        ),
    )

    manifest = {
        "package_version": PACKAGE_VERSION,
        "generated_on": "2026-08-28",
        "purpose": "ID/hash-only exact-text provenance peel and exposure crosswalk",
        "match_basis": (
            "SHA-256 of the exact Unicode string returned by the pinned parquet/CSV parsers; "
            "no case folding, Unicode normalization, whitespace normalization, or fuzzy matching"
        ),
        "revisions": {
            "cmedqa_data": CMEDQA_DATA_REVISION,
            "cmedqa_qrels": CMEDQA_QRELS_REVISION,
            "duretrieval": DURETRIEVAL_REVISION,
            "duretrieval_qrels": DURETRIEVAL_QRELS_REVISION,
            "upstream_cmedqa2": CMEDQA2_REVISION,
        },
        "inputs": {
            name: {
                "relative_path": spec["relative_path"],
                "sha256": spec["sha256"],
                "rows": spec["rows"],
            }
            for name, spec in INPUTS.items()
        },
        "counts": {
            "corpus_rows": len(corpus_rows),
            "corpus_source_class": dict(sorted(corpus_class_counts.items())),
            "corpus_exact_duretrieval_any": (
                corpus_class_counts["duretrieval_exact_only"] + corpus_class_counts["both_exact"]
            ),
            "corpus_exact_upstream_answer_any": (
                corpus_class_counts["cmedqa2_exact_only"] + corpus_class_counts["both_exact"]
            ),
            "query_rows": len(query_rows),
            "query_mapping_status": dict(sorted(query_mapping_counts.items())),
            "qrel_rows": len(qrel_rows),
            "qrel_positive_text_pair_status": dict(sorted(qrel_pair_counts.items())),
            "qrel_unique_pids": len(qrel_unique_pids),
            "qrel_unique_pids_with_exact_upstream_answer_text": len(
                qrel_unique_pids_with_upstream_match
            ),
            **upstream_stats,
        },
        "duretrieval_integrity": duretrieval_integrity,
        "unresolved_neither_policy": {
            "rows": corpus_class_counts["unresolved_neither"],
            "single_undivided_audit_class": True,
            "qrel_linkage_creates_subclass": False,
            "normalization_or_fuzzy_remapping": False,
            "special_annotation_or_review": False,
            "deletion": False,
            "formal_semantic_use": False,
        },
        "source_classes": {
            "duretrieval_exact_only": "exactly matches DuRetrieval text, not an upstream cMedQA2 answer text",
            "cmedqa2_exact_only": "exactly matches an upstream cMedQA2 answer text, not DuRetrieval text",
            "both_exact": "exactly matches texts in both sources; cannot be assigned exclusively",
            "unresolved_neither": "does not exactly match either pinned comparison source",
        },
        "limitations": [
            "The peel establishes exact-text membership, not the undocumented C-MTEB generation procedure.",
            "both_exact rows cannot be assigned exclusively to one source.",
            "unresolved_neither does not prove that a row is unrelated to cMedQA2; it may reflect an undocumented transformation.",
            "All unresolved_neither rows remain one undivided audit class; qrel linkage does not create a special subgroup or action.",
            "No DuRetrieval corpus, query, or qrel row is removed or merged because of overlap observed in C-MTEB Cmedqa.",
            "The package contains no source text and is not a usable medical corpus.",
            "Formal medical retrieval must load the pinned upstream cMedQA2 source, not a peeled C-MTEB subset.",
        ],
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(canonical_json(manifest) + "\n", encoding="utf-8")

    readme = f"""# C-MTEB Cmedqa provenance peel v2

Record: `{PACKAGE_VERSION}`

This local, gitignored package classifies every compact C-MTEB Cmedqa corpus row by
exact text membership in the pinned C-MTEB DuRetrieval corpus and pinned upstream
cMedQA2 answers. It also maps compact queries/qrels to upstream IDs where exact
text permits. It deliberately stores IDs and SHA-256 values only, never source text.

Corpus classification:

- `duretrieval_exact_only`: {corpus_class_counts['duretrieval_exact_only']:,}
- `cmedqa2_exact_only`: {corpus_class_counts['cmedqa2_exact_only']:,}
- `both_exact`: {corpus_class_counts['both_exact']:,}
- `unresolved_neither`: {corpus_class_counts['unresolved_neither']:,}

The `both_exact` rows must not be forced into a single source. All 2,536
`unresolved_neither` rows remain one undivided audit class: no qrel-linked
subgroup, normalization/fuzzy remapping, special annotation, deletion, or formal
semantic use is created for them.

DuRetrieval is preserved independently as the complete pinned C-MTEB compact
entity: 100,001 corpus rows, 2,000 queries, and 9,839 qrels, with zero rows
removed or merged because of Cmedqa overlap. This statement does not claim that
the upstream approximately eight-million-passage DuReader corpus is present.

This package is an audit/exposure crosswalk, not the formal medical corpus.
"""
    readme_path = output / "README.md"
    readme_path.write_text(readme, encoding="utf-8")

    checksum_targets = [corpus_path, query_path, qrel_path, manifest_path, readme_path]
    checksum_path = output / "manifest.sha256"
    checksum_path.write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in sorted(checksum_targets)),
        encoding="utf-8",
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--public-root",
        type=Path,
        default=Path("data/robust_fusion/public"),
        help="Root containing the pinned public datasets",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/robust_fusion/derived/cmedqa_provenance_peel_v2"),
        help="New, empty output directory",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = build_package(args.public_root, args.output)
    except Exception as exc:  # noqa: BLE001 - CLI should emit one concise failure
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(canonical_json({"output": str(args.output), "counts": manifest["counts"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
