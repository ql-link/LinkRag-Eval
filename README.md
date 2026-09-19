# LinkRag-Eval

English | [简体中文](README.zh-CN.md)

## Project overview

`LinkRag-Eval` is an **independent retrieval evaluation / quality-check project**
split off from toLink-Rag. It reuses the production system's pure computation,
retrieval components under evaluation, and Qdrant primitives, while managing
evaluation data ingestion, retrieval orchestration, and scoring. It uses local
SQLite (default `runs/linkrag_eval.sqlite3`) and Qdrant collections with an `eval`
prefix,
isolated from production storage: it never reads or writes production tables,
and real configuration values live only in the Git-ignored `.env.eval`.

The project hosts both research experiments and paper reproduction: the paper
artifact is a separately distributed cached-score replay package (see "Research
and paper reproduction"), while this repository is the full evaluation
engineering project; the two have different prerequisites and runtime
dependencies.

## Key capabilities

- Independent data ingest: corpus and query ingestion, with metadata and results
  written to local SQLite.
- Hybrid retrieval: Dense, Learned Sparse, and SQLite FTS5 BM25. Dense/Sparse
  encoding is handled by eval's own `llm/` module; chunking reuses production
  pure computation through an adapter; BM25 tokenizes inside eval. Enabling
  all three retrieval routes requires `bm25_mode=sqlite_fts5`; `stub` uses
  Dense/Sparse only.
- Candidate snapshots: per-route candidates and scores saved for reuse by later
  experiments on fixed candidate pools.
- Metrics: evaluation metrics such as preference and position (pure functions).
- LambdaMART and ranking diagnostics: the existing 38-dimensional
  `candidate_difference_v3` features and fallback capability; both the Chinese
  baseline (`models/chinese-baseline/`) and the English baseline
  (`models/english-baseline/`) are retained, while historical A/B and legacy
  controls remain only as historical evidence.

## Research and paper reproduction

Companion paper: **Preference Is Not Position: Evaluating Reranking on NevIR in
Fixed Hybrid Candidate Pools**. Within the fixed candidate pool produced by
the three retrievers, the study jointly evaluates strict preference and position
for the designated passages, comparing five ranking methods — Fusion, E0, N=8,
BGE, and Qwen — without modifying retrieval.

The reproduction package is a separately distributed cached-score replay bundle.
It recomputes the paper's three tables, two figure data sets, and the auxiliary
tiebreak results from saved per-query scores. **Python 3.11 or newer** is
required; NumPy is the only third-party Python dependency. **CPU is sufficient —
no GPU, API keys, database, or Qdrant service needed** (this simplification
applies only to the replay bundle, not to the full project; see the next
section).

- Release page: [reproduction](https://github.com/ql-link/LinkRag-Eval/releases/tag/reproduction)
- Asset download: [`linkrag-nevir-reproduction.zip`](https://github.com/ql-link/LinkRag-Eval/releases/download/reproduction/linkrag-nevir-reproduction.zip)
  (download this attached asset; GitHub's automatically generated "Source code"
  archives do not include the cached-score data)

```bash
unzip linkrag-nevir-reproduction.zip
cd linkrag-nevir-reproduction
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -B -m unittest -v test_reproduction
.venv/bin/python -B reproduce.py --output reproduced
```

The output directory `reproduced` must not already exist; pass a new directory
name to `--output` on subsequent runs.

Verified environment: macOS arm64, Python 3.11.15, NumPy 2.4.6; all 10 tests
pass and `reproduced/verification.json` reports `VERIFIED_CACHE_REPLAY`. The
verification covers replaying saved scores; it does not cover retraining, live
model inference, or rebuilding retrieval. The package README additionally
documents optional Qwen/BGE re-inference only.

## Installation and development

> To be verified: install the production dependency toLink-Rag in editable mode
> from a local path available on your machine; CI pins it to the fixed git SHA
> `861f2481` (see the pyproject.toml comment and AGENTS.md). Confirm this
> dependency is available before installing.

- Python ≥ 3.11. First install toLink-Rag locally in editable mode (it exposes
  the `src` top-level package), then `python3 -m pip install -e ".[dev,ltr]"` to
  install this project and its testing and validation dependencies (matching CI);
  `ltr` pulls in LightGBM and scikit-learn for LambdaMART training.
- Configuration: copy `.env.eval.example` to `.env.eval` and fill in real values
  (gitignored).
- Database: local SQLite `runs/linkrag_eval.sqlite3` by default; create tables
  via the Alembic migration `alembic upgrade head`. `init_eval_schema()` is only
  for tests or quick local setup.
- Checks (no live stack required):

```bash
python3 -m pytest -m "not integration" -q
lint-imports
```

## Documentation and history

| What you want | Where |
| --- | --- |
| Not sure which document to read | [Document catalog](docs/DOCUMENT_CATALOG.md) |
| Current progress and next steps | [Current status](docs/CURRENT_STATUS.md) |
| Review experiments or record a new one | [Experiment log](docs/experiments/EXPERIMENT_LOG.md) |
| Where files live and what Git/backups cover | [Workspace map](docs/WORKSPACE_MAP.md) |
| Inputs and baseline models | [Data](data/README.md) · [Models](models/README.md) |
| Pick a script or command | [Usage directory](scripts/README.md) |
| Experiment conclusions and their scope | [Report index](docs/reports/REPORT_INDEX.md) |
| Actual files from a run | [Runs directory](runs/post_recall/README.md) |
| Change engineering code | [Conventions](AGENTS.md) · [Architecture](docs/architecture/decoupling-plan.md) |

Historical preservation: pre-restructure source is kept under the tag
`research-pre-restructure-20260906` (commit `4d31f18`); view it with
`git show research-pre-restructure-20260906:<path>` or check it out in a
separate directory. Backup locations and recovery for Git-ignored evidence are
described in
[the recovery notes](docs/plans/runtime-simplification-2026-09-06.md#recovery).
No human tasks are active; [human_tasks/README.md](human_tasks/README.md) only
documents historical entry points. Steps and thresholds in historical protocols
do not automatically become prerequisites for current research.
