#!/usr/bin/env bash
set -euo pipefail

# Unattended Hard Set pipeline. Uses Spark first and gpt-5.4-mini only when Spark fails.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$ROOT/runs/golden_v2/scale_100k_991004/scale_100k_991004_batch_0001_ds992000"
HARD="$BASE/hard_80"
OUT="$HARD/overnight_final"
LOG="$OUT/logs"
mkdir -p "$LOG"

log() { printf '%s %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG/overnight.log"; }

make_stage() {
  local name="$1" start="$2" end="$3" prior_dirs="$4"
  python3 - "$HARD/candidate_pool.jsonl" "$OUT" "$name" "$start" "$end" "$prior_dirs" <<'PY'
import json, sys
from pathlib import Path

source, out_root, name, start, end, prior_dirs = sys.argv[1:]
source, out_root = Path(source), Path(out_root)
start, end = int(start), int(end)
rows = [json.loads(line) for line in source.open(encoding="utf-8") if line.strip()]
if prior_dirs:
    resolved = set()
    all_ids = set()
    for directory in prior_dirs.split(","):
        for path in sorted((out_root / directory).glob("judgments_*.jsonl")):
            if path.name.endswith("_normalized.jsonl"):
                continue
            for line in path.open(encoding="utf-8"):
                row = json.loads(line)
                all_ids.add(row["query_id"])
                if row.get("relevant"):
                    resolved.add(row["query_id"])
    rows = [row for row in rows if row["query_id"] in all_ids - resolved]
stage = out_root / name
stage.mkdir(parents=True, exist_ok=True)
for old in stage.glob("pool_*.jsonl"):
    old.unlink()
for index, offset in enumerate(range(0, len(rows), 10), start=1):
    batch = []
    for row in rows[offset:offset + 10]:
        batch.append({**row, "candidates": row["candidates"][start:end]})
    (stage / f"pool_{index:02d}.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in batch), encoding="utf-8"
    )
print(f"stage={name} queries={len(rows)} batches={index if rows else 0}")
PY
}

validate_raw() {
  local path="$1" expected="$2"
  python3 - "$path" "$expected" <<'PY'
import json, sys
from pathlib import Path
path, expected = Path(sys.argv[1]), int(sys.argv[2])
rows = [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]
required = {"query_id", "query", "role", "source", "type_hint", "hard_reason", "chunk_id", "relevant", "grade", "evidence_span", "reason", "judge_failed", "judge_model"}
if len(rows) != expected:
    raise SystemExit(f"expected {expected}, got {len(rows)}")
if any(not required.issubset(row) for row in rows):
    raise SystemExit("missing judgment fields")
if len({(row["query_id"], row["chunk_id"]) for row in rows}) != expected:
    raise SystemExit("duplicate query/chunk")
if any(row["role"] != "hard" for row in rows):
    raise SystemExit("non-hard row")
PY
}

normalize() {
  local pool="$1" raw="$2" normalized="$3"
  python3 - "$pool" "$raw" "$normalized" <<'PY'
import json, sys
from pathlib import Path
pool_path, raw_path, out_path = map(Path, sys.argv[1:])
candidates = {}
for line in pool_path.open(encoding="utf-8"):
    pool = json.loads(line)
    for candidate in pool["candidates"]:
        candidates[(pool["query_id"], candidate["chunk_id"])] = candidate
rows = []
for line in raw_path.open(encoding="utf-8"):
    row = json.loads(line)
    candidate = candidates[(row["query_id"], row.pop("chunk_id"))]
    row["candidate"] = {key: candidate[key] for key in ("chunk_id", "doc_id", "dataset_id", "sources", "rank_by_source")}
    rows.append(row)
out_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
PY
}

label_stage() {
  local stage="$1"
  local dir="$OUT/$stage"
  for pool in "$dir"/pool_*.jsonl; do
    [[ -e "$pool" ]] || continue
    local stem raw normalized expected prompt
    stem="$(basename "$pool" .jsonl | cut -d_ -f2)"
    raw="$dir/judgments_${stem}.jsonl"
    normalized="$dir/judgments_${stem}_normalized.jsonl"
    expected="$(python3 - "$pool" <<'PY'
import json, sys
print(sum(len(json.loads(line)["candidates"]) for line in open(sys.argv[1], encoding="utf-8") if line.strip()))
PY
)"
    prompt="Read ${pool#$ROOT/}. These are candidate chunks for hard retrieval queries. Compare all candidates for each query and select at most one canonical evidence chunk, or zero. A selected chunk must explicitly state the decisive query condition and outcome; partial, topical, adjacent, generic and duplicate content is false. Write exactly ${expected} JSONL records to ${raw#$ROOT/}. Fields query_id, query, role hard, source, type_hint, hard_reason, chunk_id, relevant, grade, evidence_span, reason, judge_failed false, judge_model."
    rm -f "$raw"
    log "$stage/$stem: Spark"
    if ! (cd "$ROOT" && codex --ask-for-approval never -c model_reasoning_effort=high exec --ephemeral --model gpt-5.3-codex-spark --sandbox workspace-write "$prompt") >"$LOG/${stage}_${stem}_spark.log" 2>&1 || ! validate_raw "$raw" "$expected"; then
      rm -f "$raw"
      log "$stage/$stem: fallback gpt-5.4-mini"
      (cd "$ROOT" && codex --ask-for-approval never -c model_reasoning_effort=high exec --ephemeral --model gpt-5.4-mini --sandbox workspace-write "$prompt") >"$LOG/${stage}_${stem}_mini.log" 2>&1
      validate_raw "$raw" "$expected"
    fi
    normalize "$pool" "$raw" "$normalized"
  done
}

make_stage top12 0 12 ""
label_stage top12
make_stage top24 12 24 "top12"
label_stage top24
make_stage top50 24 50 "top12,top24"
label_stage top50

python3 - "$OUT" <<'PY'
import json, sys
from pathlib import Path
out = Path(sys.argv[1])
rows = []
for stage in ("top12", "top24", "top50"):
    rows.extend(json.loads(line) for path in sorted((out / stage).glob("judgments_*_normalized.jsonl")) for line in path.open(encoding="utf-8") if line.strip())
(out / "judgments_hard_merged.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
PY

linkrag-eval golden-v2 qc --judgments "$OUT/judgments_hard_merged.jsonl" --report-out "$OUT/qc_hard.json" --markdown-out "$OUT/qc_hard.md" --max-unresolved-rate 0.60 --max-random-relevant-rate 0.05 --min-queries 80
linkrag-eval golden-v2 build --judgments "$OUT/judgments_hard_merged.jsonl" --out-dir "$OUT/golden" --user-id 990001 --tune-ratio 0.70

BLIND="$OUT/golden/hard_blind.jsonl"
for route in dense sparse bm25 dense,sparse,bm25; do
  label="${route//,/+}"
  linkrag-eval run --golden "$BLIND" --run-label "hard-${label}" --top-k 10 --enabled-sources "$route" --out-dir "$OUT/eval_${label}" --dataset hard_blind --precheck --require-chunk-references
done
log "hard set pipeline complete"
