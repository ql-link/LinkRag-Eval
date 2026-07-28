#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$ROOT/runs/golden_v2/scale_100k_991004/scale_20k_overnight/balanced_query_expansion"
IFS=',' read -r -a SETS <<< "${SETS_CSV:-exact_identifier,short_keyword,dense_paraphrase,long_sparse}"

set_dir() {
  case "$1" in
    exact_identifier) echo "$BASE/grounded_exact_replacement" ;;
    exact_extension) echo "$BASE/grounded_exact_extension" ;;
    *) echo "$BASE/grounded_supplements/$1" ;;
  esac
}

seed_path() {
  case "$1" in
    exact_identifier) echo "$(set_dir "$1")/grounded_exact_seeds_180.jsonl" ;;
    exact_extension) echo "$(set_dir "$1")/seeds.jsonl" ;;
    *) echo "$(set_dir "$1")/seeds.jsonl" ;;
  esac
}

valid_pool() {
  local seeds="$1" pool="$2" report="$3"
  python3 - "$seeds" "$pool" "$report" <<'PY'
import json
import sys
from pathlib import Path

seed_path, pool_path, report_path = map(Path, sys.argv[1:])
if not pool_path.exists() or not report_path.exists():
    raise SystemExit(1)
seeds = [json.loads(line) for line in seed_path.open(encoding="utf-8") if line.strip()]
pools = [json.loads(line) for line in pool_path.open(encoding="utf-8") if line.strip()]
report = json.loads(report_path.read_text(encoding="utf-8"))
if len(pools) != len(seeds) or report.get("queries") != len(seeds):
    raise SystemExit(1)
if {row["query_id"] for row in pools} != {row["query_id"] for row in seeds}:
    raise SystemExit(1)
if any(len(row.get("candidates", [])) < 25 for row in pools):
    raise SystemExit(1)
PY
}

set -a
source "$ROOT/.env.eval"
set +a

for name in "${SETS[@]}"; do
  dir="$(set_dir "$name")"
  seeds="$(seed_path "$name")"
  pool="$dir/candidate_pool_top24.jsonl"
  report="$dir/candidate_pool_top24_report.json"
  if valid_pool "$seeds" "$pool" "$report"; then
    echo "candidate pool already valid: $name"
    continue
  fi
  rm -f "$pool" "$report"
  linkrag-eval golden-v2 candidate-pool-live \
    --seeds "$seeds" \
    --dataset-ids 992000,992001,992002,992003 \
    --sources bm25,dense,sparse,alt_embedding \
    --route-top-n 24 \
    --random-n 8 \
    --global-dataset-scope \
    --dense-score-threshold 0.0 \
    --sparse-score-threshold 0.0 \
    --alt-score-threshold -1.0 \
    --alt-cache-path "$ROOT/runs/alt_embedding_eval.sqlite3" \
    --out "$pool" \
    --report-out "$report"
done

python3 "$ROOT/scripts/build_report_index.py"
echo "grounded candidate pools complete"
