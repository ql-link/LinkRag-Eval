#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${OUT:-$ROOT/runs/golden_v2/scale_100k_991004/scale_20k_overnight/ltr_query_expansion_2000}"
VALIDATION="$OUT/validation"
MAX_JOBS="${MAX_JOBS:-4}"
SKIP_SPARK="${SKIP_SPARK:-0}"
POOL_START="${POOL_START:-1}"
POOL_END="${POOL_END:-999999}"
mkdir -p "$VALIDATION/decisions" "$VALIDATION/logs"

validate_decisions() {
  local pool="$1" decisions="$2"
  python3 - "$pool" "$decisions" <<'PY'
import json
import sys
from pathlib import Path

pool_path, decisions_path = map(Path, sys.argv[1:])
pools = [json.loads(line) for line in pool_path.open(encoding="utf-8") if line.strip()]
rows = [json.loads(line) for line in decisions_path.open(encoding="utf-8") if line.strip()]
expected = {row["query_id"] for row in pools}
actual = [str(row.get("query_id") or "") for row in rows]
candidates = {
    row["query_id"]: {str(candidate["chunk_id"]) for candidate in row["candidates"]}
    for row in pools
}
required = {"query_id", "relevant_chunk_id", "evidence_span", "reason", "judge_model"}
if len(rows) != len(expected) or set(actual) != expected or len(set(actual)) != len(actual):
    raise SystemExit("decision IDs do not match pool")
if any(not required.issubset(row) for row in rows):
    raise SystemExit("missing decision fields")
for row in rows:
    selected = row["relevant_chunk_id"]
    if selected is not None and str(selected) not in candidates[row["query_id"]]:
        raise SystemExit(f"selected ID not in pool: {row['query_id']}")
    if row["judge_model"] not in {"gpt-5.3-codex-spark", "gpt-5.4-mini"}:
        raise SystemExit("judge model mismatch")
PY
}

run_judge_model() {
  local model="$1" pool="$2" decisions="$3" log="$4" prompt="$5" attempts="$6"
  local attempt model_prompt
  model_prompt="$prompt
Set judge_model exactly to $model."
  for attempt in $(seq 1 "$attempts"); do
    rm -f "$decisions"
    if (
      cd "$ROOT"
      codex --ask-for-approval never -c model_reasoning_effort=high exec --ephemeral \
        --model "$model" --sandbox workspace-write "$model_prompt"
    ) >"${log%.log}_${model}_attempt_${attempt}.log" 2>&1 && validate_decisions "$pool" "$decisions"; then
      return 0
    fi
  done
  return 1
}

judge_one() {
  local pool="$1"
  local stem decisions log prompt
  stem="$(basename "$pool" .jsonl)"
  decisions="$VALIDATION/decisions/${stem}.jsonl"
  log="$VALIDATION/logs/${stem}.log"
  prompt="This is a constrained data task. Read only ${pool#$ROOT/}; do not search the repository, inspect other files, or run project tests.
Independently validate every retrieval query by comparing all four candidate chunks.
Candidate order and chunk IDs contain no relevance signal.
For each query, relevant_chunk_id must be null or copied from one of that same row's four candidates; never transfer an ID between queries.
Select at most one canonical chunk only when it explicitly supports every decisive condition and requested outcome.
For similar_docs and hard-negative cases, reject candidates that share the topic but differ in threshold, time,
state transition, exception, object, or final outcome. Reject partial, adjacent, generic, contradictory, or inferred answers.
Use null relevant_chunk_id when no single candidate fully answers the query.
Write JSONL only to ${decisions#$ROOT/}, exactly one row per query, with:
query_id, relevant_chunk_id, evidence_span, reason, judge_model."
  if [[ -f "$decisions" ]] && validate_decisions "$pool" "$decisions"; then
    return
  fi
  if [[ "$SKIP_SPARK" != "1" ]]; then
    if run_judge_model "gpt-5.3-codex-spark" "$pool" "$decisions" "$log" "$prompt" 1; then
      return
    fi
  fi
  if run_judge_model "gpt-5.4-mini" "$pool" "$decisions" "$log" "$prompt" 3; then
    return
  fi
  echo "validation failed with Spark and 5.4-mini: $pool" >&2
  return 1
}

jobs=()
for pool in "$VALIDATION"/batches/pool_*.jsonl; do
  pool_index="$((10#$(basename "$pool" .jsonl | sed -E 's/pool_([0-9]+).*/\1/')))"
  if (( pool_index < POOL_START || pool_index > POOL_END )); then
    continue
  fi
  decisions="$VALIDATION/decisions/$(basename "$pool")"
  if [[ -f "$decisions" ]] && validate_decisions "$pool" "$decisions"; then
    continue
  fi
  judge_one "$pool" &
  jobs+=("$!")
  if [[ "${#jobs[@]}" -ge "$MAX_JOBS" ]]; then
    for pid in "${jobs[@]}"; do wait "$pid"; done
    jobs=()
  fi
done
for pid in ${jobs[*]-}; do wait "$pid"; done

echo "Codex blind validation complete (Spark preferred, 5.4-mini fallback)"
