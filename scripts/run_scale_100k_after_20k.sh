#!/usr/bin/env bash
set -euo pipefail

# Continue only after the 20k gate script has completed. Corpus generation uses
# the existing Spark-produced spec; ingest, BM25 and vector writes remain eval-only.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCALE="$ROOT/runs/golden_v2/scale_100k_991004"
SOURCE="$SCALE/scale_100k_991004_batch_0001_ds992000"
SPEC="$SOURCE/spark_corpus_spec.json"
REAL="$SOURCE/realistic_additional_300/overnight_final/golden_expanded_top50/realistic_blind.jsonl"
GATE_LOG="$SCALE/scale_20k_overnight/scale.log"
OUT="$SCALE/scale_100k_overnight"
mkdir -p "$OUT/logs"
LOG="$OUT/scale.log"

log() { printf '%s %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG"; }

while ! rg -q 'scale 20k pipeline complete' "$GATE_LOG" 2>/dev/null; do
  log 'waiting for scale20k gate'
  sleep 120
done

write_scoped_blind() {
  local last_dataset_id="$1"
  local scoped="$OUT/realistic_blind_scope_${last_dataset_id}.jsonl"
  python3 - "$REAL" "$scoped" "$last_dataset_id" <<'PY'
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
last = int(sys.argv[3])
dataset_ids = list(range(992000, last + 1))
rows = []
for line in source.open(encoding="utf-8"):
    if line.strip():
        row = json.loads(line)
        row["dataset_ids"] = dataset_ids
        rows.append(json.dumps(row, ensure_ascii=False))
target.write_text("\n".join(rows) + "\n", encoding="utf-8")
PY
  printf '%s' "$scoped"
}

scoped_20k="$(write_scoped_blind 992003)"
log '20k scoped blind hybrid check'
linkrag-eval run --golden "$scoped_20k" --run-label 'scale20k-scoped-final' --top-k 10 \
  --enabled-sources dense,sparse,bm25 --out-dir "$OUT/eval_after_992003" \
  --dataset realistic_blind_scale20k --precheck --require-chunk-references \
  >"$OUT/logs/eval_992003.log" 2>&1

prepare_batch() {
  local index="$1"
  local dataset_id=$((991999 + index))
  local batch_dir="$SCALE/scale_100k_991004_batch_$(printf '%04d' "$index")_ds${dataset_id}"
  mkdir -p "$batch_dir"
  linkrag-eval golden-v2 synth-corpus --spec "$SPEC" --dataset-id "$dataset_id" \
    --target-chunks 5000 --out-dir "$batch_dir/synth_background" --seed "$((1300 + index))" \
    --batch-id "scale_100k_batch_${index}" --report-out "$batch_dir/synth_background/synth_report.json"
  linkrag-eval golden-v2 spark-corpus-export \
    --chunks "$batch_dir/synth_background/chunk_records.jsonl" \
    --collection "$batch_dir/corpus/collection.tsv" --manifest "$batch_dir/corpus/manifest.jsonl" \
    --dataset-id "$dataset_id" --report-out "$batch_dir/corpus/export_report.json"
}

ingest_batch() {
  local index="$1"
  local dataset_id=$((991999 + index))
  local batch_dir="$SCALE/scale_100k_991004_batch_$(printf '%04d' "$index")_ds${dataset_id}"
  log "batch=${index} dataset=${dataset_id}: ingest eval-only corpus"
  linkrag-eval ingest --dataset-id "$dataset_id" --collection "$batch_dir/corpus/collection.tsv" \
    --manifest "$batch_dir/corpus/manifest.jsonl" --name "golden_v2_scale_${dataset_id}" \
    --source-type synth --batch 50 >"$OUT/logs/ingest_${dataset_id}.log" 2>&1
}

for start in 5 9 13 17; do
  indexes=()
  for index in $(seq "$start" "$((start + 3))"); do
    indexes+=("$index")
    log "batch=${index}: synthesize and export"
    prepare_batch "$index"
  done
  for index in "${indexes[@]}"; do
    ingest_batch "$index" &
  done
  wait
  for index in "${indexes[@]}"; do
    dataset_id=$((991999 + index))
    log "batch=${index} dataset=${dataset_id}: SQLite FTS5 BM25 backfill"
    linkrag-eval bm25-backfill --dataset-ids "$dataset_id" --batch 1000 \
      >"$OUT/logs/bm25_${dataset_id}.log" 2>&1
    log "batch=${index} dataset=${dataset_id}: alternate embedding backfill"
    linkrag-eval golden-v2 alt-embed-backfill --dataset-ids "$dataset_id" --batch 100 \
      >"$OUT/logs/alt_${dataset_id}.log" 2>&1
  done
  last_dataset_id=$((991999 + start + 3))
  scoped_blind="$(write_scoped_blind "$last_dataset_id")"
  log "scope through dataset=${last_dataset_id}: fixed blind hybrid check"
  linkrag-eval run --golden "$scoped_blind" --run-label "scale100k-after-${last_dataset_id}" \
    --top-k 10 --enabled-sources dense,sparse,bm25 \
    --out-dir "$OUT/eval_after_${last_dataset_id}" --dataset realistic_blind_scale100k \
    --precheck --require-chunk-references >"$OUT/logs/eval_${last_dataset_id}.log" 2>&1
done

log 'scale 100k pipeline complete'
pytest -q >"$OUT/logs/pytest.log" 2>&1
lint-imports >"$OUT/logs/import_lint.log" 2>&1
log 'final verification complete'
