#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$ROOT/runs/golden_v2/scale_100k_991004/scale_20k_overnight/balanced_query_expansion"
MAX_JOBS="${MAX_JOBS:-4}"
BATCH_SIZE="${BATCH_SIZE:-2}"
IFS=',' read -r -a SETS <<< "${SETS_CSV:-exact_identifier,short_keyword,dense_paraphrase,long_sparse}"
CHUNKS=(
  "$ROOT/runs/golden_v2/scale_100k_991004/scale_100k_991004_batch_0001_ds992000/synth_background/chunk_records.jsonl"
  "$ROOT/runs/golden_v2/scale_100k_991004/scale_100k_991004_batch_0002_ds992001/synth_background/chunk_records.jsonl"
  "$ROOT/runs/golden_v2/scale_100k_991004/scale_100k_991004_batch_0003_ds992002/synth_background/chunk_records.jsonl"
  "$ROOT/runs/golden_v2/scale_100k_991004/scale_100k_991004_batch_0004_ds992003/synth_background/chunk_records.jsonl"
)

set_dir() {
  case "$1" in
    exact_identifier) echo "$BASE/grounded_exact_replacement" ;;
    exact_extension) echo "$BASE/grounded_exact_extension" ;;
    *) echo "$BASE/grounded_supplements/$1" ;;
  esac
}

seed_path() {
  case "$1" in
    exact_identifier) echo "$(set_dir "$1")/grounded_exact_seeds_180.jsonl" ;;
    exact_extension) echo "$(set_dir "$1")/seeds.jsonl" ;;
    *) echo "$(set_dir "$1")/seeds.jsonl" ;;
  esac
}

validate_decisions() {
  local pool="$1" decisions="$2"
  python3 - "$pool" "$decisions" <<'PY'
import json
import sys
from pathlib import Path

pool_path, decision_path = map(Path, sys.argv[1:])
pools = [json.loads(line) for line in pool_path.open(encoding="utf-8") if line.strip()]
rows = [json.loads(line) for line in decision_path.open(encoding="utf-8") if line.strip()]
expected = {row["query_id"] for row in pools}
candidates = {
    row["query_id"]: {str(candidate["chunk_id"]) for candidate in row["candidates"]}
    for row in pools
}
actual = [str(row.get("query_id") or "") for row in rows]
required = {"query_id", "relevant_chunk_id", "evidence_span", "reason", "judge_model"}
if len(rows) != len(expected) or set(actual) != expected or len(set(actual)) != len(actual):
    raise SystemExit("decision query IDs do not match pool")
if any(not required.issubset(row) for row in rows):
    raise SystemExit("missing decision fields")
for row in rows:
    selected = row.get("relevant_chunk_id")
    if selected is not None and str(selected) not in candidates[row["query_id"]]:
        raise SystemExit(f"invalid candidate ID: {row['query_id']} {selected}")
PY
}

prepare_set() {
  local name="$1" dir seeds validation chunk_args=()
  dir="$(set_dir "$name")"
  seeds="$(seed_path "$name")"
  validation="$dir/validation"
  mkdir -p "$validation/batches" "$validation/logs"
  for chunk in "${CHUNKS[@]}"; do chunk_args+=(--chunks "$chunk"); done
  python3 "$ROOT/scripts/inject_grounded_validation_targets.py" \
    --seeds "$seeds" \
    --candidate-pool "$dir/candidate_pool_top24.jsonl" \
    "${chunk_args[@]}" \
    --out "$validation/blinded_candidate_pool.jsonl" \
    --report-out "$validation/injection_report.json" \
    --route-candidates 23 \
    --random-candidates 2
  python3 - "$validation/blinded_candidate_pool.jsonl" "$validation/batches" "$BATCH_SIZE" <<'PY'
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
out_dir = Path(sys.argv[2])
batch_size = int(sys.argv[3])
for old in out_dir.glob("pool_*.jsonl"):
    old.unlink()
rows = [json.loads(line) for line in source.open(encoding="utf-8") if line.strip()]
for index, offset in enumerate(range(0, len(rows), batch_size), start=1):
    path = out_dir / f"pool_{index:03d}.jsonl"
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows[offset:offset + batch_size]),
        encoding="utf-8",
    )
PY
}

label_one() {
  local name="$1" pool="$2" stem decisions validation prompt
  validation="$(set_dir "$name")/validation"
  stem="$(basename "$pool" .jsonl)"
  decisions="$validation/batches/decisions_${stem#pool_}.jsonl"
  prompt="Read ${pool#$ROOT/}. For each query, compare all candidate chunks and select at most one canonical evidence chunk. Select only when one chunk explicitly supports every decisive condition and requested outcome. Reject topical, partial, adjacent, contradictory, generic, or unsupported candidates. Candidate order and IDs carry no relevance signal. Write exactly one JSONL row per query only to ${decisions#$ROOT/}, with query_id, relevant_chunk_id, evidence_span, reason, judge_model. Copy IDs exactly. Use null relevant_chunk_id when no candidate fully answers the query."
  if [[ -f "$decisions" ]] && validate_decisions "$pool" "$decisions"; then
    return
  fi
  rm -f "$decisions"
  if ! (
    cd "$ROOT"
    codex --ask-for-approval never -c model_reasoning_effort=high exec --ephemeral \
      --model gpt-5.3-codex-spark --sandbox workspace-write "$prompt"
  ) >"$validation/logs/${stem}_spark.log" 2>&1 || ! validate_decisions "$pool" "$decisions"; then
    rm -f "$decisions"
    (
      cd "$ROOT"
      codex --ask-for-approval never -c model_reasoning_effort=high exec --ephemeral \
        --model gpt-5.4-mini --sandbox workspace-write "$prompt"
    ) >"$validation/logs/${stem}_mini.log" 2>&1
    validate_decisions "$pool" "$decisions"
  fi
}

for name in "${SETS[@]}"; do prepare_set "$name"; done

jobs=()
for name in "${SETS[@]}"; do
  for pool in "$(set_dir "$name")/validation/batches"/pool_*.jsonl; do
    label_one "$name" "$pool" &
    jobs+=("$!")
    if [[ "${#jobs[@]}" -ge "$MAX_JOBS" ]]; then
      for pid in "${jobs[@]}"; do wait "$pid"; done
      jobs=()
    fi
  done
done
for pid in ${jobs[*]-}; do wait "$pid"; done

for name in "${SETS[@]}"; do
  dir="$(set_dir "$name")"
  python3 "$ROOT/scripts/finalize_grounded_validation.py" \
    --seeds "$(seed_path "$name")" \
    --pool "$dir/validation/blinded_candidate_pool.jsonl" \
    --decisions-dir "$dir/validation/batches" \
    --spark-log-dir "$dir/validation/logs" \
    --out-dir "$dir/validation"
done

python3 "$ROOT/scripts/build_report_index.py"
echo "grounded validation complete"
