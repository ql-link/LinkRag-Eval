#!/usr/bin/env python3
"""Issue 21: prepare offline packets and receive human-confirmed annotations."""
from __future__ import annotations

import argparse
import html
import json
import random
import re
import subprocess
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUNS = Path("runs/post_recall")
EXPERIMENT = RUNS / "nevir-ltr-validation-20260907/data-preparation/experiment"
QWEN = RUNS / "open-judge-confirmation-20260910/l2-first-pass-k20"
GPT = RUNS / "llm-judge-pilot-20260910/l2s-confirmation-k20-v2"
DEVELOPMENT = RUNS / "subject-binding-pilot-20260908/upstream-diagnostic-20260909/first-observed-output.json"
HUMAN = RUNS / "subject-binding-pilot-20260908/human/adjudication/history/results-v5-frozen.json"
OLD_MAPPING = RUNS / "nevir-offline-diagnostic-20260907/review/private/reviewer_1-mapping.jsonl"
TYPES = ["否定范围", "主体归属", "比较方向", "改述或反义", "额外限制", "标签争议", "其他"]
STATUSES = ["pending", "reviewed", "uncertain"]
PREFERENCES = ["X", "Y", "tie", "undetermined"]
EXPOSURES = ["not_declared", "no", "yes", "unsure"]
MODES = ["not_declared", "human_only", "model_assisted"]
VERSION = "v2"
SCHEMA_VERSION = 2
ANSWER_KEYS = {"case_id", "preference", "primary_type", "reason", "status"}


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def write_rows(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


def unique(rows, key):
    result = {}
    for row in rows:
        value = row[key]
        if value in result:
            raise ValueError(f"duplicate {key}: {value}")
        result[value] = row
    return result


def load_sources(root):
    sources = {}
    methods = {}
    for name, folder in (("qwen", QWEN), ("gpt", GPT)):
        rows = unique(read_rows(root / folder / "official-per-query.jsonl"), "source_query_id")
        if len(rows) != 371:
            raise ValueError(f"{name}: expected 371 official confirmation rows")
        methods[name] = rows
        run = json.loads((root / folder / "results.json").read_text())
        sources[name] = run["trigger"]["stage1_judge"]["by_query"]
    if set(methods["qwen"]) != set(methods["gpt"]):
        raise ValueError("judge populations differ")
    wrong = {
        name: {qid for qid, row in rows.items() if row["stage1_judge"] != "strict_correct"}
        for name, rows in methods.items()
    }
    selected = wrong["qwen"] | wrong["gpt"]
    if (len(wrong["qwen"]), len(wrong["gpt"]), len(selected)) != (91, 60, 101):
        raise ValueError("unexpected confirmation error population")
    diagnostic = unique(json.loads((root / DEVELOPMENT).read_text()), "source_query_id")
    human = unique(json.loads((root / HUMAN).read_text())["results"], "original_ordinal")
    old_mapping = unique(read_rows(root / OLD_MAPPING), "source_query_id")
    if len(diagnostic) != 21 or selected & set(diagnostic):
        raise ValueError("unexpected or overlapping development population")
    records = []
    for role, qids in (("confirmation", selected), ("development", set(diagnostic))):
        prepared = unique(read_rows(root / EXPERIMENT / f"prepared/{role}/queries.jsonl"), "source_query_id")
        supervision = unique(read_rows(root / EXPERIMENT / f"prepared/{role}/supervision.jsonl"), "source_query_id")
        found = set()
        with (root / EXPERIMENT / f"candidates/{role}/inputs.jsonl").open() as stream:
            for line in stream:
                row = json.loads(line)
                qid = row["source_query_id"]
                if qid not in qids:
                    continue
                if qid in found:
                    raise ValueError("duplicate candidate query")
                found.add(qid)
                sup = supervision[qid]
                if row["query"] != prepared[qid]["query"]:
                    raise ValueError("candidate query differs from prepared input")
                candidates = unique(row["candidate_rows"], "chunk_id")
                pair = [sup["preferred_chunk_id"], sup["other_chunk_id"]]
                texts = {cid: candidates[cid]["content"] for cid in pair}
                if any(not isinstance(text, str) or not text.strip() for text in texts.values()):
                    raise ValueError("missing candidate text")
                record = {
                    "source_query_id": qid, "role": role,
                    "source_group_id": sup["source_group_id"], "pair_id": sup["pair_id"],
                    "query": row["query"], "paragraphs": texts,
                    "official_preferred_chunk_id": sup["preferred_chunk_id"],
                    "reference_chunk_id": sup["preferred_chunk_id"],
                    "reference_basis": "official_NevIR", "model_outcomes": {},
                    "technical_fallback": {}, "source_files": [
                        str(EXPERIMENT / f"prepared/{role}/queries.jsonl"),
                        str(EXPERIMENT / f"prepared/{role}/supervision.jsonl"),
                        str(EXPERIMENT / f"candidates/{role}/inputs.jsonl"),
                    ],
                }
                if role == "confirmation":
                    for name in methods:
                        outcome = methods[name][qid]
                        if any(outcome[k] != sup[k] for k in ("pair_id", "source_group_id", "direction")):
                            raise ValueError("judge identity differs from supervision")
                        record["model_outcomes"][name] = outcome["stage1_judge"]
                        record["technical_fallback"][name] = sources[name][qid]["fallback"]
                    record["model_outcomes"]["E0"] = methods["qwen"][qid]["E0"]
                    if methods["gpt"][qid]["E0"] != record["model_outcomes"]["E0"]:
                        raise ValueError("baseline outcome mismatch")
                    record["selected_for"] = [name for name in methods if qid in wrong[name]]
                else:
                    old = old_mapping[qid]
                    diag = diagnostic[qid]
                    h = human[diag["original_ordinal"]]
                    pref = h["proposal"]["pair_preference"]
                    if (pref not in ("X", "Y") or pref != diag["human_preference"]
                            or h["case_id"] != diag["case_id"] or h["case_id"] != old["case_id"]
                            or h["query"] != row["query"] or diag["query"] != row["query"]
                            or set(old["display_mapping"].values()) != set(pair)
                            or diag["E0_human_relation"] != "reverse"):
                        raise ValueError("development v5 reference mismatch")
                    record.update(
                        reference_chunk_id=old["display_mapping"][pref],
                        reference_basis="human_v5", original_ordinal=diag["original_ordinal"],
                        model_outcomes={"E0": "reverse"}, selected_for=["E0_human_v5"],
                    )
                    record["source_files"] += [str(DEVELOPMENT), str(HUMAN), str(OLD_MAPPING)]
                records.append(record)
        if found != qids:
            raise ValueError(f"missing {role} candidate rows")
    records.sort(key=lambda row: (row["role"], row["source_query_id"]))
    if len(records) != 122:
        raise ValueError("expected 122 source cases")
    fallback_errors = sum(
        r["technical_fallback"].get("qwen", False)
        and r["model_outcomes"].get("qwen") != "strict_correct" for r in records
    )
    if fallback_errors != 2:
        raise ValueError("unexpected technical-fallback error population")
    return records


def make_packet(records, reviewer):
    rng = random.Random(20260911 + reviewer)
    ordered = list(records)
    rng.shuffle(ordered)
    sides = ["X", "Y"] * (len(ordered) // 2)
    rng.shuffle(sides)
    public, mapping = [], []
    for index, (row, ref_side) in enumerate(zip(ordered, sides, strict=True), 1):
        cid = f"R{reviewer}-{index:03d}"
        ref = row["reference_chunk_id"]
        other = next(key for key in row["paragraphs"] if key != ref)
        display = {ref_side: ref, "Y" if ref_side == "X" else "X": other}
        public.append({
            "case_id": cid, "query": row["query"], "reference_preference": ref_side,
            "paragraphs": {side: row["paragraphs"][display[side]] for side in ("X", "Y")},
        })
        mapping.append({
            "case_id": cid, "source_query_id": row["source_query_id"],
            "role": row["role"], "display_mapping": display,
        })
    payload = {
        "packet_id": f"issue21-error-types-20260911-r{reviewer}-{VERSION}",
        "schema_version": SCHEMA_VERSION, "guide_version": VERSION, "reviewer_slot": reviewer,
        "types": TYPES, "cases": public,
    }
    return payload, mapping


def blank_submission(packet):
    return {
        "packet_id": packet["packet_id"], "schema_version": SCHEMA_VERSION, "guide_version": VERSION,
        "submission_kind": "draft", "reviewer_name": "", "human_confirmed": False,
        "annotation_mode": "not_declared", "assistance_notes": "",
        "previous_exposure": "not_declared", "exported_at": None,
        "answers": [
            {"case_id": c["case_id"], "preference": None, "primary_type": None,
             "reason": "", "status": "pending"} for c in packet["cases"]
        ],
    }


def validate_submission(payload, packet, require_final=False):
    if not isinstance(payload, dict):
        raise TypeError("submission must be an object")
    template = blank_submission(packet)
    if set(payload) != set(template):
        raise ValueError("submission fields differ from the packet schema")
    for key in ("packet_id", "schema_version", "guide_version"):
        if payload[key] != template[key]:
            raise ValueError(f"wrong {key}")
    if (not isinstance(payload["reviewer_name"], str)
            or type(payload["human_confirmed"]) is not bool
            or payload["annotation_mode"] not in MODES
            or not isinstance(payload["assistance_notes"], str)
            or payload["previous_exposure"] not in EXPOSURES
            or payload["submission_kind"] not in ("draft", "final")
            or (payload["exported_at"] is not None and not isinstance(payload["exported_at"], str))
            or not isinstance(payload["answers"], list)):
        raise ValueError("invalid submission metadata")
    rows = payload["answers"]
    if any(not isinstance(r, dict) or set(r) != ANSWER_KEYS for r in rows):
        raise ValueError("invalid answer fields")
    by_id = unique(rows, "case_id")
    if set(by_id) != {c["case_id"] for c in packet["cases"]}:
        raise ValueError("case IDs do not match this packet")
    for row in rows:
        if (row["status"] not in STATUSES or row["preference"] not in [None, *PREFERENCES]
                or row["primary_type"] not in [None, *TYPES] or not isinstance(row["reason"], str)):
            raise ValueError("invalid answer value")
        if row["status"] != "pending" and (row["preference"] is None or not row["reason"].strip()):
            raise ValueError("handled case lacks preference/reason")
        if row["status"] == "reviewed" and row["primary_type"] is None:
            raise ValueError("reviewed case lacks a primary type")
    counts = Counter(r["status"] for r in rows)
    if payload["submission_kind"] == "final" or require_final:
        if (payload["submission_kind"] != "final" or counts["pending"]
                or not payload["reviewer_name"].strip() or not payload["human_confirmed"]):
            raise ValueError("final submission needs all cases handled and human confirmation")
        if payload["annotation_mode"] == "not_declared":
            raise ValueError("final submission needs an annotation mode")
        if payload["annotation_mode"] == "model_assisted" and not payload["assistance_notes"].strip():
            raise ValueError("model-assisted submission needs model/tool and assistance notes")
    return dict(counts)


def render(packet):
    template = (HERE / "review-template.html").read_text()
    data = json.dumps(packet, ensure_ascii=False).replace("<", "\\u003c")
    guide = html.escape((HERE / "GUIDE.md").read_text())
    return template.replace("__PACKET_DATA__", data).replace("__GUIDE_TEXT__", guide)


def build():
    records = load_sources(ROOT)
    private = HERE / "private"
    packets = HERE / "packets"
    previous = None
    manifest_path = HERE / "packet-manifest.json"
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text())
        if previous["guide_version"] != "v1":
            raise ValueError("existing packets must not be regenerated or overwritten")
    for reviewer in (1, 2):
        targets = [packets / f"reviewer-{reviewer}-{VERSION}",
                   packets / f"issue21-reviewer-{reviewer}-122-cases-{VERSION}.zip"]
        if any(p.exists() for p in targets):
            raise ValueError("existing packets must not be regenerated or overwritten")
        mapping_path = private / f"reviewer-{reviewer}-mapping.jsonl"
        if mapping_path.exists() and read_rows(mapping_path) != make_packet(records, reviewer)[1]:
            raise ValueError("existing source/display mapping differs")
    source_path = private / "source-cases.jsonl"
    if source_path.exists() and read_rows(source_path) != records:
        raise ValueError("existing source cases differ")
    private.mkdir(exist_ok=True)
    packets.mkdir(exist_ok=True)
    if not source_path.exists():
        write_rows(source_path, records)
    accepted = []
    orders = []
    for reviewer in (1, 2):
        packet, mapping = make_packet(records, reviewer)
        folder = packets / f"reviewer-{reviewer}-{VERSION}"
        folder.mkdir()
        page = render(packet)
        (folder / "review.html").write_text(page)
        (folder / "README.md").write_text((HERE / "reviewer-instructions.md").read_text())
        (folder / "GUIDE.md").write_text((HERE / "GUIDE.md").read_text())
        blank = blank_submission(packet)
        validate_submission(blank, packet)
        write_json(folder / "blank-answers.json", blank)
        mapping_path = private / f"reviewer-{reviewer}-mapping.jsonl"
        if not mapping_path.exists():
            write_rows(mapping_path, mapping)
        for original, m, case in (
            (next(r for r in records if r["source_query_id"] == m["source_query_id"]), m, case)
            for m, case in zip(mapping, packet["cases"], strict=True)
        ):
            if (case["query"] != original["query"] or any(
                    case["paragraphs"][side] != original["paragraphs"][m["display_mapping"][side]]
                    for side in ("X", "Y"))
                    or m["display_mapping"][case["reference_preference"]] != original["reference_chunk_id"]):
                raise ValueError("packet mapping/content/reference mismatch")
        embedded = json.loads(re.search(r'<script id="packet-data" type="application/json">(.*?)</script>',
                                       page, re.DOTALL).group(1))
        if embedded != packet:
            raise ValueError("embedded packet mismatch")
        for row in records:
            for forbidden in (row["source_query_id"], row["source_group_id"], *row["paragraphs"]):
                if forbidden in page:
                    raise ValueError("private identifier leaked into reviewer page")
        archive = packets / f"issue21-reviewer-{reviewer}-122-cases-{VERSION}.zip"
        names = ("review.html", "README.md", "GUIDE.md", "blank-answers.json")
        with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as z:
            for name in names:
                z.write(folder / name, f"{folder.name}/{name}")
        with zipfile.ZipFile(archive) as z:
            if z.testzip() is not None or set(z.namelist()) != {f"{folder.name}/{n}" for n in names}:
                raise ValueError("ZIP content check failed")
            for name in names:
                if z.read(f"{folder.name}/{name}") != (folder / name).read_bytes():
                    raise ValueError("ZIP bytes differ")
        accepted.append({
            "reviewer_slot": reviewer, "packet_id": packet["packet_id"], "cases": len(mapping),
            "reference_side_counts": dict(Counter(c["reference_preference"] for c in packet["cases"])),
            "zip": str(archive.relative_to(ROOT)), "zip_bytes": archive.stat().st_size,
            "source_mapping_verified": True, "public_fields_verified": True, "zip_verified": True,
        })
        orders.append([r["source_query_id"] for r in mapping])
    if orders[0] == orders[1] or set(orders[0]) != set(orders[1]):
        raise ValueError("reviewers must see the same cases in independently shuffled orders")
    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "preparation_code_uncommitted": True, "guide_version": VERSION,
        "annotation_protocol": "human-confirmed; model assistance allowed; one or two submissions",
        "selection": {
            "qwen_confirmation": 91, "gpt_confirmation": 60, "confirmation_intersection": 50,
            "confirmation_union": 101, "development_human_v5": 21, "total": 122,
            "qwen_noncorrect_with_technical_fallback": 2,
        },
        "source_files": sorted({p for r in records for p in r["source_files"]} | {
            str(folder / f) for folder in (QWEN, GPT) for f in ("results.json", "official-per-query.jsonl")
        }),
        "packets": accepted, "different_orders_verified": True,
        "human_submissions_received": 0, "model_calls": 0, "official_test_read": False,
        "blinding": "model identity/scores/previous reasons hidden; existing reference preference visible",
        "browser_acceptance": "pending",
    }
    if previous is not None:
        manifest["supersedes"] = {
            "guide_version": previous["guide_version"], "created_at": previous["created_at"],
            "packet_paths": [p["zip"] for p in previous["packets"]],
            "change": "Allow model assistance and a single human reviewer; categories/cases/mappings unchanged.",
        }
    write_json(HERE / "packet-manifest.json", manifest)
    print(json.dumps(manifest["selection"], ensure_ascii=False))
    print("Prepared both packets; no human labels generated.")


def receive(paths, out):
    if out.exists():
        raise ValueError("receive output already exists")
    if len(paths) != 2 or not any(paths):
        raise ValueError("provide at least one reviewer file")
    source = unique(read_rows(HERE / "private/source-cases.jsonl"), "source_query_id")
    submissions, normalized, summary = {}, [], []
    for reviewer, path in zip((1, 2), paths, strict=True):
        if path is None:
            continue
        packet, expected_mapping = make_packet(list(source.values()), reviewer)
        mapping_rows = read_rows(HERE / f"private/reviewer-{reviewer}-mapping.jsonl")
        if mapping_rows != expected_mapping:
            raise ValueError("saved display mapping differs from the source packet")
        mapping = unique(mapping_rows, "case_id")
        payload = json.loads(path.read_text())
        counts = validate_submission(payload, packet, require_final=True)
        for answer in payload["answers"]:
            m = mapping[answer["case_id"]]
            pref = answer["preference"]
            normalized.append({
                **answer, "reviewer_slot": reviewer, "reviewer_name": payload["reviewer_name"],
                "annotation_mode": payload["annotation_mode"],
                "assistance_notes": payload["assistance_notes"],
                "human_confirmed": payload["human_confirmed"],
                "previous_exposure": payload["previous_exposure"],
                "source_query_id": m["source_query_id"], "role": m["role"],
                "preferred_chunk_id": m["display_mapping"].get(pref),
                "nondirectional_preference": pref if pref not in ("X", "Y") else None,
            })
        submissions[reviewer] = payload
        summary.append({"reviewer_slot": reviewer, "status_counts": counts,
                        "annotation_mode": payload["annotation_mode"],
                        "assistance_notes": payload["assistance_notes"],
                        "previous_exposure": payload["previous_exposure"]})
    if (len(submissions) == 2 and submissions[1]["reviewer_name"].strip().casefold()
            == submissions[2]["reviewer_name"].strip().casefold()):
        raise ValueError("two reviewers need distinct identities; submit one file for one person")
    by_reviewer = [
        {r["source_query_id"]: r for r in normalized if r["reviewer_slot"] == reviewer}
        for reviewer in (1, 2)
    ]
    pairs = [(by_reviewer[0][qid], by_reviewer[1][qid]) for qid in source] if len(submissions) == 2 else []
    classified = [(a, b) for a, b in pairs if a["status"] == b["status"] == "reviewed"]
    agreement = sum(a["primary_type"] == b["primary_type"] for a, b in classified)
    disputes = [
        {"source_query_id": a["source_query_id"], "reviewer_1": a, "reviewer_2": b}
        for a, b in pairs if (
            a["status"] != "reviewed" or b["status"] != "reviewed"
            or a["primary_type"] != b["primary_type"]
            or a["preferred_chunk_id"] != b["preferred_chunk_id"]
            or a["nondirectional_preference"] != b["nondirectional_preference"])
    ]
    out.mkdir(parents=True)
    for reviewer in submissions:
        (out / f"reviewer-{reviewer}-original.json").write_bytes(paths[reviewer - 1].read_bytes())
    write_rows(out / "reviewer-labels.jsonl", normalized)
    write_rows(out / "disagreements.jsonl", disputes)
    uncertain = [
        r for r in normalized
        if r["status"] == "uncertain" or r["preference"] == "undetermined"
    ]
    write_rows(out / "uncertain.jsonl", uncertain)
    write_json(out / "receipt.json", {
        "received_at": datetime.now(UTC).isoformat(), "reviewers": summary,
        "human_reviewer_count": len(submissions),
        "paired_cases": len(pairs), "both_classified": len(classified),
        "primary_type_agree": agreement,
        "primary_type_agreement_rate": agreement / len(classified) if classified else None,
        "agreement_interpretation": (
            "descriptive_between_submissions; independence not established"
            if pairs else "unavailable_single_submission"
        ),
        "cases_needing_discussion": len({r["source_query_id"] for r in disputes + uncertain}),
        "uncertain_judgments": len(uncertain),
        "uncertain_status_judgments": sum(r["status"] == "uncertain" for r in normalized),
        "undetermined_preferences": sum(r["preference"] == "undetermined" for r in normalized),
        "uncertain_definition": "status=uncertain OR preference=undetermined; original fields retained",
        "adjudication_performed": False,
        "original_research_labels_modified": False,
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build")
    p = sub.add_parser("receive")
    p.add_argument("--reviewer-1", type=Path)
    p.add_argument("--reviewer-2", type=Path)
    p.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build":
        build()
    else:
        receive([args.reviewer_1, args.reviewer_2], args.out)


if __name__ == "__main__":
    main()
