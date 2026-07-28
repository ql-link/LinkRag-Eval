#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$ROOT/runs/golden_v2/scale_100k_991004/scale_20k_overnight/balanced_query_expansion"
STAGE="${STAGE:-top24_extension}"
ADDITIONAL_CANDIDATES="${ADDITIONAL_CANDIDATES:-12}"
BATCH_SIZE="${BATCH_SIZE:-5}"
MAX_JOBS="${MAX_JOBS:-4}"
OUT="$BASE/$STAGE"
LOG_ROOT="$BASE/logs/$STAGE"
IFS=',' read -r -a SCENARIOS <<< "${SCENARIOS_CSV:-short_keyword,exact_identifier,long_sparse,dense_paraphrase}"
mkdir -p "$OUT" "$LOG_ROOT"

base_judgments() {
  if [[ -n "${BASE_STAGE:-}" ]]; then
    echo "$BASE/$BASE_STAGE/$1/judgments_combined.jsonl"
    return
  fi
  case "$1" in
    short_keyword) echo "$BASE/canonical_top12/short_keyword/judgments_merged.jsonl" ;;
    *) echo "$BASE/canonical_top12_v2/$1/judgments_merged.jsonl" ;;
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
expected_queries = {pool["query_id"] for pool in pools}
candidate_ids = {
    pool["query_id"]: {candidate["chunk_id"] for candidate in pool["candidates"]}
    for pool in pools
}
actual_queries = [str(row.get("query_id") or "") for row in rows]
if len(rows) != len(expected_queries) or set(actual_queries) != expected_queries:
    raise SystemExit(
        f"decision query mismatch expected={len(expected_queries)} actual={len(rows)}"
    )
if len(set(actual_queries)) != len(actual_queries):
    raise SystemExit("duplicate query decisions")
required = {"query_id", "relevant_chunk_id", "evidence_span", "reason", "judge_model"}
for row in rows:
    if not required.issubset(row):
        raise SystemExit("missing decision fields")
    chunk_id = row.get("relevant_chunk_id")
    if chunk_id is not None and str(chunk_id) not in candidate_ids[str(row["query_id"])]:
        raise SystemExit(f"invalid relevant_chunk_id: {row['query_id']} {chunk_id}")
PY
}

expand_decisions() {
  local pool="$1" decisions="$2" normalized="$3"
  python3 - "$pool" "$decisions" "$normalized" <<'PY'
import json
import sys
from pathlib import Path

pool_path, decision_path, out_path = map(Path, sys.argv[1:])
decisions = {
    row["query_id"]: row
    for line in decision_path.open(encoding="utf-8")
    if line.strip()
    for row in [json.loads(line)]
}
normalized = []
for line in pool_path.open(encoding="utf-8"):
    pool = json.loads(line)
    decision = decisions[pool["query_id"]]
    selected = decision.get("relevant_chunk_id")
    for candidate in pool["candidates"]:
        relevant = selected is not None and str(candidate["chunk_id"]) == str(selected)
        normalized.append(
            {
                "query_id": pool["query_id"],
                "query": pool["query"],
                "role": pool.get("role", "realistic"),
                "source": pool.get("source"),
                "type_hint": pool.get("type_hint"),
                "hard_reason": pool.get("hard_reason"),
                "relevant": relevant,
                "grade": 3 if relevant else 0,
                "evidence_span": decision.get("evidence_span", "") if relevant else "",
                "reason": (
                    decision.get("reason", "canonical evidence selected")
                    if relevant
                    else "not selected as canonical evidence"
                ),
                "judge_failed": False,
                "judge_model": decision["judge_model"],
                "candidate": {
                    key: candidate[key]
                    for key in (
                        "chunk_id", "doc_id", "dataset_id", "sources", "rank_by_source"
                    )
                },
            }
        )
out_path.write_text(
    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in normalized),
    encoding="utf-8",
)
PY
}

label_one() {
  local scenario="$1" pool="$2"
  local stem decisions normalized prompt
  stem="$(basename "$pool" .jsonl)"
  decisions="${pool%/*}/decisions_${stem#pool_}.jsonl"
  normalized="${pool%/*}/judgments_${stem#pool_}_normalized.jsonl"
  prompt="Read ${pool#$ROOT/}. For each query, compare every candidate chunk as one group and select at most one canonical evidence chunk. A selected chunk must explicitly support every decisive condition and requested outcome, including exact identifiers, numbers, dates, versions, exceptions and state constraints. Topical, partial, adjacent, contradictory, generic and duplicate chunks do not qualify. Write exactly one JSONL decision per query only to ${decisions#$ROOT/}. Copy query_id and any selected chunk_id exactly from the input. Required fields: query_id, relevant_chunk_id, evidence_span, reason, judge_model. Set relevant_chunk_id to null when no candidate fully supports the query. Do not output per-candidate judgments; the local validator expands decisions after ID validation."
  if [[ -f "$decisions" ]] && validate_decisions "$pool" "$decisions"; then
    expand_decisions "$pool" "$decisions" "$normalized"
    return
  fi
  rm -f "$decisions" "$normalized"
  if ! (
    cd "$ROOT"
    codex --ask-for-approval never -c model_reasoning_effort=high exec --ephemeral \
      --model gpt-5.3-codex-spark --sandbox workspace-write "$prompt"
  ) >"$LOG_ROOT/${scenario}_${stem}_spark.log" 2>&1 || ! validate_decisions "$pool" "$decisions"; then
    rm -f "$decisions"
    (
      cd "$ROOT"
      codex --ask-for-approval never -c model_reasoning_effort=high exec --ephemeral \
        --model gpt-5.4-mini --sandbox workspace-write "$prompt"
    ) >"$LOG_ROOT/${scenario}_${stem}_mini.log" 2>&1
    validate_decisions "$pool" "$decisions"
  fi
  expand_decisions "$pool" "$decisions" "$normalized"
}

for scenario in "${SCENARIOS[@]}"; do
  python3 "$ROOT/scripts/prepare_balanced_query_extension.py" \
    --candidate-pool "$BASE/${scenario}_candidate_pool_top24.jsonl" \
    --judgments "$(base_judgments "$scenario")" \
    --out-dir "$OUT/$scenario" \
    --additional-candidates "$ADDITIONAL_CANDIDATES" \
    --batch-size "$BATCH_SIZE"
done

jobs=()
for scenario in "${SCENARIOS[@]}"; do
  for pool in "$OUT/$scenario"/pool_*.jsonl; do
    label_one "$scenario" "$pool" &
    jobs+=("$!")
    if [[ "${#jobs[@]}" -ge "$MAX_JOBS" ]]; then
      for pid in "${jobs[@]}"; do wait "$pid"; done
      jobs=()
    fi
  done
done
for pid in ${jobs[*]-}; do wait "$pid"; done

for scenario in "${SCENARIOS[@]}"; do
  python3 - "$(base_judgments "$scenario")" "$OUT/$scenario" "$LOG_ROOT/$scenario" <<'PY'
import json
import sys
from pathlib import Path

base_path = Path(sys.argv[1])
out_dir = Path(sys.argv[2])
log_prefix = Path(sys.argv[3])
extension_rows = []
for path in sorted(out_dir.glob("judgments_[0-9][0-9][0-9]_normalized.jsonl")):
    batch = path.stem.removeprefix("judgments_").removesuffix("_normalized")
    mini_log = log_prefix.parent / f"{log_prefix.name}_pool_{batch}_mini.log"
    actual_model = "gpt-5.4-mini" if mini_log.exists() else "gpt-5.3-codex-spark"
    for line in path.open(encoding="utf-8"):
        if line.strip():
            row = json.loads(line)
            row["judge_model"] = actual_model
            extension_rows.append(row)
(out_dir / "judgments_extension_merged.jsonl").write_text(
    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in extension_rows),
    encoding="utf-8",
)
combined = base_path.read_text(encoding="utf-8") + "".join(
    json.dumps(row, ensure_ascii=False) + "\n" for row in extension_rows
)
(out_dir / "judgments_combined.jsonl").write_text(combined, encoding="utf-8")
PY
  linkrag-eval golden-v2 qc \
    --judgments "$OUT/$scenario/judgments_combined.jsonl" \
    --report-out "$OUT/$scenario/qc.json" \
    --markdown-out "$OUT/$scenario/qc.md" \
    --max-unresolved-rate 1.0 \
    --max-random-relevant-rate 0.05 \
    --min-queries 150
done

python3 "$ROOT/scripts/build_report_index.py"
echo "balanced query extension complete: $STAGE"
