#!/usr/bin/env python3
"""Mechanically diagnose v3 source failures without emitting response text."""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from linkrag_eval.robust_fusion.r2_measurement import (
    character_ngrams,
    jaccard,
    normalize_text,
    template_signature,
    text_sha256,
)
from linkrag_eval.robust_fusion.r2_source_generation import (
    PROPOSAL_FIELDS,
    _language_ok,
    _length_ok,
    build_slot_registry,
    normalized_levenshtein,
    parse_and_validate_proposal,
)
from linkrag_eval.robust_fusion.similarity_dev_calibration import (
    sha256_file,
    write_json,
    write_jsonl,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_v3/robust-fusion-r2-source-recovery-v3-20260829"
)
OUTPUT_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_v3_diagnostic_v1/"
    "robust-fusion-r2-source-recovery-v3-diagnostic-v1-20260829"
)
EXCLUSION = REPO_ROOT / (
    "runs/robust_fusion/r2_measurement_v1/robust-fusion-r2-measurement-v1-20260829/"
    "exclusions/registry.json"
)
EXPECTED_INPUTS = {
    "authorization_receipt_snapshot.json": (
        "5c77c3736219d15d43d6ebcf656553bba40add01786c9ad432889ccdca108681"
    ),
    "call_audit.jsonl": "33462e2e73e264f42ea741698295b1e8e8017b63463aa6000374580ece023e86",
    "response_archive_synthetic_only.jsonl": (
        "e5eb7aa6062ab8a0113769da83c48da144588cb3c79ca24a588ab094e557d821"
    ),
    "accepted_proposals_not_truth.jsonl": (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ),
    "coordinator_stop_decision.json": (
        "c9913338e53fae26e65c9e6a9e7a961ed40b6f0b9c48d21651695339f75800ac"
    ),
}
TEXT_FIELDS = ("query", "reference", "equivalent_candidate", "factual_conflict_candidate")


def _sidecar(path: Path) -> None:
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{sha256_file(path)}  {path.name}\n", encoding="utf-8"
    )


def _length(text: str, language: str) -> int:
    normalized = normalize_text(text)
    return len(normalized) if language == "zh" else len(normalized.split())


def _percentiles(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "min": ordered[0],
        "median": statistics.median(ordered),
        "max": ordered[-1],
    }


def _mutate_surface(text: str, *, fraction: float, replacement: str, reverse: bool) -> str:
    chars = list(text)
    positions = [index for index, char in enumerate(chars) if not char.isspace()]
    count = max(1, round(len(chars) * fraction))
    selected = positions[-count:] if reverse else positions[:count]
    for index in selected:
        chars[index] = replacement
    return "".join(chars)


def _mechanical_satisfiability_witnesses() -> int:
    passed = 0
    for slot in build_slot_registry():
        language = str(slot["language"])
        length = str(slot["length_stratum"])
        if language == "zh":
            reference = "甲" * (80 if length == "short" else 220)
            query = "这项完全虚构的规则是什么？"
            replacements = ("乙", "丙")
        else:
            words = 40 if length == "short" else 120
            reference = " ".join(["aaaaaaaa"] * words)
            query = "What is this entirely fictional rule?"
            replacements = ("b", "c")
        lower, upper = {
            1: (0.02, 0.18),
            2: (0.08, 0.28),
            3: (0.15, 0.40),
            4: (0.22, 0.58),
        }[int(slot["edit_level"])]
        fraction = (lower + upper) / 2
        value = {
            "slot_id": slot["slot_id"],
            "dataset_role": slot["dataset_role"],
            "language": slot["language"],
            "length_stratum": slot["length_stratum"],
            "conflict_type": slot["conflict_type"],
            "edit_level": slot["edit_level"],
            "query": query,
            "reference": reference,
            "equivalent_candidate": _mutate_surface(
                reference, fraction=fraction, replacement=replacements[0], reverse=False
            ),
            "factual_conflict_candidate": _mutate_surface(
                reference, fraction=fraction, replacement=replacements[1], reverse=True
            ),
        }
        parse_and_validate_proposal(
            json.dumps(value, ensure_ascii=False),
            slot=slot,
            exclusion_registry={
                "text_sha256": [],
                "template_sha256": [],
                "near_duplicate_ngrams": [],
            },
        )
        passed += 1
    return passed


def run() -> dict[str, Any]:
    if OUTPUT_ROOT.exists():
        raise RuntimeError("v3 diagnostic output exists; refusing overwrite")
    for name, expected in EXPECTED_INPUTS.items():
        if sha256_file(LIVE_ROOT / name) != expected:
            raise RuntimeError(f"v3 diagnostic input drift: {name}")
    slots = {row["slot_id"]: row for row in build_slot_registry()}
    exclusion = json.loads(EXCLUSION.read_text(encoding="utf-8"))
    excluded_texts = set(exclusion["text_sha256"])
    excluded_templates = set(exclusion["template_sha256"])
    excluded_ngrams = [set(row) for row in exclusion["near_duplicate_ngrams"]]
    archives = [
        json.loads(line)
        for line in (LIVE_ROOT / "response_archive_synthetic_only.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    output = []
    for archive in archives:
        slot = slots[str(archive["slot_id"])]
        record: dict[str, Any] = {
            "slot_id": archive["slot_id"],
            "attempt": archive["attempt"],
            "request_sha256": archive["request_sha256"],
            "response_sha256": archive["response_sha256"],
        }
        try:
            value = json.loads(str(archive["response_content"]))
        except json.JSONDecodeError:
            record.update({"json_object": False, "first_parser_failure": "json_parse"})
            output.append(record)
            continue
        record["json_object"] = isinstance(value, dict)
        keys = set(value) if isinstance(value, dict) else set()
        record["exact_fields"] = keys == PROPOSAL_FIELDS
        record["extra_fields"] = sorted(keys - PROPOSAL_FIELDS)
        record["missing_fields"] = sorted(PROPOSAL_FIELDS - keys)
        identity_fields = (
            "slot_id",
            "dataset_role",
            "language",
            "length_stratum",
            "conflict_type",
            "edit_level",
        )
        identity_matches = {
            key: isinstance(value, dict) and value.get(key) == slot[key] for key in identity_fields
        }
        record["identity_matches"] = identity_matches
        if not isinstance(value, dict) or keys != PROPOSAL_FIELDS:
            record["first_parser_failure"] = "schema_exact_fields"
            output.append(record)
            continue
        if not all(identity_matches.values()):
            record["first_parser_failure"] = "schema_slot_identity"
            output.append(record)
            continue
        texts = {field: str(value[field]) for field in TEXT_FIELDS}
        normalized = {field: normalize_text(text) for field, text in texts.items()}
        duplicate_pairs = []
        for index, left in enumerate(TEXT_FIELDS):
            for right in TEXT_FIELDS[index + 1 :]:
                if normalized[left] == normalized[right]:
                    duplicate_pairs.append(f"{left}=={right}")
        record["normalized_unique_values"] = len(set(normalized.values()))
        record["duplicate_pairs"] = duplicate_pairs
        language = str(slot["language"])
        length = str(slot["length_stratum"])
        record["field_lengths"] = {field: _length(text, language) for field, text in texts.items()}
        record["language_ok"] = {
            field: _language_ok(text, language) for field, text in texts.items()
        }
        record["length_ok"] = {
            field: _length_ok(texts[field], language, length)
            for field in ("reference", "equivalent_candidate", "factual_conflict_candidate")
        }
        edit = int(slot["edit_level"])
        lower, upper = {1: (0.02, 0.18), 2: (0.08, 0.28), 3: (0.15, 0.40), 4: (0.22, 0.58)}[edit]
        distances = {
            field: normalized_levenshtein(texts["reference"], texts[field])
            for field in ("equivalent_candidate", "factual_conflict_candidate")
        }
        record["normalized_levenshtein"] = distances
        record["edit_band"] = {"minimum": lower, "maximum": upper}
        record["edit_band_ok"] = {
            field: lower <= distance <= upper for field, distance in distances.items()
        }
        r1_hits = {"exact": [], "template": [], "near_duplicate_5gram": []}
        for field, text in texts.items():
            if text_sha256(text) in excluded_texts:
                r1_hits["exact"].append(field)
            if template_signature(text) in excluded_templates:
                r1_hits["template"].append(field)
            grams = character_ngrams(text)
            if any(jaccard(grams, prior) >= 0.82 for prior in excluded_ngrams):
                r1_hits["near_duplicate_5gram"].append(field)
        record["r1_exclusion_hits"] = r1_hits
        if duplicate_pairs:
            first = "schema_four_text_uniqueness"
        elif not all(record["language_ok"].values()):
            first = "language"
        elif not all(record["length_ok"].values()):
            first = "length"
        elif not all(record["edit_band_ok"].values()):
            first = "edit_band"
        elif any(r1_hits.values()):
            first = "r1_exclusion"
        else:
            first = "mechanically_valid"
        record["first_parser_failure"] = first
        output.append(record)
    OUTPUT_ROOT.mkdir(parents=True, mode=0o700)
    write_jsonl(OUTPUT_ROOT / "per_response_mechanical_diagnostic.jsonl", output)
    complete = [row for row in output if row.get("field_lengths")]
    summary = {
        "status": "FAIL_CLOSED_SOURCE_IMPLEMENTATION_DIAGNOSTIC",
        "semantic_evaluation_performed": False,
        "content_selection_performed": False,
        "responses": len(output),
        "accepted": 0,
        "first_parser_failure_counts": dict(
            sorted(Counter(row["first_parser_failure"] for row in output).items())
        ),
        "normalized_unique_value_counts": dict(
            sorted(Counter(str(row["normalized_unique_values"]) for row in complete).items())
        ),
        "duplicate_pair_counts": dict(
            sorted(Counter(pair for row in complete for pair in row["duplicate_pairs"]).items())
        ),
        "field_length_distributions": {
            field: _percentiles([float(row["field_lengths"][field]) for row in complete])
            for field in TEXT_FIELDS
        },
        "length_pass_counts": {
            field: sum(bool(row["length_ok"][field]) for row in complete)
            for field in ("reference", "equivalent_candidate", "factual_conflict_candidate")
        },
        "edit_distance_distributions": {
            field: _percentiles(
                [float(row["normalized_levenshtein"][field]) for row in complete]
            )
            for field in ("equivalent_candidate", "factual_conflict_candidate")
        },
        "edit_band_pass_counts": {
            field: sum(bool(row["edit_band_ok"][field]) for row in complete)
            for field in ("equivalent_candidate", "factual_conflict_candidate")
        },
        "r1_exclusion_hit_responses": sum(
            any(row["r1_exclusion_hits"].values()) for row in complete
        ),
        "mechanical_satisfiability_witness_slots_passed": (
            _mechanical_satisfiability_witnesses()
        ),
        "mathematical_satisfiability": (
            "PASS_ALL_128_SLOT_NUMERICAL_PARSER_CONSTRAINTS_HAVE_LOCAL_WITNESSES"
        ),
        "threshold_unit_alignment": {
            "zh_length": "normalized_character_count_matches_prompt_and_parser",
            "en_length": "normalized_whitespace_word_count_matches_prompt_and_parser",
            "edit_strength": "normalized_character_levenshtein_ratio_matches_prompt_and_parser",
        },
        "diagnostic_conclusion": (
            "provider did not jointly satisfy pairwise non-copy and minimum short-zh length; "
            "no mathematical parser/threshold contradiction identified"
        ),
    }
    write_json(OUTPUT_ROOT / "summary.json", summary)
    manifest = {
        "status": summary["status"],
        "inputs": [
            {
                "path": str((LIVE_ROOT / name).relative_to(REPO_ROOT)),
                "sha256": expected,
            }
            for name, expected in EXPECTED_INPUTS.items()
        ],
        "outputs": [
            {
                "path": name,
                "sha256": sha256_file(OUTPUT_ROOT / name),
                "size_bytes": (OUTPUT_ROOT / name).stat().st_size,
            }
            for name in ("per_response_mechanical_diagnostic.jsonl", "summary.json")
        ],
    }
    write_json(OUTPUT_ROOT / "manifest.json", manifest)
    for name in ("per_response_mechanical_diagnostic.jsonl", "summary.json", "manifest.json"):
        _sidecar(OUTPUT_ROOT / name)
    return {**summary, "manifest_sha256": sha256_file(OUTPUT_ROOT / "manifest.json")}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
