#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$ROOT/runs/golden_v2/scale_100k_991004/scale_100k_991004_batch_0001_ds992000"
GOLDEN="$BASE/realistic_additional_300/overnight_final/golden_expanded_top50/realistic_tune.jsonl"
OUT="$BASE/realistic_additional_300/overnight_final/tune_expanded_272"
mkdir -p "$OUT"

# This command only reads the tune split and caches route hits once before the
# local grid search. Blind data is intentionally not referenced.
linkrag-eval tune-recall --golden "$GOLDEN" --dataset realistic_tune_expanded_weighted \
  --out-dir "$OUT" --corpus-chunks 5000 --final-top-k 10 --rrf-k 60 \
  --dense-top-ks 25,50,75,100 --sparse-top-ks 25,50,75,100 \
  --dense-thresholds 0,0.1,0.2,0.3 --sparse-thresholds 0,0.05,0.1,0.2 \
  --fusion-strategy weighted_score --dense-weight 0.9 --sparse-weight 0.1 \
  --concurrency 12
