#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${OUT:-$ROOT/runs/golden_v2/scale_100k_991004/scale_20k_overnight/balanced_query_expansion/grounded_exact_replacement}"
BATCH_DIR="$OUT/generation_batches"
LOG_DIR="$OUT/logs"
MAX_JOBS="${MAX_JOBS:-4}"
EXPECTED_QUERIES="${EXPECTED_QUERIES:-180}"
SEEDS_NAME="${SEEDS_NAME:-grounded_exact_seeds_180.jsonl}"
SOURCE_NAME="${SOURCE_NAME:-codex_grounded_exact_v2}"
mkdir -p "$LOG_DIR"

validate_queries() {
  local targets="$1" queries="$2"
  python3 - "$targets" "$queries" <<'PY'
import json
import re
import sys
from pathlib import Path

exact_re = re.compile(
    r"(?:v\d+(?:\.\d+){0,3}|\d{4}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?|"
    r"\d+(?:\.\d+)?\s*(?:%|元|小时|分钟|天|次|个|份|MB|GB|kg|工作日))",
    flags=re.IGNORECASE,
)
target_path, query_path = map(Path, sys.argv[1:])
targets = [json.loads(line) for line in target_path.open(encoding="utf-8") if line.strip()]
rows = [json.loads(line) for line in query_path.open(encoding="utf-8") if line.strip()]
target_by_id = {row["query_id"]: row for row in targets}
if len(rows) != len(targets) or {row.get("query_id") for row in rows} != set(target_by_id):
    raise SystemExit("generated query IDs do not match targets")
if len({str(row.get("query") or "").strip() for row in rows}) != len(rows):
    raise SystemExit("duplicate generated queries in batch")
required = {"query_id", "query", "reason", "generator_model"}
for row in rows:
    if not required.issubset(row):
        raise SystemExit("missing generated query fields")
    query = str(row["query"]).strip()
    if not 8 <= len(query) <= 120:
        raise SystemExit(f"query length out of range: {row['query_id']}")
    query_exact = {value.lower().replace(" ", "") for value in exact_re.findall(query)}
    content_exact = {
        value.lower().replace(" ", "")
        for value in target_by_id[row["query_id"]]["exact_expressions"]
    }
    if not query_exact:
        raise SystemExit(f"query has no exact expression: {row['query_id']}")
    if not query_exact.issubset(content_exact):
        raise SystemExit(
            f"query invented exact expression: {row['query_id']} "
            f"query={sorted(query_exact)} content={sorted(content_exact)}"
        )
PY
}

generate_one() {
  local targets="$1"
  local stem queries prompt
  stem="$(basename "$targets" .jsonl)"
  queries="$BATCH_DIR/queries_${stem#targets_}.jsonl"
  prompt="Read ${targets#$ROOT/}. Generate exactly one realistic Chinese retrieval query for every target chunk. The target chunk must fully answer the query. Preserve query_id exactly. Every number, date, version, percentage, duration, amount, count or identifier used in the query must appear verbatim in the target content; never invent a value. Use the exact expression as a real decision condition, not decorative text. Paraphrase the surrounding intent naturally and do not copy a full source sentence. The query should be answerable by one chunk and should remain challenging through paraphrase or added supported constraints. Write JSONL only to ${queries#$ROOT/}, one row per target, with query_id, query, reason, generator_model."
  if [[ -f "$queries" ]] && validate_queries "$targets" "$queries"; then
    return
  fi
  rm -f "$queries"
  if ! (
    cd "$ROOT"
    codex --ask-for-approval never -c model_reasoning_effort=high exec --ephemeral \
      --model gpt-5.3-codex-spark --sandbox workspace-write "$prompt"
  ) >"$LOG_DIR/${stem}_spark.log" 2>&1 || ! validate_queries "$targets" "$queries"; then
    rm -f "$queries"
    (
      cd "$ROOT"
      codex --ask-for-approval never -c model_reasoning_effort=high exec --ephemeral \
        --model gpt-5.4-mini --sandbox workspace-write "$prompt"
    ) >"$LOG_DIR/${stem}_mini.log" 2>&1
    validate_queries "$targets" "$queries"
  fi
}

jobs=()
for targets in "$BATCH_DIR"/targets_*.jsonl; do
  generate_one "$targets" &
  jobs+=("$!")
  if [[ "${#jobs[@]}" -ge "$MAX_JOBS" ]]; then
    for pid in "${jobs[@]}"; do wait "$pid"; done
    jobs=()
  fi
done
for pid in ${jobs[*]-}; do wait "$pid"; done

python3 - "$BATCH_DIR" "$OUT/$SEEDS_NAME" "$EXPECTED_QUERIES" "$SOURCE_NAME" <<'PY'
import json
import sys
from pathlib import Path

batch_dir = Path(sys.argv[1])
out_path = Path(sys.argv[2])
expected_queries = int(sys.argv[3])
source_name = sys.argv[4]
rows = []
for target_path in sorted(batch_dir.glob("targets_*.jsonl")):
    batch = target_path.stem.removeprefix("targets_")
    query_path = batch_dir / f"queries_{batch}.jsonl"
    targets = {
        row["query_id"]: row
        for line in target_path.open(encoding="utf-8")
        if line.strip()
        for row in [json.loads(line)]
    }
    queries = [json.loads(line) for line in query_path.open(encoding="utf-8") if line.strip()]
    for query in queries:
        target = targets[query["query_id"]]
        rows.append(
            {
                "query_id": query["query_id"],
                "query": query["query"],
                "role": "realistic",
                "source": source_name,
                "type_hint": "exact_identifier",
                "hard_reason": "grounded_exact_expression",
                "dataset_ids": [target["dataset_id"]],
                "target_chunk_id": target["chunk_id"],
                "target_doc_id": target["doc_id"],
                "exact_expressions": target["exact_expressions"],
                "generation_reason": query["reason"],
            }
        )
if len(rows) != expected_queries or len({row["query_id"] for row in rows}) != expected_queries:
    raise SystemExit(f"expected {expected_queries} unique generated queries, got {len(rows)}")
if len({row["query"] for row in rows}) != len(rows):
    raise SystemExit("duplicate queries across generation batches")
out_path.write_text(
    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
    encoding="utf-8",
)
(out_path.parent / "generation_report.json").write_text(
    json.dumps(
        {
            "queries": len(rows),
            "datasets": {
                str(dataset_id): sum(dataset_id in row["dataset_ids"] for row in rows)
                for dataset_id in sorted({row["dataset_ids"][0] for row in rows})
            },
            "grounding_rule": "all exact expressions in query must exist in target chunk",
            "output": str(out_path),
        },
        ensure_ascii=False,
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
PY

python3 "$ROOT/scripts/build_report_index.py"
echo "grounded exact query generation complete"
