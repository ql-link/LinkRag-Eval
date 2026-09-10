"""Offline pointwise judging of fixed candidate pools; labels never enter prompts."""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import subprocess
import tempfile
import time
import tomllib
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from itertools import pairwise
from pathlib import Path
from typing import Protocol

from .features import ENGLISH_FEATURE_VERSION, FEATURE_NAMES, build_online_features
from .pairwise_training import _indexed, _method_view

PROMPT_VERSION = "judge_prompt_v1"
STAGE1_FEATURE = "baseline_score"
JUDGE_PROMPT = """You are a strict evidence judge. For each item, decide how well the PASSAGE alone supports
answering the QUERY. Check every condition the query imposes: negation and its scope, which
entity does or has what (attribution), direction of comparisons, and any extra restriction.
Use only the passage; no outside knowledge. Score each item independently.
Score: 4 = the passage explicitly satisfies all conditions; 3 = satisfies all conditions but one
detail is only implicit; 2 = topically related but a required condition is not stated;
1 = a required condition is contradicted, negated, or attributed to a different entity;
0 = unrelated. Do not run commands or read files. Return JSON only, one entry per item id,
reason at most 25 words."""
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["items"], "properties": {
    "items": {"type": "array", "items": {"type": "object", "additionalProperties": False,
    "required": ["id", "score", "reason"], "properties": {"id": {"type": "string"},
    "score": {"type": "integer", "minimum": 0, "maximum": 4}, "reason": {"type": "string"}}}}}}


def read_rows(path):
    with Path(path).open() as f:
        return [json.loads(line) for line in f if line.strip()]


def write_json(path, value):
    with Path(path).open("x") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")


def write_rows(path, rows):
    with Path(path).open("x") as f:
        f.writelines(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows)


def runtime_metadata(model=None, effort="low"):
    if effort not in {"low", "medium"}:
        raise ValueError("effort must be low or medium")
    config = tomllib.loads((Path.home() / ".codex/config.toml").read_text())
    effective = model or config.get("model")
    if not effective:
        raise ValueError("cannot resolve effective Codex model")
    return {"prompt_version": PROMPT_VERSION, "model": effective, "effort": effort,
            "codex_version": subprocess.check_output(["codex", "--version"], text=True).strip()}


def _pool_features(queries, inputs):
    planned, pools = _indexed(queries), _indexed(inputs)
    if set(planned) != set(pools):
        raise ValueError("candidate query population mismatch")
    for qid, q in planned.items():
        view = _method_view(pools[qid], q["query"])
        ids, matrix = build_online_features(**view, feature_version=ENGLISH_FEATURE_VERSION)
        yield qid, ids, matrix


def stage1_scores(queries, inputs):
    column = FEATURE_NAMES.index(STAGE1_FEATURE)
    return [{"source_query_id": qid, "scores": [{"chunk_id": cid, "score": float(value)}
             for cid, value in zip(ids, matrix[:, column], strict=True)]}
            for qid, ids, matrix in _pool_features(queries, inputs)]


def baseline_scores(queries, inputs, booster):
    result = []
    for qid, ids, matrix in _pool_features(queries, inputs):
        values = booster.predict(matrix, num_threads=1)
        if len(values) != len(ids) or not all(math.isfinite(v) for v in values):
            raise ValueError("invalid baseline scores")
        result.append({"source_query_id": qid, "scores": [
            {"chunk_id": cid, "score": float(v)} for cid, v in zip(ids, values, strict=True)]})
    return result


def check_exact(actual, saved):
    a, b = _indexed(actual), _indexed(saved)
    if list(a) != list(b) or any(a[q]["scores"] != b[q]["scores"] for q in a):
        raise ValueError("full-pool scores/order differ from reference")


def score_maps(predictions):
    result = {}
    for qid, row in _indexed(predictions).items():
        scores = {v["chunk_id"]: v["score"] for v in row["scores"]}
        if len(scores) != len(row["scores"]) or not all(
            type(v) in (int, float) and math.isfinite(v) for v in scores.values()
        ):
            raise ValueError("invalid/duplicate prediction score")
        result[qid] = scores
    return result


def baseline_order(scores):
    return sorted(scores, key=lambda cid: (-scores[cid], cid))


def build_items(queries, supervision, inputs, predictions=None, *, stage1=None, level="l1", top_k=20):
    if level not in {"l1", "l2", "l3"} or type(top_k) is not int or top_k < 1:
        raise ValueError("invalid item level/top K")
    planned, labels, pools = map(_indexed, (queries, supervision, inputs))
    if (level == "l1" and (predictions is None or stage1 is not None)) or (
            level != "l1" and (stage1 is None or predictions is not None)):
        raise ValueError("L1 requires baseline predictions; L2/L3 require stage1 scores only")
    scores = score_maps(predictions if level == "l1" else stage1)
    if not set(planned) == set(labels) == set(pools) == set(scores):
        raise ValueError("item input query population mismatch")
    items = []
    for qid, q in planned.items():
        view = _method_view(pools[qid], q["query"])
        contents, label = view["candidate_contents"], labels[qid]
        if set(scores[qid]) != set(contents):
            raise ValueError("ranking scores must cover the complete candidate pool")
        if level == "l1":
            selected = [label["preferred_chunk_id"], label["other_chunk_id"]]
            if not label["official_label_available"] or not set(selected) <= set(contents):
                continue
        else:
            selected = baseline_order(scores[qid])[:top_k]
        for cid in selected:
            items.append({"source_query_id": qid, "chunk_id": cid, "pair_id": label["pair_id"],
                          "query": q["query"], "passage": contents[cid], "level": level})
    return items


def plan_batches(items, *, batch_size=40, seed=20260910):
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("batch size must be positive")
    groups = defaultdict(list)
    for item in items:
        groups[item["pair_id"]].append(item)
    if not groups:
        return []
    count = max(math.ceil(len(items) / batch_size), max(map(len, groups.values())))
    batches = [[] for _ in range(count)]
    rng = random.Random(seed)
    grouped = list(groups.values())
    rng.shuffle(grouped)
    grouped.sort(key=len, reverse=True)
    for group in grouped:
        rng.shuffle(group)
        slots = list(range(count))
        rng.shuffle(slots)
        slots.sort(key=lambda i: len(batches[i]))
        for item, slot in zip(group, slots, strict=False):
            batches[slot].append(item)
    for batch in batches:
        rng.shuffle(batch)
    return [b for b in batches if b]


def cache_key(item, metadata):
    parts = [metadata[k] for k in ("prompt_version", "model", "effort")]
    return hashlib.sha256(json.dumps([*parts, item["query"], item["passage"]],
                                     ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def prompt_for(items):
    return JUDGE_PROMPT + "\n\n" + "\n\n".join(
        f"ITEM id=i{i:02d}\nQUERY: {r['query']}\nPASSAGE: {r['passage']}"
        for i, r in enumerate(items, 1)) + "\n"


def validate_response(value, count):
    if not isinstance(value, dict) or set(value) != {"items"} or not isinstance(value["items"], list):
        raise ValueError("invalid response object")
    expected = {f"i{i:02d}" for i in range(1, count + 1)}
    result = {}
    for r in value["items"]:
        if (not isinstance(r, dict) or set(r) != {"id", "score", "reason"}
                or not isinstance(r["id"], str) or r["id"] not in expected or r["id"] in result
                or type(r["score"]) is not int or not 0 <= r["score"] <= 4
                or not isinstance(r["reason"], str)):
            raise ValueError("invalid/duplicate item, score or reason")
        result[r["id"]] = r
    if set(result) != expected:
        raise ValueError("missing response ids")
    return [result[f"i{i:02d}"] for i in range(1, count + 1)]


class JudgeRunner(Protocol):
    def run(self, prompt: str, out: Path) -> dict: ...


class CodexRunner:
    def __init__(self, *, model=None, effort="low", timeout=600, isolated_state=False):
        self.metadata = runtime_metadata(model, effort)
        self.model, self.effort, self.timeout = model, effort, timeout
        self.isolated_state = isolated_state

    def run(self, prompt, out):
        # Only prompt/schema enter the isolated cwd; the local identity map stays outside it.
        with tempfile.TemporaryDirectory(prefix="llm-judge-") as folder:
            cwd = Path(folder)
            write_json(cwd / "schema.json", SCHEMA)
            (cwd / "prompt.txt").write_text(prompt)
            command = ["codex", "exec", "--ephemeral", "--skip-git-repo-check", "-s", "read-only",
                       "--color", "never", "-c", f"model_reasoning_effort={self.effort}"]
            if self.model:
                command.extend(["-m", self.model])
            command.extend(["--output-schema", "schema.json", "-o", "out.json", "-"])
            overrides = {"CODEX_SQLITE_HOME": str(cwd / "state")} if self.isolated_state else {}
            write_json(out / "command.json", {**self.metadata, "argv": command, "cwd": folder,
                                              "environment_overrides": overrides})
            try:
                proc = subprocess.run(command, cwd=cwd, input=prompt, text=True,
                                      capture_output=True, timeout=self.timeout, check=False,
                                      env=dict(os.environ, **overrides))
            except subprocess.TimeoutExpired as exc:
                for name, data in (("stdout", exc.stdout), ("stderr", exc.stderr)):
                    (out / f"{name}.txt").write_text(data.decode() if isinstance(data, bytes) else data or "")
                raise
            for name in ("stdout", "stderr"):
                (out / f"{name}.txt").write_text(getattr(proc, name))
            write_rows(out / "events.jsonl", [dict(self.metadata, stream=name, line=line)
                       for name in ("stdout", "stderr") for line in getattr(proc, name).splitlines()])
            if (cwd / "out.json").exists():
                (out / "out.json").write_bytes((cwd / "out.json").read_bytes())
            if proc.returncode:
                raise RuntimeError(f"codex exited {proc.returncode}; see batch stderr")
            return json.loads((out / "out.json").read_text())


def judge_items(items, runner, out, *, metadata, cache_dirs=(), batch_size=40, workers=4, seed=20260910):
    if workers < 1 or metadata["prompt_version"] != PROMPT_VERSION:
        raise ValueError("invalid workers/prompt version")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    cache = {}
    for directory in cache_dirs:
        for path in sorted(Path(directory).glob("*.jsonl")):
            for r in read_rows(path):
                judged_scores([dict(r, source_query_id="cache", chunk_id="cache")])
                if r["status"] == "unavailable":
                    continue  # infrastructure failures are not terminal; retry in later runs
                if r["key"] in cache and cache[r["key"]] != r:
                    raise ValueError("conflicting cache records")
                cache[r["key"]] = r
    unique = {cache_key(r, metadata): r for r in items}
    if any(any(cache[key].get(k) != metadata[k] for k in ("model", "effort", "prompt_version"))
           for key in unique if key in cache):
        raise ValueError("cache key metadata mismatch")
    pending = [r for key, r in unique.items() if key not in cache]
    cache_out = out / "judge-cache"
    cache_out.mkdir()
    batches = plan_batches(pending, batch_size=batch_size, seed=seed)

    def execute(batch, name, failures=0):
        folder = out / name
        folder.mkdir()
        prompt = prompt_for(batch)
        (folder / "prompt.txt").write_text(prompt)
        write_json(folder / "schema.json", SCHEMA)
        write_rows(folder / "mapping.jsonl", [dict(metadata, id=f"i{i:02d}",
                   key=cache_key(r, metadata), source_query_id=r["source_query_id"],
                   chunk_id=r["chunk_id"], pair_id=r["pair_id"]) for i, r in enumerate(batch, 1)])
        tick = time.perf_counter()
        error = None
        try:
            raw = runner.run(prompt, folder)
            if not (folder / "out.json").exists():
                write_json(folder / "out.json", raw)
            values = validate_response(raw, len(batch))
        except (ValueError, TypeError, KeyError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
            error = f"{type(exc).__name__}: {exc}"
        write_json(folder / "metadata.json", dict(metadata, wall_seconds=time.perf_counter() - tick,
                   item_count=len(batch), failure_number=failures + bool(error), error=error))
        if error:
            if failures == 0:
                return execute(batch, name + "-retry", 1) + 1
            if failures == 1:
                middle = max(1, len(batch) // 2)
                return 1 + sum(execute(part, name + f"-split{i}", 2)
                               for i, part in enumerate((batch[:middle], batch[middle:])) if part)
            values = [{"score": None, "reason": "", "status": "unavailable"} for _ in batch]
        records = [dict(metadata, key=cache_key(item, metadata), score=value["score"],
                        reason=value["reason"], status=value.get("status", "available"))
                   for item, value in zip(batch, values, strict=True)]
        write_rows(cache_out / f"{name}.jsonl", records)
        return 1

    with ThreadPoolExecutor(max_workers=workers) as pool:
        calls = list(pool.map(lambda pair: execute(pair[1], f"batch-{pair[0]:03d}"), enumerate(batches, 1)))
    for path in sorted(cache_out.glob("*.jsonl")):
        for r in read_rows(path):
            cache[r["key"]] = r
    results = [dict(r, **cache[cache_key(r, metadata)]) for r in items]
    write_rows(out / "scores.jsonl", results)
    summary = dict(metadata, items=len(items), unique_keys=len(unique),
                   cache_hits=len(unique) - len(pending), cache_misses=len(pending),
                   duplicate_items=len(items) - len(unique), planned_batches=len(batches),
                   batch_count=sum(calls), workers=workers, batch_size=batch_size, seed=seed,
                   unavailable=sum(r["status"] == "unavailable" for r in results),
                   wall_seconds=time.perf_counter() - started)
    write_json(out / "summary.json", summary)
    return results, summary


def judged_scores(rows):
    scores = defaultdict(dict)
    for r in rows:
        qid, cid = r["source_query_id"], r["chunk_id"]
        if cid in scores[qid]:
            raise ValueError("duplicate judged candidate")
        value = r["score"]
        if ((r["status"] == "available" and (type(value) is not int or not 0 <= value <= 4))
                or (r["status"] == "unavailable" and value is not None)
                or r["status"] not in {"available", "unavailable"}):
            raise ValueError("invalid judged availability/score")
        scores[qid][cid] = value
    return dict(scores)


def check_judged_scope(judged, stage1, *, top_k):
    """Validate coverage, returning only stage-1 top K; same-pool supersets are allowed."""
    if type(top_k) is not int or top_k < 1:
        raise ValueError("top K must be positive")
    expected = {qid: baseline_order(scores)[:top_k] for qid, scores in stage1.items()}
    if set(judged) != set(expected) or any(
            not set(expected[qid]) <= set(judged[qid]) or not set(judged[qid]) <= set(stage1[qid])
            for qid in expected):
        raise ValueError("judged candidates must cover stage1 top K within the saved pool, including unavailable rows")
    return {qid: {cid: judged[qid][cid] for cid in ids} for qid, ids in expected.items()}


def relation(preferred, other):
    if preferred is None or other is None:
        return "unavailable"
    if preferred > other:
        return "strict_correct"
    return "reverse" if preferred < other else "model_tie"


def metrics(rows, key):
    counts = Counter(r[key] for r in rows)
    groups, pairs = defaultdict(list), defaultdict(list)
    for r in rows:
        groups[r["source_group_id"]].append(r)
        pairs[r["pair_id"]].append(r)
    by_source = {s: {"n": len(rs), "strict_correct": sum(r[key] == "strict_correct" for r in rs)}
                 for s, rs in sorted(groups.items())}
    complete = [rs for rs in pairs.values() if len(rs) == 2 and
                {r["direction"] for r in rs} == {"q1", "q2"}]
    both = sum(all(r[key] == "strict_correct" for r in rs) for rs in complete)
    n = len(rows)
    return {"n": n, **{k: counts[k] for k in ("strict_correct", "reverse", "model_tie", "unavailable")},
            "strict_accuracy": counts["strict_correct"] / n if n else None,
            "source_groups": len(groups), "by_source_group": by_source,
            "source_macro_accuracy": math.fsum(v["strict_correct"] / v["n"] for v in by_source.values())
            / len(groups) if groups else None,
            "eligible_bidirectional_pairs": len(complete), "both_directions_correct": both,
            "both_directions_accuracy": both / len(complete) if complete else None}


def contrast(rows, baseline="E0", model="judge"):
    counts = Counter((r[baseline] == "strict_correct", r[model] == "strict_correct") for r in rows)
    return {"n": len(rows), "common_correct": counts[True, True], "corrected": counts[False, True],
            "damaged": counts[True, False], "common_not_correct": counts[False, False],
            "net": counts[False, True] - counts[True, False]}


def evaluate_pairs(supervision, baseline, judged, *, human=None):
    rows = []
    for label in supervision:
        qid = label["source_query_id"]
        preferred, other = label["preferred_chunk_id"], label["other_chunk_id"]
        if (not label["official_label_available"] or
                not {preferred, other} <= baseline.get(qid, {}).keys()):
            continue
        if human is not None:
            if qid not in human:
                continue
            preferred, other = human[qid]
        row = {k: label[k] for k in ("source_query_id", "source_group_id", "pair_id", "direction")}
        row.update(E0=relation(baseline[qid][preferred], baseline[qid][other]),
                   judge=relation(judged.get(qid, {}).get(preferred), judged.get(qid, {}).get(other)))
        rows.append(row)
    report = {"E0": metrics(rows, "E0"), "judge": metrics(rows, "judge"), "contrast": contrast(rows),
              "contrast_by_source_group": {s: contrast([r for r in rows if r["source_group_id"] == s])
                  for s in sorted({r["source_group_id"] for r in rows})}}
    return report, rows


def human_population(policy_path, mapping_path, baseline):
    policy = json.loads(Path(policy_path).read_text())
    raw = Path(policy["human_results"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != policy["human_results_sha256"]:
        raise ValueError("frozen human decisions changed")
    human = json.loads(raw)
    if policy["version"] != "human_pair_sensitivity_v2" or human["version"] != 5:
        raise ValueError("expected human v5 / analysis policy v2")
    if not human["human_judgments_locked"] or human["models_associated"]:
        raise ValueError("human judgments must be frozen before association")
    records = read_rows(mapping_path)
    maps = {r["case_id"]: r for r in records}
    if (len(maps) != len(records) or len(human["results"]) != 76 or
            set(maps) != {r["case_id"] for r in human["results"]}):
        raise ValueError("human mapping population mismatch")
    eligible, exclusions = {}, Counter()
    for h in human["results"]:
        m = maps[h["case_id"]]
        qid, target = m["source_query_id"], m["display_mapping"]
        pref = h["proposal"]["pair_preference"]
        covered = set(target.values()) <= baseline[qid].keys()
        if pref not in {"X", "Y"}:
            exclusions[{None: "unresolved", "tie": "human_tie", "undetermined": "human_undetermined"}[pref]] += 1
        if not covered:
            exclusions["targets_not_jointly_recalled"] += 1
        if covered and pref in {"X", "Y"}:
            eligible[qid] = (target[pref], target["Y" if pref == "X" else "X"])
    if len(eligible) != 52:
        raise ValueError("human strict population must be exactly 52")
    return eligible, {"eligible": len(eligible), "all_queries": 76, "exclusions_nonexclusive": dict(exclusions)}


def resort(stage1, judged, *, secondary=None, top_k=20):
    """Re-sort stage-1 top K; unavailable scores fall back to stage 1 for the query."""
    if type(top_k) is not int or top_k < 1:
        raise ValueError("top K must be positive")
    secondary = stage1 if secondary is None else secondary
    if set(secondary) != set(stage1):
        raise ValueError("secondary scores must cover the same stage1 pool")
    order = baseline_order(stage1)
    top = order[:top_k]
    available = sum(judged.get(cid) is not None for cid in top)
    stats = {"K": top_k, "judged_calls": len(top), "top_k_candidates": len(top), "available": available,
             "unavailable": len(top) - available, "fallback": available != len(top),
             "triggered": False, "moved_candidates": 0}
    if available != len(top):
        return order, dict(stage1), stats
    keys = {cid: (1, judged[cid], secondary[cid]) if cid in top else (0, 0, stage1[cid])
            for cid in order}
    front = sorted(top, key=lambda cid: (-judged[cid], -secondary[cid], cid))
    final = front + order[top_k:]
    values = {cid: -float(i) for i, cid in enumerate(final)}
    for a, b in pairwise(final):
        if keys[a] == keys[b]:
            values[b] = values[a]
    stats.update(triggered=front != top,
                 moved_candidates=sum(a != b for a, b in zip(front, top, strict=True)))
    return final, values, stats


def l2_rankers(baseline, stage1, judged, *, top_k=20):
    if set(baseline) != set(stage1) or any(set(baseline[q]) != set(stage1[q]) for q in baseline):
        raise ValueError("E0/stage1 candidate populations differ")
    selected = check_judged_scope(judged, stage1, top_k=top_k)
    rankers = {"E0": baseline, "stage1": stage1, "stage1_judge": {}, "E0_judge": {}}
    orders = {name: {q: baseline_order(s) for q, s in scores.items()} for name, scores in rankers.items()}
    triggers = {}
    for name, secondary in (("stage1_judge", stage1), ("E0_judge", baseline)):
        by_query = {}
        for qid, scores in stage1.items():
            order, values, stats = resort(scores, selected[qid], secondary=secondary[qid], top_k=top_k)
            rankers[name][qid], orders[name][qid], by_query[qid] = values, order, stats
        triggers[name] = {"K": top_k, "queries": len(by_query),
                          "fallback_queries": sum(s["fallback"] for s in by_query.values()),
                          "changed_queries": sum(s["triggered"] for s in by_query.values()),
                          "judged_calls_per_query": {q: s["judged_calls"] for q, s in by_query.items()},
                          "judged_calls_definition": "top-K query/passage judgments used; includes cache hits, not subprocess batches",
                          "by_query": by_query}
    return rankers, orders, triggers


def list_metrics(rows, orders, labels, *, human=None):
    """One-based list positions after deterministic chunk-ID tie breaking."""
    ranks = []
    for row in rows:
        qid = row["source_query_id"]
        preferred, other = (human[qid] if human is not None else
                            (labels[qid]["preferred_chunk_id"], labels[qid]["other_chunk_id"]))
        positions = {cid: i for i, cid in enumerate(orders[qid], 1)}
        ranks.append((positions[preferred], positions[other]))
    n = len(ranks)
    return {"n": n, "preferred@1": sum(p == 1 for p, _ in ranks) / n if n else None,
            "preferred@3": sum(p <= 3 for p, _ in ranks) / n if n else None,
            "preferred_mrr": math.fsum(1 / p for p, _ in ranks) / n if n else None,
            "mean_rank_preferred": math.fsum(p for p, _ in ranks) / n if n else None,
            "mean_rank_other": math.fsum(o for _, o in ranks) / n if n else None}


def evaluate_rankers(supervision, rankers, orders, *, human=None):
    base, labels = rankers["E0"], _indexed(supervision)
    if not {"E0", "stage1"} <= rankers.keys() or set(orders) != set(rankers):
        raise ValueError("ranker report requires E0, stage1 and matching orders")
    report, combined = {}, {}
    for name, scores in rankers.items():
        if set(scores) != set(base) or set(orders[name]) != set(base):
            raise ValueError("ranker query population mismatch")
        if any(set(scores[q]) != set(base[q]) or set(orders[name][q]) != set(base[q])
               or len(orders[name][q]) != len(base[q]) for q in base):
            raise ValueError("ranker candidate/order population mismatch")
        pair_report, rows = evaluate_pairs(supervision, base, scores, human=human)
        report[name] = {"pairwise": pair_report["judge"],
                        "list": list_metrics(rows, orders[name], labels, human=human)}
        for row in rows:
            qid = row["source_query_id"]
            combined.setdefault(qid, {k: row[k] for k in
                ("source_query_id", "source_group_id", "pair_id", "direction")})[name] = row["judge"]
    rows = list(combined.values())
    contrasts = {reference: {name: {**contrast(rows, reference, name),
                  "by_source_group": {s: contrast([r for r in rows if r["source_group_id"] == s], reference, name)
                  for s in sorted({r["source_group_id"] for r in rows})}}
                  for name in rankers if name != reference} for reference in ("E0", "stage1")}
    return {"rankers": report, "contrasts": contrasts}, rows
