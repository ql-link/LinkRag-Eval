#!/usr/bin/env bash
set -euo pipefail

# Final, fixed-parameter evaluation of the expanded realistic blind set.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$ROOT/runs/golden_v2/scale_100k_991004/scale_100k_991004_batch_0001_ds992000"
REAL="$BASE/realistic_additional_300/overnight_final"
GOLDEN="$REAL/golden_expanded_top50/realistic_blind.jsonl"
OUT="$REAL/final_expanded_116"
mkdir -p "$OUT/logs"

run_route() {
  local route="$1"
  local label="${route//,/+}"
  linkrag-eval run \
    --golden "$GOLDEN" \
    --run-label "final-expanded-${label}-top10" \
    --top-k 10 \
    --enabled-sources "$route" \
    --out-dir "$OUT/eval_${label}" \
    --dataset realistic_blind_expanded \
    --precheck \
    --require-chunk-references \
    >"$OUT/logs/${label}.log" 2>&1
}

for route in dense sparse bm25 dense,sparse,bm25; do
  run_route "$route" &
done
wait

printf '%s final expanded realistic evaluation complete\n' "$(date '+%F %T')" \
  | tee "$OUT/logs/complete.log"
