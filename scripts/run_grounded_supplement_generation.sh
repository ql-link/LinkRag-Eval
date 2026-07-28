#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/runs/golden_v2/scale_100k_991004/scale_20k_overnight/balanced_query_expansion/grounded_supplements"
MAX_JOBS="${MAX_JOBS:-4}"
IFS=',' read -r -a SCENARIOS <<< "${SCENARIOS_CSV:-short_keyword,dense_paraphrase,long_sparse}"

validate_queries() {
  local scenario="$1" targets="$2" queries="$3"
  python3 - "$scenario" "$targets" "$queries" <<'PY'
import json
import re
import sys
from pathlib import Path

scenario = sys.argv[1]
target_path, query_path = map(Path, sys.argv[2:])
targets = {row["query_id"]: row for row in map(json.loads, target_path.read_text().splitlines())}
rows = list(map(json.loads, query_path.read_text().splitlines()))
if len(rows) != len(targets) or {row.get("query_id") for row in rows} != set(targets):
    raise SystemExit("generated query IDs do not match targets")
if len({str(row.get("query") or "").strip() for row in rows}) != len(rows):
    raise SystemExit("duplicate generated queries in batch")
required = {"query_id", "query", "reason", "generator_model"}
number_re = re.compile(r"\d+(?:\.\d+)?")
for row in rows:
    if not required.issubset(row):
        raise SystemExit("missing generated query fields")
    query = str(row["query"]).strip()
    length = len(query)
    if scenario == "short_keyword" and not 4 <= length <= 15:
        raise SystemExit(f"short query length invalid: {row['query_id']} {length}")
    if scenario == "dense_paraphrase" and not 16 <= length <= 35:
        raise SystemExit(f"dense query length invalid: {row['query_id']} {length}")
    if scenario == "long_sparse" and not 36 <= length <= 140:
        raise SystemExit(f"long query length invalid: {row['query_id']} {length}")
    query_numbers = set(number_re.findall(query))
    content_numbers = set(number_re.findall(targets[row["query_id"]]["content"]))
    if not query_numbers.issubset(content_numbers):
        raise SystemExit(f"query invented numeric value: {row['query_id']}")
PY
}

generate_one() {
  local scenario="$1" targets="$2"
  local stem queries log_dir constraint prompt
  stem="$(basename "$targets" .jsonl)"
  queries="${targets%/*}/queries_${stem#targets_}.jsonl"
  log_dir="${targets%/*}/logs"
  mkdir -p "$log_dir"
  case "$scenario" in
    short_keyword) constraint="Query must be 4-15 Chinese characters and look like a natural terse search phrase." ;;
    dense_paraphrase) constraint="Query must be 16-35 Chinese characters and semantically paraphrase the rule without copying its main wording." ;;
    long_sparse) constraint="Query must be 36-140 Chinese characters and include at least two conditions that the same target chunk explicitly supports." ;;
  esac
  prompt="Read ${targets#$ROOT/}. Generate exactly one realistic Chinese retrieval query for every target chunk. Preserve query_id exactly. The target chunk must fully answer the query. ${constraint} Do not invent any number, date, version, identifier, threshold, exception or outcome; any numeric value in the query must occur in the target content. Avoid copying a complete source sentence. Write JSONL only to ${queries#$ROOT/}, one row per target, with query_id, query, reason, generator_model."
  if [[ -f "$queries" ]] && validate_queries "$scenario" "$targets" "$queries"; then
    return
  fi
  rm -f "$queries"
  if ! (
    cd "$ROOT"
    codex --ask-for-approval never -c model_reasoning_effort=high exec --ephemeral \
      --model gpt-5.3-codex-spark --sandbox workspace-write "$prompt"
  ) >"$log_dir/${stem}_spark.log" 2>&1 || ! validate_queries "$scenario" "$targets" "$queries"; then
    rm -f "$queries"
    (
      cd "$ROOT"
      codex --ask-for-approval never -c model_reasoning_effort=high exec --ephemeral \
        --model gpt-5.4-mini --sandbox workspace-write "$prompt"
    ) >"$log_dir/${stem}_mini.log" 2>&1
    validate_queries "$scenario" "$targets" "$queries"
  fi
}

jobs=()
for scenario in "${SCENARIOS[@]}"; do
  for targets in "$OUT/$scenario"/targets_[0-9][0-9][0-9].jsonl; do
    generate_one "$scenario" "$targets" &
    jobs+=("$!")
    if [[ "${#jobs[@]}" -ge "$MAX_JOBS" ]]; then
      for pid in "${jobs[@]}"; do wait "$pid"; done
      jobs=()
    fi
  done
done
for pid in ${jobs[*]-}; do wait "$pid"; done

for scenario in "${SCENARIOS[@]}"; do
  python3 - "$scenario" "$OUT/$scenario" <<'PY'
import json
import sys
from pathlib import Path

scenario = sys.argv[1]
scenario_dir = Path(sys.argv[2])
rows = []
for target_path in sorted(scenario_dir.glob("targets_[0-9][0-9][0-9].jsonl")):
    batch = target_path.stem.removeprefix("targets_")
    targets = {
        row["query_id"]: row
        for row in map(json.loads, target_path.read_text(encoding="utf-8").splitlines())
    }
    queries = list(
        map(
            json.loads,
            (scenario_dir / f"queries_{batch}.jsonl").read_text(encoding="utf-8").splitlines(),
        )
    )
    for query in queries:
        target = targets[query["query_id"]]
        rows.append(
            {
                "query_id": query["query_id"],
                "query": query["query"],
                "role": "realistic",
                "source": "codex_grounded_supplement_v1",
                "type_hint": scenario,
                "hard_reason": "grounded_scenario_supplement",
                "dataset_ids": [target["dataset_id"]],
                "target_chunk_id": target["chunk_id"],
                "target_doc_id": target["doc_id"],
                "generation_reason": query["reason"],
            }
        )
expected = {"short_keyword": 28, "dense_paraphrase": 12, "long_sparse": 72}[scenario]
if len(rows) != expected or len({row["query"] for row in rows}) != expected:
    raise SystemExit(f"{scenario}: expected {expected} unique queries, got {len(rows)}")
(scenario_dir / "seeds.jsonl").write_text(
    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
    encoding="utf-8",
)
(scenario_dir / "generation_report.json").write_text(
    json.dumps({"scenario": scenario, "queries": len(rows)}, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY
done

python3 "$ROOT/scripts/build_report_index.py"
echo "grounded supplement generation complete"
