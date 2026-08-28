#!/usr/bin/env python3
"""Build ID/hash-only Gate A eligibility and exclusion manifests.

This script closes split-level exposure and query-family leakage for the pinned
T2Ranking and cMedQA2 entities, while preserving the pinned DuRetrieval entity
as an independent auxiliary dataset.  It deliberately does *not* select the
final Gate A denominator: document/version/template-family checks,
constructability, power and human adjudication remain later hard gates.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import shutil
import unicodedata
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

ARTIFACT_VERSION = "ROBUST-FUSION-GATE-A-ELIGIBILITY-2026-08-28-v1"
SCIENTIFIC_PROTOCOL = "ROBUST-FUSION-RESEARCH-2026-08-28-v19"
T2_REVISION = "2a369a430a70979223f1b9a41b1919774d46b432"
CMEDQA2_REVISION = "85feb9278c3ae552c591205cbf3e828368c91f8f"
DU_DATA_REVISION = "a1a333e290fe30b10f3f56498e3a0d911a693ced"
DU_QRELS_REVISION = "497b7bd1bbb25cb3757ff34d95a8be50a3de2279"

EXPECTED_SHA256 = {
    "t2/queries.train.tsv": "b9328c8a0be4980cb8860819285ff3da8c6976f5089e0a606ff003165c4b2c0e",
    "t2/queries.dev.tsv": "1df544dd04bf9b6d0de0dd77e0f3a84a0d74fc4bb9a1ff67b7306de8169135ba",
    "t2/qrels.train.tsv": "5da21371d1f2fa2700bc74a4fdc69b2389b5f304e864a42ac2fe555cad87c77e",
    "cmedqa2/question.zip": "df4738599e20deed824757c40f78c5a3b752b262d2c730de72d69449d95daa89",
    "cmedqa2/answer.zip": "5fd8ba9f049e419929ff3526e7b6902aaa2caba43cf207ea086b1d7755394485",
    "cmedqa2/train_candidates.zip": "e3219cfcd5fe0e84e926e815c2029e494ef776520ef32b09f2a24dc3cbac9ab1",
    "cmedqa2/dev_candidates.zip": "3301b55cddbdd512f6960fb4ed72fd27c7b00db2ed3f10e88d0c2764263a379e",
    "cmedqa2/test_candidates.zip": "d358f5d6b5711a39942e3798f45b5a66887393d1858e88aa1953925e0b630c07",
    "du/corpus.parquet": "d4b4eb51b63549ef0851a15fc63c2a61b703dce95e3727b535a08f7ba1d14424",
    "du/queries.parquet": "62ac55e764bffd4ffceb0aa51e7a536a0e5932f23c8606566906db6a9efb4b94",
    "du/qrels.parquet": "c87e7c16f535a98b29ee0ebf6977639c793e3bd149c04634a1810273cfd3c3e5",
}

_WHITESPACE_RE = re.compile(r"\s+")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_query_family(text: str) -> str:
    """Frozen first-layer family key: NFKC + trim + whitespace collapse."""

    return _WHITESPACE_RE.sub(" ", unicodedata.normalize("NFKC", text).strip())


def family_sha256(text: str) -> str:
    return sha256_bytes(normalize_query_family(text).encode("utf-8"))


def verify_inputs(
    paths: dict[str, Path], repository_root: Path
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for key, path in paths.items():
        if not path.is_file():
            raise RuntimeError(f"missing pinned input: {path}")
        actual = sha256_file(path)
        expected = EXPECTED_SHA256[key]
        if actual != expected:
            raise RuntimeError(f"pinned input checksum mismatch: {key}: {actual} != {expected}")
        records[key] = {
            "relative_path": str(path.relative_to(repository_root)),
            "size_bytes": path.stat().st_size,
            "sha256": actual,
        }
    return records


def read_t2_queries(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != ["qid", "text"]:
            raise RuntimeError(f"unexpected T2 query schema: {reader.fieldnames}")
        for row in reader:
            qid = row["qid"]
            if qid in rows:
                raise RuntimeError(f"duplicate T2 query id: {qid}")
            rows[qid] = row["text"]
    return rows


def audit_t2_qrels(path: Path, query_ids: set[str]) -> dict[str, Any]:
    grades: Counter[int] = Counter()
    pair_count = 0
    qids: set[str] = set()
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None or not {"qid", "pid", "rel"}.issubset(
            reader.fieldnames
        ):
            raise RuntimeError(f"unexpected T2 qrel schema: {reader.fieldnames}")
        for row in reader:
            if row["qid"] not in query_ids:
                raise RuntimeError(f"T2 qrel references unknown qid: {row['qid']}")
            pair_count += 1
            qids.add(row["qid"])
            grades[int(row["rel"])] += 1
    return {
        "pair_count": pair_count,
        "query_count": len(qids),
        "grade_counts": {str(key): grades[key] for key in sorted(grades)},
        "unjudged_is_negative": False,
    }


def build_t2_rows(train: dict[str, str], dev: dict[str, str]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    train_families = {qid: family_sha256(text) for qid, text in train.items()}
    dev_families = {qid: family_sha256(text) for qid, text in dev.items()}
    dev_family_set = set(dev_families.values())
    cross_family_set = set(train_families.values()).intersection(dev_family_set)
    train_family_sizes = Counter(train_families.values())
    dev_family_sizes = Counter(dev_families.values())

    rows: list[dict[str, str]] = []
    for qid, digest in train_families.items():
        excluded = digest in cross_family_set
        rows.append(
            {
                "dataset_id": "t2ranking",
                "source_split": "train",
                "query_id": qid,
                "query_family_sha256": digest,
                "source_family_size": str(train_family_sizes[digest]),
                "eligibility_role": (
                    "excluded" if excluded else "gatea_or_gateb_eligible_upper_bound"
                ),
                "exclusion_reason": "cross_split_query_family" if excluded else "",
            }
        )
    for qid, digest in dev_families.items():
        rows.append(
            {
                "dataset_id": "t2ranking",
                "source_split": "dev",
                "query_id": qid,
                "query_family_sha256": digest,
                "source_family_size": str(dev_family_sizes[digest]),
                "eligibility_role": "calibration_exposed_only",
                "exclusion_reason": "historical_dev_exposure",
            }
        )
    rows.sort(key=lambda row: (row["source_split"], row["query_id"].encode("utf-8")))
    eligible = sum(row["eligibility_role"] == "gatea_or_gateb_eligible_upper_bound" for row in rows)
    return rows, {
        "train_query_count": len(train),
        "dev_query_count": len(dev),
        "train_unique_family_count": len(set(train_families.values())),
        "dev_unique_family_count": len(set(dev_families.values())),
        "cross_split_family_count": len(cross_family_set),
        "train_queries_excluded_by_cross_split_family": len(train) - eligible,
        "eligible_upper_bound": eligible,
        "role": "main_gate_dataset",
        "final_denominator_frozen": False,
    }


def zip_csv_rows(path: Path) -> Iterable[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if len(names) != 1:
            raise RuntimeError(f"expected one CSV member in {path}, got {names}")
        with (
            archive.open(names[0]) as binary,
            io.TextIOWrapper(binary, encoding="utf-8-sig", newline="") as text,
        ):
            yield from csv.DictReader(text)


def read_cmed_questions(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in zip_csv_rows(path):
        qid = row["question_id"]
        if qid in result:
            raise RuntimeError(f"duplicate cMedQA2 question id: {qid}")
        result[qid] = row["content"]
    return result


def read_cmed_candidate_splits(paths: dict[str, Path]) -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, int]]:
    query_ids: dict[str, set[str]] = {split: set() for split in paths}
    positive_answers: dict[str, set[str]] = {split: set() for split in paths}
    record_counts: dict[str, int] = {}
    for split, path in paths.items():
        count = 0
        for row in zip_csv_rows(path):
            count += 1
            qid = row["question_id"]
            query_ids[split].add(qid)
            if split == "train":
                positive_answers[split].add(row["pos_ans_id"])
            elif row["label"] == "1":
                positive_answers[split].add(row["ans_id"])
        record_counts[split] = count
    return query_ids, positive_answers, record_counts


def build_cmed_rows(
    questions: dict[str, str],
    split_query_ids: dict[str, set[str]],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    memberships: dict[str, set[str]] = defaultdict(set)
    family_by_qid: dict[str, str] = {}
    for split, qids in split_query_ids.items():
        missing = qids - set(questions)
        if missing:
            raise RuntimeError(f"cMedQA2 {split} has unknown qids: {sorted(missing)[:3]}")
        for qid in qids:
            digest = family_sha256(questions[qid])
            family_by_qid[qid] = digest
            memberships[digest].add(split)
    cross_families = {digest for digest, splits in memberships.items() if len(splits) > 1}
    source_family_sizes = {
        split: Counter(family_by_qid[qid] for qid in qids)
        for split, qids in split_query_ids.items()
    }

    default_role = {
        "train": "gatea_eligible_upper_bound",
        "dev": "calibration_exposed_only",
        "test": "gateb_eligible_upper_bound",
    }
    rows: list[dict[str, str]] = []
    for split in ("train", "dev", "test"):
        for qid in split_query_ids[split]:
            digest = family_by_qid[qid]
            crossed = digest in cross_families
            if split == "dev":
                role = "calibration_exposed_only"
                reason = (
                    "historical_dev_exposure;cross_split_query_family"
                    if crossed
                    else "historical_dev_exposure"
                )
            elif crossed:
                role = "excluded"
                reason = "cross_split_query_family"
            else:
                role = default_role[split]
                reason = ""
            rows.append(
                {
                    "dataset_id": "cmedqa2",
                    "source_split": split,
                    "query_id": qid,
                    "query_family_sha256": digest,
                    "source_family_size": str(source_family_sizes[split][digest]),
                    "eligibility_role": role,
                    "exclusion_reason": reason,
                }
            )
    rows.sort(key=lambda row: (row["source_split"], row["query_id"].encode("utf-8")))
    role_counts = Counter((row["source_split"], row["eligibility_role"]) for row in rows)
    affected = {
        split: sum(
            family_by_qid[qid] in cross_families for qid in split_query_ids[split]
        )
        for split in ("train", "dev", "test")
    }
    return rows, {
        "query_counts": {split: len(split_query_ids[split]) for split in ("train", "dev", "test")},
        "cross_split_family_count": len(cross_families),
        "cross_split_affected_query_counts": affected,
        "gatea_eligible_upper_bound": role_counts[("train", "gatea_eligible_upper_bound")],
        "gateb_eligible_upper_bound": role_counts[("test", "gateb_eligible_upper_bound")],
        "role": "main_gate_dataset_condition_rich_stratum",
        "domain_specific_endpoint": False,
        "final_denominator_frozen": False,
    }


def audit_du(corpus_path: Path, query_path: Path, qrel_path: Path) -> dict[str, Any]:
    corpus = pq.read_table(corpus_path, columns=["id", "text"])
    queries = pq.read_table(query_path, columns=["id", "text"])
    qrels = pq.read_table(qrel_path)
    corpus_ids = [str(value) for value in corpus.column("id").to_pylist()]
    query_ids = [str(value) for value in queries.column("id").to_pylist()]
    qrel_names = set(qrels.column_names)
    if not {"qid", "pid", "score"}.issubset(qrel_names):
        raise RuntimeError(f"unexpected Du qrel schema: {qrels.column_names}")
    qrel_qids = [str(value) for value in qrels.column("qid").to_pylist()]
    qrel_pids = [str(value) for value in qrels.column("pid").to_pylist()]
    scores = qrels.column("score").to_pylist()
    if len(set(corpus_ids)) != len(corpus_ids) or len(set(query_ids)) != len(query_ids):
        raise RuntimeError("DuRetrieval entity IDs are not unique")
    if not set(qrel_qids).issubset(query_ids) or not set(qrel_pids).issubset(corpus_ids):
        raise RuntimeError("DuRetrieval qrels reference unknown entity IDs")
    pairs = list(zip(qrel_qids, qrel_pids))
    if len(set(pairs)) != len(pairs) or set(scores) != {1}:
        raise RuntimeError("DuRetrieval qrel pair/score contract drift")
    return {
        "data_revision": DU_DATA_REVISION,
        "qrels_revision": DU_QRELS_REVISION,
        "corpus_count": len(corpus_ids),
        "query_count": len(query_ids),
        "qrel_count": len(pairs),
        "all_rows_preserved": True,
        "role": "independent_auxiliary_robustness_only",
        "main_gate_path": False,
        "cmedqa_overlap_changes_membership": False,
    }


def write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise RuntimeError(f"refusing to write empty table: {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def build(repository_root: Path, output_root: Path) -> dict[str, Any]:
    t2_root = repository_root / "data/robust_fusion/public/THUIR_T2Ranking" / T2_REVISION / "data"
    cmed_root = repository_root / "data/robust_fusion/public/zhangsheng93_cMedQA2" / CMEDQA2_REVISION
    du_root = repository_root / "data/robust_fusion/public/C-MTEB_DuRetrieval" / DU_DATA_REVISION / "data"
    du_qrel_root = repository_root / "data/robust_fusion/public/C-MTEB_DuRetrieval-qrels" / DU_QRELS_REVISION / "data"
    paths = {
        "t2/queries.train.tsv": t2_root / "queries.train.tsv",
        "t2/queries.dev.tsv": t2_root / "queries.dev.tsv",
        "t2/qrels.train.tsv": t2_root / "qrels.train.tsv",
        "cmedqa2/question.zip": cmed_root / "question.zip",
        "cmedqa2/answer.zip": cmed_root / "answer.zip",
        "cmedqa2/train_candidates.zip": cmed_root / "train_candidates.zip",
        "cmedqa2/dev_candidates.zip": cmed_root / "dev_candidates.zip",
        "cmedqa2/test_candidates.zip": cmed_root / "test_candidates.zip",
        "du/corpus.parquet": du_root / "corpus-00000-of-00001-19b9e924cb33e4d5.parquet",
        "du/queries.parquet": du_root / "queries-00000-of-00001-7c7edb40be6b560c.parquet",
        "du/qrels.parquet": du_qrel_root / "dev-00000-of-00001-d3c385852a7c0c9d.parquet",
    }
    inputs = verify_inputs(paths, repository_root)

    train_queries = read_t2_queries(paths["t2/queries.train.tsv"])
    dev_queries = read_t2_queries(paths["t2/queries.dev.tsv"])
    t2_rows, t2_summary = build_t2_rows(train_queries, dev_queries)
    t2_summary["qrels_train"] = audit_t2_qrels(
        paths["t2/qrels.train.tsv"], set(train_queries)
    )

    cmed_questions = read_cmed_questions(paths["cmedqa2/question.zip"])
    cmed_candidate_paths = {
        split: paths[f"cmedqa2/{split}_candidates.zip"]
        for split in ("train", "dev", "test")
    }
    cmed_qids, positive_answers, candidate_counts = read_cmed_candidate_splits(
        cmed_candidate_paths
    )
    cmed_rows, cmed_summary = build_cmed_rows(cmed_questions, cmed_qids)
    cmed_summary.update(
        {
            "candidate_record_counts": candidate_counts,
            "positive_answer_counts": {
                split: len(positive_answers[split]) for split in ("train", "dev", "test")
            },
            "positive_answer_cross_split_intersections": {
                "train_dev": len(positive_answers["train"] & positive_answers["dev"]),
                "train_test": len(positive_answers["train"] & positive_answers["test"]),
                "dev_test": len(positive_answers["dev"] & positive_answers["test"]),
            },
        }
    )
    if cmed_summary["cross_split_family_count"] != 80:
        raise RuntimeError(f"cMedQA2 cross-split family drift: {cmed_summary}")
    if cmed_summary["gatea_eligible_upper_bound"] != 99_894:
        raise RuntimeError(f"cMedQA2 Gate A upper-bound drift: {cmed_summary}")
    if cmed_summary["gateb_eligible_upper_bound"] != 3_954:
        raise RuntimeError(f"cMedQA2 Gate B upper-bound drift: {cmed_summary}")
    if any(cmed_summary["positive_answer_cross_split_intersections"].values()):
        raise RuntimeError("cMedQA2 positive answer IDs overlap across source splits")

    du_summary = audit_du(
        paths["du/corpus.parquet"],
        paths["du/queries.parquet"],
        paths["du/qrels.parquet"],
    )
    if (du_summary["corpus_count"], du_summary["query_count"], du_summary["qrel_count"]) != (
        100_001,
        2_000,
        9_839,
    ):
        raise RuntimeError(f"DuRetrieval pinned entity drift: {du_summary}")

    output_root.mkdir(parents=True, exist_ok=False)
    write_tsv(output_root / "t2_query_eligibility.tsv", t2_rows)
    write_tsv(output_root / "cmedqa2_query_eligibility.tsv", cmed_rows)
    script_path = Path(__file__).resolve()
    manifest = {
        "artifact_version": ARTIFACT_VERSION,
        "scientific_protocol": SCIENTIFIC_PROTOCOL,
        "status": "ELIGIBILITY_UPPER_BOUNDS_ONLY_NOT_A_FINAL_GATE_DENOMINATOR",
        "contains_plaintext": False,
        "query_family_rule": "Unicode NFKC + trim + collapse all contiguous whitespace; SHA-256 UTF-8",
        "datasets": {
            "t2ranking": {"revision": T2_REVISION, **t2_summary},
            "cmedqa2": {"revision": CMEDQA2_REVISION, **cmed_summary},
            "duretrieval": du_summary,
            "internal_stress_v6": {
                "role": "main_gate_dataset",
                "population_state": "EMPTY_AWAITING_NEW_REAL_QUERY_INTAKE",
                "eligible": False,
            },
        },
        "inputs": inputs,
        "generator": {
            "relative_path": str(script_path.relative_to(repository_root)),
            "sha256": sha256_file(script_path),
        },
        "remaining_hard_gates": [
            "document_family_zero_overlap",
            "version_family_zero_overlap",
            "counterfactual_template_family_zero_overlap",
            "thirty_family_constructability_pilot",
            "power_derived_final_query_family_denominator",
            "two_independent_reranker_families",
            "human_double_adjudication_and_false_negative_audit",
            "internal_stress_v6_real_query_and_verified_evidence_population",
        ],
        "prohibitions": [
            "do_not_treat_unjudged_public_pairs_as_negative",
            "do_not_use_duretrieval_as_a_post_result_backup_gate_path",
            "do_not_relabel_medical_domain_as_a_separate_endpoint",
            "do_not_unlock_gate_a_from_this_eligibility_artifact",
        ],
    }
    manifest_path = output_root / "manifest.json"
    manifest_path.write_text(canonical_json(manifest) + "\n", encoding="utf-8")
    files = sorted(path for path in output_root.iterdir() if path.is_file())
    checksum_lines = [f"{sha256_file(path)}  {path.name}" for path in files]
    (output_root / "manifest.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    readme = "# Gate A eligibility v1\n\n"
    readme += "This local artifact contains only public IDs, split roles and query-family hashes. "
    readme += "It closes first-layer split leakage but is not a final Gate A/Gate B denominator.\n"
    (output_root / "README.md").write_text(readme, encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/robust_fusion/derived/gate_a_eligibility_v1"),
    )
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    repository_root = args.repository_root.resolve()
    output_root = (
        args.output_root if args.output_root.is_absolute() else repository_root / args.output_root
    )
    if output_root.exists():
        if not args.replace:
            raise RuntimeError(f"refusing to overwrite existing output: {output_root}")
        shutil.rmtree(output_root)
    manifest = build(repository_root, output_root)
    print(
        canonical_json(
            {
                "artifact_version": manifest["artifact_version"],
                "status": manifest["status"],
                "output_root": str(output_root),
                "manifest_sha256": sha256_file(output_root / "manifest.json"),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
