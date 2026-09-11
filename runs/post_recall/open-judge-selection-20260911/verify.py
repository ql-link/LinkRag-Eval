"""Replay N10/N11 evaluation from saved scores; never invoke a judge or network."""

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PILOT = Path("runs/post_recall/llm-judge-pilot-20260910")
CONFIRMATION = Path("runs/post_recall/open-judge-confirmation-20260910")
MODELS = ("qwen3-8b", "qwen3-8b-think", "qwen3-14b-awq", "qwen3-14b-awq-think")


def read_json(path):
    return json.loads((ROOT / path).read_text())


def read_rows(path):
    with (ROOT / path).open() as stream:
        return [json.loads(line) for line in stream if line.strip()]


def comparable(result):
    """Only normalize paths; keep every metric and run field in the comparison."""
    result = dict(result)
    if "inputs" in result:
        result["inputs"] = {
            key: str((ROOT / value).resolve()) for key, value in result["inputs"].items()
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="A new output directory")
    args = parser.parse_args()
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    checks = []
    commands = []

    def replay(name, command, expected, filename="results.json"):
        target = output / name
        cli = [sys.executable, "scripts/llm_judge_pilot.py", *map(str, command)]
        cli += ["--output", str(target)] if filename is None else ["--out", str(target)]
        completed = subprocess.run(cli, cwd=ROOT, capture_output=True, text=True, check=True)
        (output / f"{name}.log").write_text(completed.stdout + completed.stderr)
        actual_path = target if filename is None else target / filename
        actual = json.loads(actual_path.read_text())
        equal = comparable(actual) == comparable(read_json(expected))
        checks.append({"name": name, "expected": str(expected), "all_fields_equal": equal})
        commands.append(cli)
        if not equal:
            raise AssertionError(f"Saved evaluation differs: {name}")
        print(f"PASS {name}", flush=True)

    for model in MODELS:
        judged = PILOT / f"l1-development-judge-{model}"
        replay(f"development-{model}", [
            "evaluate-l1", "--role", "development", "--baseline",
            PILOT / "baseline/development/scores.jsonl", "--scores", judged / "scores.jsonl",
        ], PILOT / f"l1-development-eval-{model}/results.json")
        replay(f"agreement-{model}.json", [
            "agreement", "--a", judged, "--b", PILOT / "l1-development-judge",
        ], PILOT / f"l1-development-agreement-{model}-vs-gpt6.json", filename=None)

    for suffix, label in (("", "first-pass"), ("-retry", "retry")):
        replay(f"l1-{label}", [
            "evaluate-l1", "--role", "confirmation", "--baseline",
            PILOT / "baseline/confirmation/scores.jsonl", "--scores",
            PILOT / f"l1-confirmation-judge-qwen3-14b-awq-think{suffix}/scores.jsonl",
        ], CONFIRMATION / f"l1-{label}/results.json")
        for top_k in (10, 20):
            replay(f"l2-{label}-k{top_k}", [
                "evaluate-l2", "--role", "confirmation", "--baseline",
                PILOT / "baseline/confirmation/scores.jsonl", "--stage1",
                PILOT / "items-stage1-top20/confirmation/stage1-confirmation.jsonl",
                "--scores",
                PILOT / f"l2s-confirmation-judge-qwen3-14b-awq-think{suffix}/scores.jsonl",
                "--top-k", top_k,
            ], CONFIRMATION / f"l2-{label}-k{top_k}/results.json")

    retry_checks = []
    for level in ("l1", "l2s"):
        run = PILOT / f"{level}-confirmation-judge-qwen3-14b-awq-think"
        first = read_rows(run / "scores.jsonl")
        retry = read_rows(Path(f"{run}-retry") / "scores.jsonl")
        assert len(first) == len(retry)
        identity = ("source_query_id", "chunk_id", "key", "model", "effort", "prompt_version")
        valid_preserved = all(
            all(a[k] == b[k] for k in identity)
            and (a["score"] is None or (a["score"], a["status"]) == (b["score"], b["status"]))
            for a, b in zip(first, retry, strict=True)
        )
        assert valid_preserved
        changed = sum((a["score"], a["status"]) != (b["score"], b["status"])
                      for a, b in zip(first, retry, strict=True))
        assert changed == (1 if level == "l1" else 0)
        retry_checks.append({"level": level, "rows": len(first),
                             "valid_scores_preserved": valid_preserved,
                             "changed_score_or_status_rows": changed})

    record = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                            text=True).strip(),
        "scope": "Four N10 L1 evaluations, four GPT agreements, six N11 evaluations; offline only",
        "model_requests": 0,
        "evaluations": checks,
        "retry_checks": retry_checks,
        "commands": commands,
        "status": "passed",
    }
    (output / "verification.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"PASS {len(checks)} saved reports and {len(retry_checks)} retry comparisons", flush=True)


if __name__ == "__main__":
    main()
