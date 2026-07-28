#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${OUT:-$ROOT/runs/golden_v2/scale_100k_991004/scale_20k_overnight/ltr_query_expansion_2000}"
MAX_JOBS="${MAX_JOBS:-4}"
SKIP_SPARK="${SKIP_SPARK:-0}"
mkdir -p "$OUT/generated" "$OUT/generation_logs"

validate_batch() {
  local targets="$1" generated="$2"
  python3 - "$targets" "$generated" <<'PY'
import json
import re
import sys
from pathlib import Path

targets_path, generated_path = map(Path, sys.argv[1:])
targets = {row["query_id"]: row for row in map(json.loads, targets_path.read_text().splitlines())}
rows = [json.loads(line) for line in generated_path.open(encoding="utf-8") if line.strip()]
if len(rows) != len(targets) or {row.get("query_id") for row in rows} != set(targets):
    raise SystemExit("generated IDs do not match targets")
if len({str(row.get("query") or "").strip() for row in rows}) != len(rows):
    raise SystemExit("duplicate queries in batch")
required = {
    "query_id", "query", "type_hint", "hard_reason", "target_chunk_id",
    "reason", "generator_model",
}
number_re = re.compile(r"\d+(?:\.\d+)?")
for row in rows:
    if not required.issubset(row):
        raise SystemExit("missing fields")
    target = targets[row["query_id"]]
    if row["type_hint"] != target["type_hint"]:
        raise SystemExit("type_hint mismatch")
    if str(row["target_chunk_id"]) != str(target["target"]["chunk_id"]):
        raise SystemExit("target_chunk_id mismatch")
    if row["generator_model"] not in {"gpt-5.3-codex-spark", "gpt-5.4-mini"}:
        raise SystemExit("generator model mismatch")
    query = str(row["query"]).strip()
    length = len(query)
    limits = {
        "short_keyword": (4, 15),
        "exact_identifier": (8, 30),
        "dense_paraphrase": (16, 40),
        "alias": (12, 40),
        "number_time": (12, 60),
        "multi_constraint": (30, 120),
        "similar_docs": (16, 70),
    }
    low, high = limits[row["type_hint"]]
    if not low <= length <= high:
        raise SystemExit(f"invalid query length: {row['query_id']} {length}")
    query_numbers = set(number_re.findall(query))
    target_numbers = set(number_re.findall(target["target"]["content"]))
    if not query_numbers.issubset(target_numbers):
        raise SystemExit(f"invented numeric value: {row['query_id']}")
PY
}

run_generator_model() {
  local model="$1" targets="$2" generated="$3" log="$4" prompt="$5" attempts="$6"
  local attempt model_prompt
  model_prompt="$prompt
Set generator_model exactly to $model."
  for attempt in $(seq 1 "$attempts"); do
    rm -f "$generated"
    if (
      cd "$ROOT"
      codex --ask-for-approval never -c model_reasoning_effort=high exec --ephemeral \
        --model "$model" --sandbox workspace-write "$model_prompt"
    ) >"${log%.log}_${model}_attempt_${attempt}.log" 2>&1 && validate_batch "$targets" "$generated"; then
      return 0
    fi
  done
  return 1
}

generate_one() {
  local targets="$1"
  local stem generated log prompt
  stem="$(basename "$targets" .jsonl)"
  generated="$OUT/generated/${stem}.jsonl"
  log="$OUT/generation_logs/${stem}.log"
  prompt="This is a constrained data task. Read only ${targets#$ROOT/}; do not search the repository, inspect other files, or run project tests.
Generate exactly one realistic Chinese retrieval query for every row.
The query must be fully answered by target.content and must not be fully answered by any hard_negatives content.
Preserve query_id, type_hint, hard_reason, and target.chunk_id exactly.
For each row, copy target_chunk_id only from that same row's target.chunk_id; never transfer an ID between rows.
If rewrite_context exists, do not repeat rejected_query; use judge_reason to remove the unsupported scope and make
the target's decisive condition and outcome explicit.
Rules by type_hint:
- similar_docs: ask for a decisive condition or outcome that distinguishes the target from the highly similar negatives; 16-70 Chinese characters.
- multi_constraint: include at least two conditions explicitly supported by the target; 30-120 characters.
- number_time: include a number/date/time/threshold that occurs verbatim in target.content; 12-60 characters.
- alias: use a natural alias or indirect expression instead of copying the target's main object phrase; 12-40 characters.
- dense_paraphrase: semantic paraphrase with low surface overlap; 16-40 characters.
- short_keyword: natural terse search phrase; 4-15 characters.
- exact_identifier: use only the object, exact identifier/version/time, and core action; no explanatory tail; 8-24 Chinese characters (hard maximum 30).
Never invent a number, identifier, condition, exception, or outcome. Avoid copying a complete source sentence.
Write JSONL only to ${generated#$ROOT/}, exactly one row per target, with:
query_id, query, type_hint, hard_reason, target_chunk_id, reason, generator_model."
  if [[ -f "$generated" ]] && validate_batch "$targets" "$generated"; then
    return
  fi
  if [[ "$SKIP_SPARK" != "1" ]]; then
    if run_generator_model "gpt-5.3-codex-spark" "$targets" "$generated" "$log" "$prompt" 1; then
      return
    fi
  fi
  if run_generator_model "gpt-5.4-mini" "$targets" "$generated" "$log" "$prompt" 3; then
    return
  fi
  echo "generation failed with Spark and 5.4-mini: $targets" >&2
  return 1
}

jobs=()
for targets in "$OUT"/generation_batches/targets_*.jsonl; do
  generate_one "$targets" &
  jobs+=("$!")
  if [[ "${#jobs[@]}" -ge "$MAX_JOBS" ]]; then
    for pid in "${jobs[@]}"; do wait "$pid"; done
    jobs=()
  fi
done
for pid in ${jobs[*]-}; do wait "$pid"; done

python3 - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
targets = {
    row["query_id"]: row
    for row in map(json.loads, (out / "targets.jsonl").read_text().splitlines())
}
rows = [
    json.loads(line)
    for path in sorted((out / "generated").glob("targets_*.jsonl"))
    for line in path.open(encoding="utf-8")
    if line.strip()
]
if len(rows) != len(targets) or len({row["query_id"] for row in rows}) != len(targets):
    raise SystemExit("generated coverage mismatch")
if len({row["query"] for row in rows}) != len(rows):
    raise SystemExit("duplicate generated queries")
(out / "generated_queries.jsonl").write_text(
    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
    encoding="utf-8",
)
(out / "generation_report.json").write_text(
    json.dumps(
        {
            "targets": len(targets),
            "generated": len(rows),
            "models": dict(__import__("collections").Counter(row["generator_model"] for row in rows)),
        },
        ensure_ascii=False,
        indent=2,
    ) + "\n",
    encoding="utf-8",
)
PY

echo "Codex query generation complete (Spark preferred, 5.4-mini fallback)"
