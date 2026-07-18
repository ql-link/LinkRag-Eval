#!/usr/bin/env bash
set -euo pipefail

# Tune only on the scoped tune split, then evaluate the frozen candidate once
# on the scoped blind split. All storage remains in eval-only datasets.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCALE="$ROOT/runs/golden_v2/scale_100k_991004/scale_20k_overnight"
TUNE="$SCALE/realistic_tune_scope_992003.jsonl"
BLIND="$SCALE/realistic_blind_scope_992003.jsonl"
OUT="$SCALE/acceptance"
mkdir -p "$OUT/logs"

linkrag-eval tune-recall --golden "$TUNE" --dataset realistic_tune_scope20k \
  --out-dir "$OUT/tune" --corpus-chunks 20000 --final-top-k 10 --rrf-k 60 \
  --dense-top-ks 50,75,100,150 --sparse-top-ks 25,50,75,100 \
  --dense-thresholds 0,0.1,0.2,0.3 --sparse-thresholds 0,0.05,0.1,0.2 \
  --fusion-strategy weighted_score --dense-weight 0.9 --sparse-weight 0.1 \
  --concurrency 12 >"$OUT/logs/tune.log" 2>&1

TUNE_JSON="$(ls -t "$OUT"/tune/*.json | head -1)"
read -r DENSE_K SPARSE_K DENSE_THRESHOLD SPARSE_THRESHOLD <<EOF
$(python3 - "$TUNE_JSON" <<'PY'
import json, sys
best = json.load(open(sys.argv[1], encoding="utf-8"))["best"]
print(best["dense_top_k"], best["sparse_top_k"], best["dense_threshold"], best["sparse_threshold"])
PY
)
EOF

COMMON=(--golden "$BLIND" --top-k 10 --dataset realistic_blind_scope20k --precheck --require-chunk-references)
linkrag-eval run "${COMMON[@]}" --run-label scale20k-tuned-hybrid \
  --enabled-sources dense,sparse,bm25 --dense-top-k "$DENSE_K" --sparse-top-k "$SPARSE_K" \
  --dense-score-threshold "$DENSE_THRESHOLD" --sparse-score-threshold "$SPARSE_THRESHOLD" \
  --fusion-strategy weighted_score --dense-weight 0.9 --sparse-weight 0.1 --bm25-weight 0.0 \
  --out-dir "$OUT/eval_tuned_hybrid" >"$OUT/logs/tuned_hybrid.log" 2>&1

for route in dense sparse bm25; do
  linkrag-eval run "${COMMON[@]}" --run-label "scale20k-${route}" --enabled-sources "$route" \
    --out-dir "$OUT/eval_${route}" >"$OUT/logs/${route}.log" 2>&1 &
done
wait

pytest -q >"$OUT/logs/pytest.log" 2>&1
lint-imports >"$OUT/logs/import_lint.log" 2>&1
printf '%s scale20k acceptance pipeline complete\n' "$(date '+%F %T')" >"$OUT/complete.log"
