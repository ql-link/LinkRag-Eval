#!/usr/bin/env bash
set -euo pipefail

# Build three additional eval-only distractor batches, taking the corpus from
# 5k to 20k chunks. Every write targets only eval datasets and eval collections.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCALE="$ROOT/runs/golden_v2/scale_100k_991004"
SOURCE="$SCALE/scale_100k_991004_batch_0001_ds992000"
SPEC="$SOURCE/spark_corpus_spec.json"
REAL="$SOURCE/realistic_additional_300/overnight_final/golden_expanded_top50/realistic_blind.jsonl"
OUT="$SCALE/scale_20k_overnight"
mkdir -p "$OUT"
LOG="$OUT/scale.log"

log() { printf '%s %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG"; }

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
    if not line.strip():
        continue
    row = json.loads(line)
    row["dataset_ids"] = dataset_ids
    rows.append(json.dumps(row, ensure_ascii=False))
target.write_text("\n".join(rows) + "\n", encoding="utf-8")
print(target)
PY
}

for index in 2 3 4; do
  dataset_id=$((991999 + index))
  batch_dir="$SCALE/scale_100k_991004_batch_$(printf '%04d' "$index")_ds${dataset_id}"
  mkdir -p "$batch_dir"
  log "batch=${index} dataset=${dataset_id}: synthesize"
  linkrag-eval golden-v2 synth-corpus \
    --spec "$SPEC" --dataset-id "$dataset_id" --target-chunks 5000 \
    --out-dir "$batch_dir/synth_background" --seed "$((1300 + index))" \
    --batch-id "scale_20k_batch_${index}" \
    --report-out "$batch_dir/synth_background/synth_report.json"
  log "batch=${index} dataset=${dataset_id}: export"
  linkrag-eval golden-v2 spark-corpus-export \
    --chunks "$batch_dir/synth_background/chunk_records.jsonl" \
    --collection "$batch_dir/corpus/collection.tsv" \
    --manifest "$batch_dir/corpus/manifest.jsonl" \
    --dataset-id "$dataset_id" --report-out "$batch_dir/corpus/export_report.json"
  log "batch=${index} dataset=${dataset_id}: ingest eval-only corpus"
  linkrag-eval ingest --dataset-id "$dataset_id" \
    --collection "$batch_dir/corpus/collection.tsv" --manifest "$batch_dir/corpus/manifest.jsonl" \
    --name "golden_v2_scale_${dataset_id}" --source-type synth --batch 50
  log "batch=${index} dataset=${dataset_id}: backfill SQLite FTS5 BM25"
  linkrag-eval bm25-backfill --dataset-ids "$dataset_id" --batch 1000
  log "batch=${index} dataset=${dataset_id}: backfill alternate embedding"
  linkrag-eval golden-v2 alt-embed-backfill --dataset-ids "$dataset_id" --batch 100
  log "batch=${index} dataset=${dataset_id}: fixed blind hybrid check"
  scoped_blind="$(write_scoped_blind "$dataset_id")"
  linkrag-eval run --golden "$scoped_blind" --run-label "scale20k-after-${dataset_id}" --top-k 10 \
    --enabled-sources dense,sparse,bm25 --out-dir "$OUT/eval_after_${dataset_id}" \
    --dataset realistic_blind_scale20k --precheck --require-chunk-references
done

log "scale 20k pipeline complete"
