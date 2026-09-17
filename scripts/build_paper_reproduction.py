"""Build an allowlisted, local-only NevIR cached-score reproduction package.

Never traverses the manuscript directory or copies an entire run directory.
The output must not exist. Publication and inference are separate actions.
"""
from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import json
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs/post_recall"
MAIN = RUNS / "nevir-test-main-20260911"
SNAPSHOT = RUNS / "nevir-test-candidates-20260910/snapshot"
EARLY = RUNS / "nevir-ltr-validation-20260907/data-preparation/experiment"
REVISION = "6263585072ce3b435ed09658613553fbf4e74184"
LABEL_FIELDS = (
    "source_query_id", "source_group_id", "pair_id", "direction", "role",
    "preferred_chunk_id", "other_chunk_id", "official_label_available",
    "structural_conflict",
)


def rows(path):
    with Path(path).open() as stream:
        return [json.loads(line) for line in stream if line.strip()]


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def export_rows(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as stream:
        for value in values:
            stream.write((json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                                     allow_nan=False) + "\n").encode())


def select(value, keys):
    return {key: value[key] for key in keys}


def copied_functions(output):
    """Vendor only pure scoring functions; do not bundle runtime/service code."""
    source = ROOT / "src/linkrag_eval/retrieval/learning_to_rank"
    selections = {
        "llm_judge.py": ["baseline_order", "score_maps", "judged_scores", "relation", "metrics",
                         "contrast", "evaluate_pairs", "check_judged_scope", "resort",
                         "l2_rankers", "list_metrics", "evaluate_rankers", "plan_batches",
                         "prompt_for", "validate_response"],
        "nevir_evaluation.py": ["_bootstrap_delta"],
        "pair_statistics.py": ["_available", "_delta", "_ci", "strict_delta_ci"],
    }
    content = ['"""Pure functions extracted verbatim; provenance in manifest.json."""',
               "from __future__ import annotations", "import math", "import random",
               "from collections import Counter, defaultdict", "from itertools import pairwise",
               "import numpy as np", 'RELATIONS = frozenset({"strict_correct", "reverse", "model_tie", "unavailable"})',
               ("def _indexed(rows):\n    result = {}\n    for row in rows:\n"
               "        key = row['source_query_id']\n"
               "        if not isinstance(key, str) or not key or key in result:\n"
               "            raise ValueError('empty or duplicate query ID')\n"
               "        result[key] = row\n    return result\n")]
    origins = []
    for name, names in selections.items():
        text = (source / name).read_text()
        tree = ast.parse(text)
        found = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        for name_ in names:
            content.append(ast.get_source_segment(text, found[name_]))
        origins.append({"path": str((source / name).relative_to(ROOT)), "functions": names})
        if name == "llm_judge.py":
            constants = {}
            for node in tree.body:
                if (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                        and node.targets[0].id in {"JUDGE_PROMPT", "SCHEMA"}):
                    constants[node.targets[0].id] = ast.literal_eval(node.value)
            content.append("JUDGE_PROMPT = " + repr(constants["JUDGE_PROMPT"]))
            (output / "prompt.txt").write_text(constants["JUDGE_PROMPT"] + "\n")
            write(output / "schema.json", constants["SCHEMA"])
    (output / "core.py").write_text("\n\n".join(content) + "\n")
    return origins


def expected_result():
    result = {"test": {}, "l1": {}, "statistics": {}}
    for arm in ("qwen", "bge"):
        original = read(MAIN / f"{arm}-evaluation/results.json")
        for population in ("primary", "including_conflict"):
            level = original["populations"]["l2"][population]
            for name, source in (("E0", "E0"), ("fusion", "stage1"), (arm, "stage1_judge")):
                result["test"].setdefault(population, {})[name] = level["metrics"]["rankers"][source]
            result["statistics"].setdefault(population, {})[arm] = level["statistics"][0]["strict"]
            result["l1"].setdefault(population, {})[arm] = original["populations"]["l1"][population]["metrics"]["judge"]
    n8 = read(RUNS / "nevir-test-final-20260911/results.json")
    for population, old in (("primary", "primary_no_structural_conflict"),
                            ("including_conflict", "including_conflict")):
        result["test"][population]["n8_original_aggregate"] = n8["results"][old]["background_n8"]
    result["populations"] = {
        "train": {"planned": 1896, "used": 1869, "complete_pairs": None, "source_groups": 472},
        "development": {"planned": 76, "used": 74, "complete_pairs": 37, "source_groups": 19},
        "confirmation": {"planned": 374, "used": 371, "complete_pairs": 185, "source_groups": 96},
        "test": {"planned": 2766, "used": 2736, "complete_pairs": 1363, "source_groups": 699},
    }
    result["list_diagnostics"] = read(RUNS / "list-collapse-20260910/results.json")
    decomposition = read(MAIN / "qwen-decision-decomposition.json")["analysis"]
    result["decomposition"] = {k: select(v, ("n", "strict_correct", "reverse", "model_tie"))
                               for k, v in decomposition["branches"].items()}
    result["test"]["primary"]["qwen"]["fallback"] = decomposition["branches"]["whole_query_fallback"]["n"]
    unavailable_queries = {r["source_query_id"] for r in rows(MAIN / "l2-judge/scores.jsonl")
                           if r["status"] == "unavailable"}
    covered_queries = {r["source_query_id"] for r in rows(MAIN / "qwen-evaluation/l2-including_conflict-per-query.jsonl")}
    result["test"]["including_conflict"]["qwen"]["fallback"] = len(unavailable_queries & covered_queries)
    result["planned_fallback"] = {arm: read(MAIN / f"{arm}-evaluation/results.json")["l2_fallback_queries"]
                                  for arm in ("qwen", "bge")}
    for population in ("primary", "including_conflict"):
        result["test"][population]["bge"]["fallback"] = 0
    return result


def build(output):
    output.mkdir(parents=True, exist_ok=False)
    templates = ROOT / "docs/papers/artifacts"
    for name in ("README.md", "reproduce.py", "rerun_judge.py", "test_reproduction.py", "requirements.txt"):
        shutil.copyfile(templates / name, output / name)
    if (templates / "SELF_CHECK.md").exists():
        shutil.copyfile(templates / "SELF_CHECK.md", output / "SELF_CHECK.md")
    origins = copied_functions(output)
    sources = []

    def export(source, destination, fields=None):
        values = rows(source)
        if fields:
            values = [select(value, fields) for value in values]
        if fields == ("source_query_id", "scores"):
            for value in values:
                value["scores"] = [select(score, ("chunk_id", "score")) for score in value["scores"]]
        export_rows(output / destination, values)
        sources.append({"file": destination, "source": str(source.relative_to(ROOT)),
                        "rows": len(values), "fields": fields or "numeric full-pool scores only"})
        return values

    labels = {}
    for role in ("train", "development", "confirmation", "test"):
        root = SNAPSHOT if role == "test" else EARLY
        label_rows = rows(root / f"prepared/{role}/supervision.jsonl")
        coverage = {r["source_query_id"]: r for r in rows(root / f"coverage/{role}.jsonl")}
        if set(coverage) != {r["source_query_id"] for r in label_rows}:
            raise ValueError("coverage and label populations differ")
        exported = [{**select(r, LABEL_FIELDS),
                     "pair_in_union": coverage[r["source_query_id"]]["pair_in_union"],
                     "loss_eligible": coverage[r["source_query_id"]]["loss_eligible"]}
                    for r in label_rows]
        labels[role] = exported
        destination = f"data/{role}/labels.jsonl.gz"
        export_rows(output / destination, exported)
        sources.append({"file": destination, "source": str(root.relative_to(ROOT)),
                        "rows": len(exported), "fields": list(LABEL_FIELDS) + ["pair_in_union", "loss_eligible"]})
    for name, source in {
        "fusion": MAIN / "inputs/stage1-test.jsonl", "E0": MAIN / "baseline/scores.jsonl",
        "n8": RUNS / "n8-test-replay-20260914/scores.jsonl",
    }.items():
        export(source, f"data/test/{name}-scores.jsonl.gz", ("source_query_id", "scores"))
    for level in ("l1", "l2"):
        export(MAIN / f"{level}-judge/scores.jsonl", f"data/test/qwen-{level}-scores.jsonl.gz",
               ("source_query_id", "chunk_id", "score", "status"))
        export(MAIN / f"inputs/{level}-test.jsonl", f"data/test/{level}-items.jsonl.gz",
               ("source_query_id", "chunk_id", "pair_id", "level"))
    export(MAIN / "bge/scores.jsonl", "data/test/bge-scores.jsonl.gz",
           ("source_query_id", "chunk_id", "score", "status", "levels"))
    for role in ("development", "confirmation"):
        for name, prefix in (("E0", "E0"), ("n8", "background_n8")):
            export(RUNS / f"list-collapse-20260910/{prefix}-{role}-scores.jsonl",
                   f"data/{role}/{name}-scores.jsonl.gz", ("source_query_id", "scores"))
    export(RUNS / "llm-judge-pilot-20260910/items-stage1-top20/confirmation/stage1-confirmation.jsonl",
           "data/confirmation/fusion-scores.jsonl.gz", ("source_query_id", "scores"))

    # Verify every redistributed Test query/passage against the pinned public dataset.
    dataset_url = f"https://huggingface.co/datasets/orionweller/NevIR/resolve/{REVISION}/test.jsonl"
    with urllib.request.urlopen(dataset_url, timeout=60) as response:
        official = [json.loads(line) for line in response.read().decode().splitlines() if line.strip()]
    queries = rows(SNAPSHOT / "prepared/test/queries.jsonl")
    corpus = rows(SNAPSHOT / "prepared/corpus.jsonl")
    public_queries = {r[k] for r in official for k in ("q1", "q2")}
    public_passages = {r[k] for r in official for k in ("doc1", "doc2")}
    if {r["query"] for r in queries} != public_queries or {r["content"] for r in corpus} != public_passages:
        raise ValueError("prepared text differs from pinned public NevIR Test")
    mapping = {r["source_passage_id"]: r["chunk_id"] for r in rows(SNAPSHOT / "prepared/passage-mapping.jsonl")}
    passages = [{"chunk_id": mapping[r["source_passage_id"]], "passage": r["content"]} for r in corpus]
    export_rows(output / "data/test/queries.jsonl.gz", queries)
    export_rows(output / "data/test/passages.jsonl.gz", passages)
    query_map = {r["source_query_id"]: r["query"] for r in queries}
    passage_map = {r["chunk_id"]: r["passage"] for r in passages}
    for level in ("l1", "l2"):
        for r in rows(MAIN / f"inputs/{level}-test.jsonl"):
            if r["query"] != query_map[r["source_query_id"]] or r["passage"] != passage_map[r["chunk_id"]]:
                raise ValueError("inference input text differs from the public snapshot")
    license_url = "https://raw.githubusercontent.com/orionw/NevIR/main/LICENSE"
    with urllib.request.urlopen(license_url, timeout=30) as response:
        (output / "LICENSE-NevIR.txt").write_bytes(response.read())
    write(output / "dataset-provenance.json", {
        "repository": "orionweller/NevIR", "revision": REVISION, "source": dataset_url,
        "declared_license": "MIT", "license_source": license_url,
        "public_text_verified_exact": True, "queries": len(queries), "passages": len(passages),
        "note": "Only official public Test query and passage text; no human annotations or worker metadata.",
    })

    frozen, bge = read(MAIN / "frozen-config.json"), read(MAIN / "bge/execution-config.json")
    write(output / "config.json", {
        "top_k": 20, "statistics": {"seed": 20260910, "repeats": 2000},
        "historical_statistics_numpy": "2.5.3",
        "qwen": {"model": frozen["model"], "judge": select(frozen["judge_arguments"],
                 ("think", "max_tokens", "num_ctx", "workers", "batch_size", "temperature",
                  "timeout_seconds", "batch_shuffle_seed", "model_request_seed", "prompt_version")),
                 "server": select(frozen["server"], ("vllm", "torch", "transformers", "context_length",
                  "gpu_memory_utilization", "reasoning_parser", "seed", "python_version", "driver_version"))},
        "bge": {"model": bge["model"], "runtime": select(bge["runtime"],
                ("torch", "transformers", "batch_size", "max_input_tokens", "seed",
                 "attention_implementation", "gpu_memory_fraction_limit", "python_version"))},
    })
    write(output / "expected/summary.json", expected_result())
    summary = read(MAIN / "paper-summary.json")
    cost = summary["cost"]
    write(output / "historical-cost-summary.json", {
        "kind": "Historical aggregates, not reconstructible timing from scores",
        "e0_seconds": cost["e0"]["wall_seconds"],
        "e0_scope": cost["e0"]["timing_scope"],
        "bge": select(cost["bge"], ("items", "inference_wall_seconds", "total_wall_seconds", "timing_scope")),
        "qwen_observed_receipts": cost["qwen_observed_receipts"],
        "qwen_continuation_seconds": cost["qwen_continuation"]["wall_seconds"],
        "n8_original_time": None,
    })
    for arm in ("qwen", "bge"):
        for level in ("l1", "l2"):
            export(MAIN / f"{arm}-evaluation/{level}-primary-per-query.jsonl",
                   f"expected/{arm}-{level}-primary-per-query.jsonl.gz")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    write(output / "manifest.json", {
        "schema_version": 1, "issue": 26, "source_commit": commit, "code_functions": origins,
        "sources": sources, "expected_sources": [
            "runs/post_recall/nevir-test-main-20260911/{qwen,bge}-evaluation/results.json",
            "runs/post_recall/nevir-test-final-20260911/results.json",
            "runs/post_recall/list-collapse-20260910/results.json",
            "runs/post_recall/nevir-test-main-20260911/qwen-decision-decomposition.json"],
        "historical_scoring_commit": "b4d01d7bae361f72ab83643cc0a9df7280e06e65",
        "n8_score_origin": "2026-09-14 fixed-model replay; original per-query output unavailable",
        "publication": "Prepared locally only; no upload, release, commit or PR performed",
        "excluded": ["manuscript", "authors", "human annotations", "generated explanations",
                     "API credentials", "infrastructure endpoints", "databases", "model weights"],
    })
    checksums = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(output.rglob("*")) if p.is_file()}
    write(output / "checksums.json", checksums)


def archive(source, destination):
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as zip_:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                if path.is_symlink():
                    raise ValueError("symlinks are not distributable")
                zip_.write(path, Path("linkrag-nevir-reproduction") / path.relative_to(source))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    build(args.output.resolve())
    if args.archive:
        archive(args.output.resolve(), args.archive.resolve())
    print(json.dumps({"status": "built", "output": str(args.output), "archive": str(args.archive)}))


if __name__ == "__main__":
    main()
