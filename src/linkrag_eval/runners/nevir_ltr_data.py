"""本轮 NevIR 原文、匿名运行身份和独立监督的离线准备。"""

from __future__ import annotations

import json
import random
import re
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from linkrag_eval.store.ids import eval_chunk_id

ROLES = ("train", "development", "confirmation")
PAIR_COUNTS = {"train": 948, "development": 38, "confirmation": 187}
GROUP_COUNTS = {"train": 473, "development": 19, "confirmation": 96}
CORPUS_COUNT = 1761
DATASET_ID = 995300
DOC_ID_BASE = 9953000000000
QDRANT_PREFIX = "eval_nevir_ltr_20260907"
SEED = 20260907
_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
_CONFLICT = "identical_query_text_opposite_preferences_same_pair"


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON must be an object: {path}")
    return value


def read_source_rows(path: Path) -> list[dict[str, Any]]:
    """明确路径逐行读取；不枚举原始目录或打开 Test。"""
    if path.name not in {"train.jsonl", "validation.jsonl"}:
        raise ValueError("NevIR preparation only reads train.jsonl and validation.jsonl")
    rows = []
    with path.open(encoding="utf-8") as stream:
        for position, line in enumerate(stream):
            if not line.strip():
                raise ValueError(f"Blank source row: {path.name}:{position + 1}")
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TypeError(f"Non-object source row: {path.name}:{position + 1}")
            rows.append(value)
    return rows


def _source_prefix(pair_id: str) -> str:
    prefix, separator, suffix = pair_id.rpartition("-")
    if not separator or not prefix or not suffix:
        raise ValueError("Invalid source pair ID")
    return prefix


def _check_sources(sources: dict[str, list[dict[str, Any]]]) -> None:
    seen_ids: set[str] = set()
    for split, rows in sources.items():
        if not rows:
            raise ValueError(f"Empty source split: {split}")
        for position, row in enumerate(rows):
            for key in ("id", "q1", "q2", "doc1", "doc2"):
                if not isinstance(row.get(key), str) or not row[key].strip():
                    raise ValueError(f"Invalid {key} in {split} source row {position}")
            _source_prefix(row["id"])
            if row["id"] in seen_ids:
                raise ValueError("Duplicate pair ID in allowed sources")
            seen_ids.add(row["id"])
            if row["doc1"] == row["doc2"]:
                raise ValueError("Unexpected identical target bodies in a source pair")


def _members(
    sources: dict[str, list[dict[str, Any]]],
    proposals: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    members = []
    seen_locations: set[tuple[str, int]] = set()
    seen_groups: set[str] = set()
    for role in ROLES:
        split = "train" if role == "train" else "validation"
        proposal = proposals[role]
        groups = proposal.get(f"{role}_groups")
        if not isinstance(groups, list) or not groups:
            raise ValueError(f"Missing groups for {role}")
        for group in groups:
            group_id = group.get("component_id")
            if not isinstance(group_id, str) or not group_id or group_id in seen_groups:
                raise ValueError("Missing or repeated source group ID")
            seen_groups.add(group_id)
            group_members = group.get("members")
            if not isinstance(group_members, list) or not group_members:
                raise ValueError("Empty or invalid source group")
            actual_prefixes = set()
            for member in group_members:
                index = member.get("source_row_index_zero_based")
                if type(index) is not int or not 0 <= index < len(sources[split]):
                    raise ValueError(f"Invalid source row index for {role}")
                if (split, index) in seen_locations:
                    raise ValueError("A source row is assigned more than once")
                seen_locations.add((split, index))
                row = sources[split][index]
                if member.get("pair_id") != row["id"]:
                    raise ValueError(f"Proposal pair ID does not match source row in {role}")
                actual_prefixes.add(_source_prefix(row["id"]))
                structural_conflict = row["q1"] == row["q2"]
                declared_conflict = member.get("structural_label_conflict")
                if structural_conflict != (declared_conflict == _CONFLICT):
                    raise ValueError("Structural conflict differs from accepted proposal")
                if declared_conflict is not None and declared_conflict != _CONFLICT:
                    raise ValueError("Unknown structural conflict annotation")
                if role == "train" and member.get("recommended_loss_eligible") is not (
                    not structural_conflict
                ):
                    raise ValueError("Train loss eligibility differs from structural policy")
                note = member.get("unresolved_label_note")
                if note is not None and (not isinstance(note, str) or not note):
                    raise ValueError("Invalid unresolved label note")
                prior_exposure = member.get("prior_exposure", "not_previously_identified")
                if prior_exposure not in {
                    "not_previously_identified", "direct_text_or_results", "source_associated"
                }:
                    raise ValueError("Unknown prior exposure annotation")
                if role == "confirmation" and (
                    note is not None or prior_exposure != "not_previously_identified"
                ):
                    raise ValueError("Confirmation member has prior development exposure")
                members.append({
                    "role": role, "source_split": split, "source_group_id": group_id,
                    "source_row_index_zero_based": index, "row": row, "annotation": member,
                })
            prefixes = group.get("source_prefixes")
            if not isinstance(prefixes, list) or set(prefixes) != actual_prefixes:
                raise ValueError("Proposal source prefixes do not match source rows")
            if len(prefixes) != len(set(prefixes)):
                raise ValueError("Duplicate source prefix within group")
    expected = {(split, index) for split, rows in sources.items() for index in range(len(rows))}
    if seen_locations != expected:
        raise ValueError("Allowed source rows are not fully covered by the split proposal")
    return members


def _check_isolation(members: list[dict[str, Any]]) -> dict[str, Any]:
    """校验建议连通组；仅字符串和词项关系，不声称语义／文章级完全隔离。"""
    parent = list(range(len(members)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    first: dict[tuple[str, Any], int] = {}
    for index, member in enumerate(members):
        row = member["row"]
        keys: list[tuple[str, Any]] = [("prefix", _source_prefix(row["id"]))]
        keys.extend(("body", row[slot]) for slot in ("doc1", "doc2"))
        for slot in ("q1", "q2"):
            query = row[slot]
            tokens = tuple(_TOKEN.findall(query.lower()))
            keys.append(("exact_query", query))
            # Empty ASCII token sequences are not evidence that two queries are equivalent.
            if tokens:
                keys.extend([
                    ("normalized_query", tokens),
                    ("query_token_multiset", tuple(sorted(tokens))),
                ])
        for key in keys:
            if key not in first:
                first[key] = index
                continue
            previous = first[key]
            if member["source_group_id"] != members[previous]["source_group_id"]:
                raise ValueError(f"Split proposal separates a known {key[0]} relationship")
            if member["role"] != members[previous]["role"]:
                raise ValueError(f"Cross-role {key[0]} overlap")
            parent[find(index)] = find(previous)
    group_roots: dict[str, set[int]] = {}
    for index, member in enumerate(members):
        group_roots.setdefault(member["source_group_id"], set()).add(find(index))
    if any(len(roots) != 1 for roots in group_roots.values()):
        raise ValueError("Proposal merges members without a known grouping relationship")
    return {
        "source_group_count": len(group_roots),
        "cross_role_known_relationships": 0,
        "source_row_coverage_complete": True,
        "checked_relationships": [
            "source_prefix", "exact_decoded_body", "exact_query",
            "lowercase_ascii_query_token_sequence", "query_token_multiset",
        ],
        "semantic_equivalence_review": "No new semantic review; prior bounded lexical audit only",
        "article_level_isolation_proven": False,
        "test_isolation_proven": False,
        "test_file_opened": False,
    }


def build_nevir_ltr_inputs(
    *, train_rows: list[dict[str, Any]], validation_rows: list[dict[str, Any]],
    train_development_proposal: dict[str, Any], confirmation_proposal: dict[str, Any],
    dataset_id: int = DATASET_ID, doc_id_base: int = DOC_ID_BASE,
    qdrant_prefix: str = QDRANT_PREFIX, seed: int = SEED,
) -> dict[str, Any]:
    """从已采纳建议构造纯数据；不读取配置、存储或模型。"""
    if type(dataset_id) is not int or dataset_id <= 0:
        raise ValueError("dataset_id must be a positive integer")
    if type(doc_id_base) is not int or doc_id_base <= 0:
        raise ValueError("doc_id_base must be a positive integer")
    if not isinstance(qdrant_prefix, str) or "eval" not in qdrant_prefix:
        raise ValueError("Qdrant prefix must contain eval")
    if type(seed) is not int:
        raise ValueError("An explicit integer seed is required")
    proposals = {
        "train": train_development_proposal, "development": train_development_proposal,
        "confirmation": confirmation_proposal,
    }
    for proposal in (train_development_proposal, confirmation_proposal):
        if proposal.get("status") != "suggested_not_consumed":
            raise ValueError("Expected original suggested_not_consumed split proposal")
    if confirmation_proposal.get("not_for_training_consumption") is not True:
        raise ValueError("Confirmation proposal must be marked not for training consumption")
    if train_development_proposal.get("counts") != confirmation_proposal.get("counts"):
        raise ValueError("Split proposals disagree about role counts")
    sources = {"train": train_rows, "validation": validation_rows}
    _check_sources(sources)
    members = _members(sources, proposals)
    isolation = _check_isolation(members)
    counts = {}
    for role in ROLES:
        selected = [member for member in members if member["role"] == role]
        pair_count = len(selected)
        group_count = len({member["source_group_id"] for member in selected})
        expected = {
            "official_pair_rows": pair_count, "query_slots": 2 * pair_count,
            "source_components": group_count,
        }
        if train_development_proposal.get("counts", {}).get(role) != expected:
            raise ValueError(f"Proposal count mismatch for {role}")
        counts[role] = {
            "pair_count": pair_count, "query_count": 2 * pair_count,
            "source_group_count": group_count,
        }

    # Shuffle all distinct passages before assigning independent document identities.
    texts = list(dict.fromkeys(
        row[slot] for rows in sources.values() for row in rows for slot in ("doc1", "doc2")
    ))
    random.Random(seed).shuffle(texts)
    if doc_id_base + len(texts) - 1 > 2**63 - 1:
        raise ValueError("Document identity exceeds SQLite signed integer range")
    corpus = []
    mapping = []
    passage_by_text = {}
    for index, content in enumerate(texts):
        passage_id = f"p{index:06d}"
        doc_id = doc_id_base + index
        mapped = {
            "source_passage_id": passage_id, "dataset_id": dataset_id,
            "doc_id": doc_id, "chunk_id": eval_chunk_id(dataset_id, doc_id, 0),
        }
        corpus.append({"source_passage_id": passage_id, "content": content})
        mapping.append(mapped)
        passage_by_text[content] = mapped

    # Global shuffle ensures IDs do not encode role, pair, direction, or source group.
    slots = [(member, direction) for member in members for direction in ("q1", "q2")]
    random.Random(seed + 1).shuffle(slots)
    roles: dict[str, dict[str, list[dict[str, Any]]]] = {
        role: {"queries": [], "supervision": []} for role in ROLES
    }
    for index, (member, direction) in enumerate(slots):
        row, annotation, role = member["row"], member["annotation"], member["role"]
        query_id = f"q{index:06d}"
        preferred, other = ("doc1", "doc2") if direction == "q1" else ("doc2", "doc1")
        preferred_mapping, other_mapping = (
            passage_by_text[row[preferred]], passage_by_text[row[other]]
        )
        note = annotation.get("unresolved_label_note")
        prior = annotation.get("prior_exposure", "not_previously_identified")
        conflict = row["q1"] == row["q2"]
        issues = ([_CONFLICT] if conflict else []) + ([note] if note else [])
        review_status = "not_semantically_reviewed"
        if note:
            review_status = "previous_ai_review_with_unresolved_pair_issue"
        elif prior == "direct_text_or_results":
            review_status = "previous_exposure_without_independent_label_verification"
        roles[role]["queries"].append({"source_query_id": query_id, "query": row[direction]})
        roles[role]["supervision"].append({
            "source_query_id": query_id, "role": role,
            "source_group_id": member["source_group_id"], "pair_id": row["id"],
            "direction": direction,
            "preferred_chunk_id": preferred_mapping["chunk_id"],
            "other_chunk_id": other_mapping["chunk_id"],
            "preferred_passage_id": preferred_mapping["source_passage_id"],
            "other_passage_id": other_mapping["source_passage_id"],
            "official_label_available": True, "structural_conflict": conflict,
            "semantic_uncertain": note is not None,
            "label_basis": "official_NevIR_q1_prefers_doc1_q2_prefers_doc2",
            "issue_reasons": issues, "semantic_review_status": review_status,
            "semantic_issue_scope": "existing_pair_level_note" if note else "none_recorded",
            "prior_exposure": prior,
            "exposure_basis": annotation.get("exposure_basis"),
            "source_split": member["source_split"],
            "source_row_index_zero_based": member["source_row_index_zero_based"],
        })
    for role in ROLES:
        supervision = roles[role]["supervision"]
        counts[role].update({
            "structural_conflict_query_count": sum(row["structural_conflict"] for row in supervision),
            "semantic_uncertain_query_count": sum(row["semantic_uncertain"] for row in supervision),
            "semantic_review_status_counts": dict(Counter(
                row["semantic_review_status"] for row in supervision
            )),
        })
    return {
        "corpus": corpus, "passage_mapping": mapping, "roles": roles, "counts": counts,
        "identity": {
            "dataset_id": dataset_id, "doc_id_base": doc_id_base,
            "qdrant_prefix": qdrant_prefix, "corpus_count": len(corpus),
        },
        "isolation": isolation,
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")


def prepare_nevir_ltr(
    *, source_dir: Path, train_development_proposal: Path, confirmation_proposal: Path,
    output_dir: Path, dataset_id: int = DATASET_ID, doc_id_base: int = DOC_ID_BASE,
    qdrant_prefix: str = QDRANT_PREFIX, seed: int = SEED,
) -> dict[str, Any]:
    """只生成本轮已授权规模；完整校验后写入新的非覆盖目录。"""
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        raise FileExistsError(f"Refusing to overwrite nonempty output: {output_dir}")
    prepared = build_nevir_ltr_inputs(
        train_rows=read_source_rows(source_dir / "train.jsonl"),
        validation_rows=read_source_rows(source_dir / "validation.jsonl"),
        train_development_proposal=_json_object(train_development_proposal),
        confirmation_proposal=_json_object(confirmation_proposal),
        dataset_id=dataset_id, doc_id_base=doc_id_base, qdrant_prefix=qdrant_prefix, seed=seed,
    )
    for role in ROLES:
        if prepared["counts"][role]["pair_count"] != PAIR_COUNTS[role]:
            raise ValueError(f"Current experiment pair count changed for {role}")
        if prepared["counts"][role]["source_group_count"] != GROUP_COUNTS[role]:
            raise ValueError(f"Current experiment group count changed for {role}")
    if prepared["identity"]["corpus_count"] != CORPUS_COUNT:
        raise ValueError("Current experiment corpus count changed")
    conflicts = {
        (role, row["pair_id"]) for role in ROLES for row in prepared["roles"][role]["supervision"]
        if row["structural_conflict"]
    }
    if conflicts != {("train", "619-2")}:
        raise ValueError("Current experiment structural conflict set changed")
    paths = {
        "corpus": "prepared/corpus.jsonl", "passage_mapping": "prepared/passage-mapping.jsonl",
        "roles": {
            role: {
                "queries": f"prepared/{role}/queries.jsonl",
                "supervision": f"prepared/{role}/supervision.jsonl",
                "candidate_inputs": f"candidates/{role}/inputs.jsonl",
            } for role in ROLES
        },
    }
    repository = Path(__file__).resolve().parents[3]
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True,
    ).strip()
    metadata = {
        "format": "nevir-ltr-experiment-v1", "preparation_status": "complete",
        "prepared_utc": datetime.now(UTC).isoformat(), "code_revision": revision,
        "identity": prepared["identity"], "counts": prepared["counts"], "paths": paths,
        "source_paths": {
            split: str((source_dir / f"{split}.jsonl").resolve())
            for split in ("train", "validation")
        },
        "accepted_split_proposals": {
            "train_development": str(train_development_proposal.resolve()),
            "confirmation": str(confirmation_proposal.resolve()),
        },
        "anonymization": {
            "seed": seed, "passage_order": "Random(seed).shuffle(exact unique original bodies)",
            "query_order": "Random(seed + 1).shuffle(all original query slots)",
            "document_identity": "one independent document per exact paragraph; ordinal=0",
            "query_identity": "anonymous global sequence; no role/pair/direction/group in ID",
        },
        "supervision_policy": {
            "official_preferences": "preserved; q1 prefers doc1; q2 prefers doc2",
            "background_candidates": "unjudged; never inferred negative",
            "main_train_loss_excluded_pair_ids": ["619-2"],
            "main_train_maximum_before_candidate_coverage": {"pair_count": 947, "query_count": 1894},
            "semantic_uncertain": "existing pair-level AI note, not independent query adjudication",
            "no_recorded_issue_is_not_verified": True,
            "inference_fields": "query, actual route identity/score/rank, candidate content only",
            "confirmation_access": "data/evaluation only; training reads explicit train/development paths",
        },
        "isolation": prepared["isolation"], "preparation_remote_requests": 0,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    prepared_dir = output_dir / "prepared"
    prepared_dir.mkdir(exist_ok=False)
    _write_jsonl(output_dir / paths["corpus"], prepared["corpus"])
    _write_jsonl(output_dir / paths["passage_mapping"], prepared["passage_mapping"])
    for role in ROLES:
        (prepared_dir / role).mkdir(exist_ok=False)
        for kind in ("queries", "supervision"):
            _write_jsonl(output_dir / paths["roles"][role][kind], prepared["roles"][role][kind])
    with (output_dir / "run.json").open("x", encoding="utf-8") as stream:
        json.dump(metadata, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return metadata
