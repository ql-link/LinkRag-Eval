"""Independently verify saved #15/#16 evaluations; never run model inference.

L2 pair decisions compare priority/score tuples directly. No production ranker,
metric function, evaluator or model client is imported by this verifier.
"""

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PILOT = ROOT / "runs/post_recall/llm-judge-pilot-20260910"
EXPERIMENT = ROOT / "runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment"
POLICY = ROOT / "runs/post_recall/subject-binding-pilot-20260908/human/adjudication/analysis-policy-v2.json"
MAPPING = ROOT / "runs/post_recall/nevir-offline-diagnostic-20260907/review/private/reviewer_1-mapping.jsonl"
STATES = ("strict_correct", "reverse", "model_tie", "unavailable")


class VerificationError(ValueError):
    """An input or output contradicts the declared evaluation."""


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def load(path):
    return json.loads(Path(path).read_text())


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def indexed(values, key, context):
    result = {}
    for value in values:
        identity = key(value)
        require(identity not in result, f"{context}: duplicate identity {identity}")
        result[identity] = value
    return result


def item_key(row):
    return row["source_query_id"], row["chunk_id"]


def score_maps(path):
    result = {}
    for qid, row in indexed(rows(path), lambda r: r["source_query_id"], str(path)).items():
        candidates = indexed(row["scores"], lambda r: r["chunk_id"], qid)
        require(all(type(r["score"]) in (int, float) and math.isfinite(r["score"])
                    for r in candidates.values()), f"{path}: nonfinite/nonnumeric baseline")
        result[qid] = {cid: row["score"] for cid, row in candidates.items()}
    return result


def scalar_order(scores):
    return sorted(scores, key=lambda cid: (-scores[cid], cid))


def relation(a, b):
    if a is None or b is None:
        return "unavailable"
    return "strict_correct" if a > b else "reverse" if a < b else "model_tie"


def human_preferences(base, policy_path=POLICY, mapping_path=MAPPING):
    policy = load(policy_path)
    source = Path(policy["human_results"])
    raw = source.read_bytes()
    # The existing frozen-label policy is the consumer of this integrity check.
    require(hashlib.sha256(raw).hexdigest() == policy["human_results_sha256"],
            "frozen human labels differ from the existing policy")
    human = json.loads(raw)
    require(policy["version"] == "human_pair_sensitivity_v2" and human["version"] == 5,
            "unexpected human policy/version")
    require(human["human_judgments_locked"] and not human["models_associated"],
            "human decisions were not independently locked")
    decisions = indexed(human["results"], lambda r: r["case_id"], "human decisions")
    mapping = indexed(rows(mapping_path), lambda r: r["case_id"], "human mapping")
    require(len(decisions) == 76 and decisions.keys() == mapping.keys(), "human mapping scope differs")
    chosen = {}
    for case, decision in decisions.items():
        pref = decision["proposal"]["pair_preference"]
        row = mapping[case]
        qid, displays = row["source_query_id"], row["display_mapping"]
        if pref in {"X", "Y"} and set(displays.values()) <= base[qid].keys():
            require(qid not in chosen, "duplicate eligible human query")
            chosen[qid] = (displays[pref], displays["Y" if pref == "X" else "X"])
    require(len(chosen) == 52, "human strict population is not 52")
    return chosen


def independent_l2(base, fused, judged, top_k):
    """Compare tuple values, without reproducing production rank-score assignment."""
    require(type(top_k) is int and top_k > 0, "invalid K")
    require(base.keys() == fused.keys() == judged.keys(), "L2 query populations differ")
    values = {"E0": base, "stage1": fused, "stage1_judge": {}, "E0_judge": {}}
    orders = {"E0": {q: scalar_order(s) for q, s in base.items()},
              "stage1": {q: scalar_order(s) for q, s in fused.items()},
              "stage1_judge": {}, "E0_judge": {}}
    failures = {}
    for qid, fusion in fused.items():
        require(fusion.keys() == base[qid].keys(), f"{qid}: baseline candidate scopes differ")
        top = set(orders["stage1"][qid][:top_k])
        require(top <= judged[qid].keys() <= fusion.keys(), f"{qid}: incomplete judge scope")
        missing = sum(judged[qid][cid] is None for cid in top)
        failures[qid] = missing
        for arm, secondary in (("stage1_judge", fusion), ("E0_judge", base[qid])):
            if missing:
                values[arm][qid] = fusion
                orders[arm][qid] = scalar_order(fusion)
            else:
                keys = {cid: ((1, judged[qid][cid], secondary[cid]) if cid in top else
                              (0, 0, fusion[cid])) for cid in fusion}
                values[arm][qid] = keys
                orders[arm][qid] = sorted(keys, key=lambda cid: (*(-x for x in keys[cid]), cid))
    return values, orders, failures


def metric(labels, states):
    counts = Counter(states[row["source_query_id"]] for row in labels)
    groups, pairs = defaultdict(list), defaultdict(list)
    for row in labels:
        groups[row["source_group_id"]].append(row["source_query_id"])
        pairs[row["pair_id"]].append(row)
    by_source = {group: {"n": len(qids), "strict_correct": sum(states[q] == "strict_correct" for q in qids)}
                 for group, qids in sorted(groups.items())}
    complete = [group for group in pairs.values() if len(group) == 2
                and {row["direction"] for row in group} == {"q1", "q2"}]
    both = sum(all(states[row["source_query_id"]] == "strict_correct" for row in group)
               for group in complete)
    n = len(labels)
    return {"n": n, **{key: counts[key] for key in STATES},
            "strict_accuracy": counts["strict_correct"] / n if n else None,
            "source_groups": len(groups), "by_source_group": by_source,
            "source_macro_accuracy": math.fsum(v["strict_correct"] / v["n"] for v in by_source.values())
            / len(groups) if groups else None,
            "eligible_bidirectional_pairs": len(complete), "both_directions_correct": both,
            "both_directions_accuracy": both / len(complete) if complete else None}


def list_metric(labels, orders, preferences):
    positions = []
    for row in labels:
        qid = row["source_query_id"]
        preferred, other = preferences[qid]
        rank = {cid: i for i, cid in enumerate(orders[qid], 1)}
        positions.append((rank[preferred], rank[other]))
    n = len(positions)
    return {"n": n, "preferred@1": sum(a == 1 for a, _ in positions) / n if n else None,
            "preferred@3": sum(a <= 3 for a, _ in positions) / n if n else None,
            "preferred_mrr": math.fsum(1 / a for a, _ in positions) / n if n else None,
            "mean_rank_preferred": math.fsum(a for a, _ in positions) / n if n else None,
            "mean_rank_other": math.fsum(b for _, b in positions) / n if n else None}


def verify_outputs(*, role, level, items, scores, result_dir, baseline, supervision,
                   stage1=None, top_k=None, per_query_dir=None):
    """Read and verify one evaluation; exposed for offline historical rehearsals."""
    require(role in {"development", "confirmation"} and level in {"l1", "l2"}, "unsupported scope")
    result_dir = Path(result_dir)
    per_query_dir = Path(per_query_dir) if per_query_dir else result_dir
    original, saved = rows(items), rows(scores)
    source = indexed(original, item_key, "frozen input")
    actual = indexed(saved, item_key, "saved scores")
    require(source.keys() == actual.keys(), "saved input ID scope differs")
    require(list(map(item_key, original)) == list(map(item_key, saved)), "input order changed")
    require(all(a[k] == b[k] for a, b in zip(original, saved, strict=True)
                for k in ("source_query_id", "chunk_id", "pair_id", "query", "passage", "level")),
            "saved query/passage or source metadata differs")
    require(all(r["level"] == level for r in saved), "unexpected input level")
    summary = load(Path(scores).with_name("summary.json"))
    report = load(result_dir / "results.json")
    require(report["role"] == role and report["judge_run"] == summary, "report runtime summary differs")
    require(summary["items"] == len(saved), "summary item count differs")
    require(summary["unavailable"] == sum(r["status"] == "unavailable" for r in saved),
            "summary unavailable count differs")
    identity_scores, judged = {}, defaultdict(dict)
    for row in saved:
        require((row["status"] == "available" and type(row["score"]) is int and 0 <= row["score"] <= 4)
                or (row["status"] == "unavailable" and row["score"] is None), "invalid LLM score/status")
        require(all(row[k] == summary[k] == report[k] for k in
                    ("model", "effort", "prompt_version", "codex_version")), "runtime identity differs")
        identity = tuple(row[k] for k in ("model", "effort", "prompt_version", "query", "passage"))
        value = (row["score"], row["status"], row["reason"])
        require(identity not in identity_scores or identity_scores[identity] == value,
                "deduplicated input has conflicting saved outcomes")
        identity_scores[identity] = value
        judged[row["source_query_id"]][row["chunk_id"]] = row["score"]
    require(summary["unique_keys"] == len(identity_scores), "unique input count differs")
    require(summary["duplicate_items"] == len(saved) - len(identity_scores), "duplicate count differs")
    base = score_maps(baseline)
    all_labels = indexed(rows(supervision), lambda r: r["source_query_id"], "supervision")
    labels = [r for r in all_labels.values() if r["official_label_available"] and
              {r["preferred_chunk_id"], r["other_chunk_id"]} <= base.get(r["source_query_id"], {}).keys()]
    official = {r["source_query_id"]: (r["preferred_chunk_id"], r["other_chunk_id"]) for r in labels}
    populations = {"official": official}
    if role == "development":
        populations["human_v5"] = human_preferences(base)
        require(set(populations["human_v5"]) <= official.keys(), "human/official query eligibility differs")
    failures, orders = {}, None
    if level == "l1":
        require({q: set(s) for q, s in judged.items()} == {q: set(pair) for q, pair in official.items()},
                "L1 score scope is not the complete designated covered population")
        values = {"E0": base, "judge": judged}
        expected_status = "completed_with_unavailable" if summary["unavailable"] else "completed"
    else:
        require(report["K"] == top_k, "result K differs")
        fused = score_maps(stage1)
        require({q: set(s) for q, s in judged.items()} ==
                {q: set(scalar_order(s)[:20]) for q, s in fused.items()}, "L2 input is not frozen top 20")
        values, orders, failures = independent_l2(base, fused, judged, top_k)
        observed = indexed(rows(result_dir / "orders.jsonl"), lambda r: r["source_query_id"], "orders")
        require(observed.keys() == base.keys(), "saved orders omit/add queries")
        for qid, row in observed.items():
            require(row["orders"] == {arm: order[qid] for arm, order in orders.items()},
                    f"{qid}: saved order differs from independent score keys")
        expected_status = "completed_with_fallback" if any(failures.values()) else "completed"
        for arm in ("stage1_judge", "E0_judge"):
            trigger = report["trigger"][arm]
            require(trigger["queries"] == len(base) and trigger["fallback_queries"] ==
                    sum(n > 0 for n in failures.values()), f"{arm}: fallback denominator/count differs")
            require(set(trigger["by_query"]) == base.keys(), f"{arm}: trigger query scope differs")
            for qid, missing in failures.items():
                entry = trigger["by_query"][qid]
                require(entry["unavailable"] == missing and entry["fallback"] == (missing > 0),
                        f"{arm}/{qid}: failure/fallback status differs")
    require(report["status"] == expected_status, "evaluation completion/failure status differs")
    checked = {}
    for population, preferences in populations.items():
        selected = [r for r in labels if r["source_query_id"] in preferences]
        require(len(selected) == len(preferences), f"{population}: eligible denominator differs")
        expected_states = {arm: {qid: relation(scores[qid].get(a), scores[qid].get(b))
                                for qid, (a, b) in preferences.items()} for arm, scores in values.items()}
        observed = indexed(rows(per_query_dir / f"{population}-per-query.jsonl"),
                           lambda r: r["source_query_id"], population)
        require(observed.keys() == preferences.keys(), f"{population}: per-query denominator differs")
        aggregates = {}
        for row in selected:
            qid = row["source_query_id"]
            require(all(observed[qid][key] == row[key] for key in
                        ("source_query_id", "source_group_id", "pair_id", "direction")),
                    f"{population}/{qid}: label identity differs")
            require(all(observed[qid][arm] == states[qid] for arm, states in expected_states.items()),
                    f"{population}/{qid}: saved state contradicts raw scores")
        for arm, states in expected_states.items():
            aggregates[arm] = metric(selected, states)
            observed_metric = (report[population][arm] if level == "l1" else
                               report[population]["rankers"][arm]["pairwise"])
            require(observed_metric == aggregates[arm], f"{population}/{arm}: aggregate counts differ")
            if level == "l2":
                require(report[population]["rankers"][arm]["list"] ==
                        list_metric(selected, orders[arm], preferences), f"{population}/{arm}: list metrics differ")
        checked[population] = {"n": len(selected), "methods": aggregates,
                               "fallback_queries": sum(failures.get(qid, 0) > 0 for qid in preferences)}
    return {"role": role, "level": level, "K": top_k, "results": str(result_dir / "results.json"),
            "model": summary["model"], "effort": summary["effort"], "prompt_version": summary["prompt_version"],
            "per_query_source": str(per_query_dir), "input_rows": len(saved),
            "unique_inputs": len(identity_scores), "unavailable_rows": summary["unavailable"],
            "orders_checked": len(base) if level == "l2" else 0,
            "fallback_queries_full_pool": sum(n > 0 for n in failures.values()),
            "populations": checked, "status": "passed"}


def verify_kind(kind):
    role = "development" if kind == "8b" else "confirmation"
    folder = ROOT / ("runs/post_recall/open-judge-qwen3-8b-development-20260911" if kind == "8b"
                     else "runs/post_recall/open-judge-confirmation-20260911")
    config = load(folder / ("execution-config.json" if kind == "8b" else "frozen-config.json"))
    require(load(folder / "execution-finished.json")["status"] == "completed", "inference is incomplete")
    jobs = indexed(config["jobs"], lambda job: job["level"], "declared jobs")
    common = {"role": role, "baseline": PILOT / f"baseline/{role}/scores.jsonl",
              "supervision": EXPERIMENT / f"prepared/{role}/supervision.jsonl"}
    l1_directory = folder / "l1"
    if kind == "8b":
        original_l1 = ROOT / config["existing_l1_result"]
        require(load(l1_directory / "results.json") == load(original_l1), "reused L1 result differs from original")
        l1_scores = PILOT / "l1-development-judge-qwen3-8b-think/scores.jsonl"
        l1_items = PILOT / "items/l1-development.jsonl"
        if not (l1_directory / "official-per-query.jsonl").exists():
            l1_directory = original_l1.parent
    else:
        l1_scores = ROOT / jobs["l1"]["output"] / "scores.jsonl"
        l1_items = ROOT / jobs["l1"]["input"]
    evaluations = [verify_outputs(**common, level="l1", items=l1_items, scores=l1_scores,
                                  result_dir=folder / "l1", per_query_dir=l1_directory)]
    for top_k in (10, 20):
        evaluations.append(verify_outputs(**common, level="l2", top_k=top_k,
            items=ROOT / jobs["l2"]["input"], scores=ROOT / jobs["l2"]["output"] / "scores.jsonl",
            result_dir=folder / f"l2-k{top_k}", stage1=PILOT / f"items-stage1-top20/{role}/stage1-{role}.jsonl"))
    for checked in evaluations:
        require(checked["model"] == config["model"]["served_name"] and checked["effort"] == "think"
                and checked["prompt_version"] == config["judge_arguments"]["prompt_version"],
                "evaluated model/prompt differs from the declared experiment")
        require(checked["populations"]["official"]["n"] == (74 if kind == "8b" else 371),
                "official denominator differs from the declared experiment")
        if kind == "8b":
            require(checked["populations"]["human_v5"]["n"] == 52, "human denominator changed")
    return {"kind": kind, "status": "passed", "model_calls": 0,
            "verified_at": datetime.now(UTC).isoformat(), "evaluations": evaluations}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("8b", "confirmation"), required=True)
    args = parser.parse_args()
    try:
        result = verify_kind(args.kind)
    except FileNotFoundError as exc:
        print(json.dumps({"status": "incomplete", "missing_path": str(exc.filename)}), file=sys.stderr)
        return 2
    except (VerificationError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
