#!/usr/bin/env bash
set -euo pipefail

# Unattended Spark canonical-labeling and blind-evaluation runner.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$ROOT/runs/golden_v2/scale_100k_991004/scale_100k_991004_batch_0001_ds992000"
ADDITIONAL="$BASE/realistic_additional_300"
BATCH_DIR="$ADDITIONAL/spark_label_batches"
OUT_DIR="$ADDITIONAL/overnight_final"
LOG_DIR="$OUT_DIR/logs"
mkdir -p "$LOG_DIR"

log() {
  printf '%s %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG_DIR/overnight.log"
}

validate_raw_batch() {
  local batch="$1"
  python3 - "$BATCH_DIR/judgments_spark_canonical_${batch}.jsonl" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
rows = [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]
required = {
    "query_id", "query", "role", "source", "type_hint", "hard_reason", "chunk_id",
    "relevant", "grade", "evidence_span", "reason", "judge_failed", "judge_model",
}
if len(rows) != 300:
    raise SystemExit(f"expected 300 judgments, got {len(rows)}")
if any(not required.issubset(row) for row in rows):
    raise SystemExit("missing required raw judgment fields")
if len({(row["query_id"], row["chunk_id"]) for row in rows}) != 300:
    raise SystemExit("duplicate query/chunk pair")
if any(row["role"] != "realistic" or row["hard_reason"] is not None for row in rows):
    raise SystemExit("non-realistic row in canonical realistic batch")
if any(row["judge_model"] != "gpt-5.3-codex-spark-canonical" for row in rows):
    raise SystemExit("unexpected judge model")
PY
}

normalize_batch() {
  local batch="$1"
  python3 - "$BATCH_DIR/candidate_pool_${batch}.jsonl" \
    "$BATCH_DIR/judgments_spark_canonical_${batch}.jsonl" \
    "$BATCH_DIR/judgments_spark_canonical_${batch}_normalized.jsonl" <<'PY'
import json
import sys
from pathlib import Path

pool_path, raw_path, out_path = map(Path, sys.argv[1:])
candidates = {}
for line in pool_path.open(encoding="utf-8"):
    query = json.loads(line)
    for candidate in query["candidates"]:
        candidates[(query["query_id"], candidate["chunk_id"])] = candidate

rows = []
for line in raw_path.open(encoding="utf-8"):
    row = json.loads(line)
    candidate = candidates[(row["query_id"], row.pop("chunk_id"))]
    row["candidate"] = {
        key: candidate[key]
        for key in ("chunk_id", "doc_id", "dataset_id", "sources", "rank_by_source")
    }
    rows.append(row)
out_path.write_text(
    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
    encoding="utf-8",
)
PY
}

label_batch() {
  local batch="$1"
  local raw="$BATCH_DIR/judgments_spark_canonical_${batch}.jsonl"
  local prompt="Read runs/golden_v2/scale_100k_991004/scale_100k_991004_batch_0001_ds992000/realistic_additional_300/spark_label_batches/candidate_pool_${batch}.jsonl. Build canonical chunk qrels at runs/golden_v2/scale_100k_991004/scale_100k_991004_batch_0001_ds992000/realistic_additional_300/spark_label_batches/judgments_spark_canonical_${batch}.jsonl. Compare all 12 candidates for each query. Select at most one canonical evidence chunk, or zero. It must explicitly state both the decisive condition and outcome. All partial, topical, adjacent, generic, and duplicate chunks are false. Output exactly 300 JSONL records with query_id, query, role realistic, source, type_hint, hard_reason null, chunk_id, relevant, grade, evidence_span, reason, judge_failed false, judge_model gpt-5.3-codex-spark-canonical."

  for attempt in 1 2 3; do
    rm -f "$raw"
    log "batch ${batch}: Spark attempt ${attempt}/3"
    if (
      cd "$ROOT"
      codex --ask-for-approval never -c model_reasoning_effort=high exec --ephemeral \
        --model gpt-5.3-codex-spark --sandbox workspace-write "$prompt"
    ) >>"$LOG_DIR/spark_${batch}_attempt_${attempt}.log" 2>&1 && validate_raw_batch "$batch"; then
      normalize_batch "$batch"
      log "batch ${batch}: complete"
      return 0
    fi
    log "batch ${batch}: failed validation or request"
    sleep 90
  done
  log "batch ${batch}: exhausted retries"
  return 1
}

for batch in 01 02 03 04 05 06 07; do
  if [[ ! -f "$BATCH_DIR/judgments_spark_canonical_${batch}_normalized.jsonl" ]]; then
    validate_raw_batch "$batch"
    normalize_batch "$batch"
  fi
done

for batch in 08 09 10 11 12; do
  label_batch "$batch"
done

python3 - "$BASE/realistic_120/judgments_final_top50.jsonl" "$BATCH_DIR" "$OUT_DIR/judgments_realistic_merged.jsonl" <<'PY'
import json
import sys
from pathlib import Path

old_path, batch_dir, out_path = map(Path, sys.argv[1:])
rows = [json.loads(line) for line in old_path.open(encoding="utf-8") if line.strip()]
for index in range(1, 13):
    path = batch_dir / f"judgments_spark_canonical_{index:02d}_normalized.jsonl"
    rows.extend(json.loads(line) for line in path.open(encoding="utf-8") if line.strip())
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(
    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
    encoding="utf-8",
)
PY

linkrag-eval golden-v2 qc \
  --judgments "$OUT_DIR/judgments_realistic_merged.jsonl" \
  --report-out "$OUT_DIR/qc_realistic_merged.json" \
  --markdown-out "$OUT_DIR/qc_realistic_merged.md" \
  --max-unresolved-rate 0.30 --max-random-relevant-rate 0.05 --min-queries 400

linkrag-eval golden-v2 build \
  --judgments "$OUT_DIR/judgments_realistic_merged.jsonl" \
  --out-dir "$OUT_DIR/golden" --user-id 990001 --tune-ratio 0.70

BLIND="$OUT_DIR/golden/realistic_blind.jsonl"
for route in dense sparse bm25 dense,sparse,bm25; do
  label="${route//,/+}"
  linkrag-eval run --golden "$BLIND" --run-label "overnight-${label}" --top-k 10 \
    --enabled-sources "$route" --out-dir "$OUT_DIR/eval_${label}" --dataset realistic_blind \
    --precheck --require-chunk-references
done

log "overnight realistic pipeline complete"
