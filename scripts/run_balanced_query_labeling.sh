#!/usr/bin/env bash
set -euo pipefail

# Canonical chunk labeling for the balanced query expansion.
# Spark is the primary judge; gpt-5.4-mini is used only when Spark fails.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/runs/golden_v2/scale_100k_991004/scale_20k_overnight/balanced_query_expansion"
LABEL_VARIANT="${LABEL_VARIANT:-canonical_top12}"
LABEL_ROOT="$OUT/$LABEL_VARIANT"
LOG_ROOT="$OUT/logs/$LABEL_VARIANT"
MAX_JOBS="${MAX_JOBS:-4}"
BATCH_SIZE="${BATCH_SIZE:-10}"
IFS=',' read -r -a SCENARIOS <<< "${SCENARIOS_CSV:-short_keyword,exact_identifier,long_sparse,dense_paraphrase}"

mkdir -p "$LABEL_ROOT" "$LOG_ROOT"

prepare_batches() {
  local scenario="$1"
  python3 - "$OUT/${scenario}_candidate_pool_top24.jsonl" "$LABEL_ROOT/$scenario" "$BATCH_SIZE" <<'PY'
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
batch_size = int(sys.argv[3])
target.mkdir(parents=True, exist_ok=True)
for old in target.glob("pool_*.jsonl"):
    old.unlink()

rows = [json.loads(line) for line in source.open(encoding="utf-8") if line.strip()]
for batch_index, offset in enumerate(range(0, len(rows), batch_size), start=1):
    batch = []
    for row in rows[offset : offset + batch_size]:
        route = [
            candidate
            for candidate in row["candidates"]
            if set(candidate.get("sources") or []) != {"random_neighbor"}
        ][:12]
        random_only = [
            candidate
            for candidate in row["candidates"]
            if set(candidate.get("sources") or []) == {"random_neighbor"}
        ][:2]
        selected = route + random_only
        if len(route) < 12 or len(random_only) < 2:
            raise SystemExit(
                f"{row['query_id']}: route={len(route)} random_only={len(random_only)}"
            )
        batch.append({**row, "candidates": selected})
    path = target / f"pool_{batch_index:02d}.jsonl"
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in batch),
        encoding="utf-8",
    )
print(f"prepared scenario={target.name} queries={len(rows)} batches={batch_index}")
PY
}

validate_raw() {
  local pool="$1" raw="$2"
  python3 - "$pool" "$raw" <<'PY'
import json
import sys
from collections import Counter
from pathlib import Path

pool_path, raw_path = map(Path, sys.argv[1:])
pools = [json.loads(line) for line in pool_path.open(encoding="utf-8") if line.strip()]
rows = [json.loads(line) for line in raw_path.open(encoding="utf-8") if line.strip()]
required = {
    "query_id", "query", "role", "source", "type_hint", "hard_reason",
    "chunk_id", "relevant", "grade", "evidence_span", "reason",
    "judge_failed", "judge_model",
}
expected_pairs = {
    (pool["query_id"], candidate["chunk_id"])
    for pool in pools
    for candidate in pool["candidates"]
}
actual_pairs = [(row.get("query_id"), row.get("chunk_id")) for row in rows]
if len(rows) != len(expected_pairs):
    raise SystemExit(f"expected {len(expected_pairs)} rows, got {len(rows)}")
if any(not required.issubset(row) for row in rows):
    raise SystemExit("missing judgment fields")
if len(set(actual_pairs)) != len(actual_pairs) or set(actual_pairs) != expected_pairs:
    raise SystemExit("judgment query/chunk pairs do not match candidate pool")
positive_counts = Counter(row["query_id"] for row in rows if row.get("relevant"))
if any(count > 1 for count in positive_counts.values()):
    raise SystemExit("more than one canonical positive for a query")
if any(row.get("judge_failed") for row in rows):
    raise SystemExit("judge_failed must be false")
if any((not row.get("relevant")) and int(row.get("grade", 0) or 0) != 0 for row in rows):
    raise SystemExit("non-relevant judgment must use grade 0")
PY
}

normalize() {
  local pool="$1" raw="$2" normalized="$3"
  python3 - "$pool" "$raw" "$normalized" <<'PY'
import json
import sys
from pathlib import Path

pool_path, raw_path, out_path = map(Path, sys.argv[1:])
candidates = {}
for line in pool_path.open(encoding="utf-8"):
    pool = json.loads(line)
    for candidate in pool["candidates"]:
        candidates[(pool["query_id"], candidate["chunk_id"])] = candidate
rows = []
for line in raw_path.open(encoding="utf-8"):
    if not line.strip():
        continue
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

label_one() {
  local scenario="$1" pool="$2"
  local stem raw normalized prompt
  stem="$(basename "$pool" .jsonl)"
  raw="${pool%/*}/judgments_${stem#pool_}.jsonl"
  normalized="${raw%.jsonl}_normalized.jsonl"
  prompt="Read ${pool#$ROOT/}. For every query, compare all 14 candidate chunks as one group. Mark at most one canonical evidence chunk relevant. A positive chunk must explicitly support every decisive condition and the requested outcome; exact numbers, dates, versions, identifiers, exceptions and state constraints in the query must be supported when they affect the answer. Topical, partial, adjacent, contradictory, generic, duplicated and random-only chunks are false. Output one judgment for every query/candidate pair, preserving query and chunk IDs. Write JSONL only to ${raw#$ROOT/}. Required fields: query_id, query, role, source, type_hint, hard_reason, chunk_id, relevant, grade, evidence_span, reason, judge_failed false, judge_model. Use grade 3 only for the single canonical positive and grade 0 for false. If no candidate fully supports the query, all 14 must be false."
  if [[ -f "$raw" ]] && validate_raw "$pool" "$raw"; then
    normalize "$pool" "$raw" "$normalized"
    return
  fi
  rm -f "$raw" "$normalized"
  if ! (
    cd "$ROOT"
    codex --ask-for-approval never -c model_reasoning_effort=high exec --ephemeral \
      --model gpt-5.3-codex-spark --sandbox workspace-write "$prompt"
  ) >"$LOG_ROOT/${scenario}_${stem}_spark.log" 2>&1 || ! validate_raw "$pool" "$raw"; then
    rm -f "$raw"
    (
      cd "$ROOT"
      codex --ask-for-approval never -c model_reasoning_effort=high exec --ephemeral \
        --model gpt-5.4-mini --sandbox workspace-write "$prompt"
    ) >"$LOG_ROOT/${scenario}_${stem}_mini.log" 2>&1
    validate_raw "$pool" "$raw"
  fi
  normalize "$pool" "$raw" "$normalized"
}

for scenario in "${SCENARIOS[@]}"; do
  prepare_batches "$scenario"
done

jobs=()
for scenario in "${SCENARIOS[@]}"; do
  for pool in "$LABEL_ROOT/$scenario"/pool_*.jsonl; do
    label_one "$scenario" "$pool" &
    jobs+=("$!")
    if [[ "${#jobs[@]}" -ge "$MAX_JOBS" ]]; then
      for pid in "${jobs[@]}"; do wait "$pid"; done
      jobs=()
    fi
  done
done
for pid in "${jobs[@]}"; do wait "$pid"; done

python3 - "$LABEL_ROOT" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
for scenario_dir in sorted(path for path in root.iterdir() if path.is_dir()):
    rows = [
        json.loads(line)
        for path in sorted(scenario_dir.glob("judgments_*_normalized.jsonl"))
        for line in path.open(encoding="utf-8")
        if line.strip()
    ]
    out = scenario_dir / "judgments_merged.jsonl"
    out.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(f"merged scenario={scenario_dir.name} judgments={len(rows)}")
PY

for scenario in "${SCENARIOS[@]}"; do
  linkrag-eval golden-v2 qc \
    --judgments "$LABEL_ROOT/$scenario/judgments_merged.jsonl" \
    --report-out "$LABEL_ROOT/$scenario/qc.json" \
    --markdown-out "$LABEL_ROOT/$scenario/qc.md" \
    --max-unresolved-rate 1.0 \
    --max-random-relevant-rate 0.05 \
    --min-queries 150
done

python3 "$ROOT/scripts/build_report_index.py"

echo "balanced canonical labeling complete"
