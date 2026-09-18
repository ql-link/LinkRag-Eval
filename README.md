# LinkRag-Eval

Companion repository for the paper:

**Preference Is Not Position: Evaluating Reranking on NevIR in Fixed Hybrid Candidate Pools**

## What this study evaluates

Starting from a fixed hybrid candidate pool — dense, learned-sparse, and BM25
candidates kept as retrieved — the evaluation scores reranking methods jointly on
two aspects of the designated passages: strict pairwise preference and the
position of the preferred passage. Five rankers are compared: Fusion, a
pair-trained E0, an N=8 variant, BGE, and Qwen. Retrieval itself is not modified.

## Reproduction entry point: recompute from saved scores

The default entry point replays the evaluation from the saved per-query scores
inside the reproduction package. It regenerates three tables, two figure data
sets, and the auxiliary tiebreak results. It needs no GPU, no API keys, and no
Qdrant service; NumPy is the only dependency. Python 3.11 or newer is required.

```bash
unzip linkrag-nevir-reproduction.zip
cd linkrag-nevir-reproduction
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -B -m unittest -v test_reproduction
.venv/bin/python -B reproduce.py --output reproduced
```

The output directory must not already exist; use a different name on a second
run. `reproduced/verification.json` should report `VERIFIED_CACHE_REPLAY`.

Package download: get `linkrag-nevir-reproduction.zip` from the
[release page](https://github.com/ql-link/LinkRag-Eval/releases/tag/reproduction)
([direct download](https://github.com/ql-link/LinkRag-Eval/releases/download/reproduction/linkrag-nevir-reproduction.zip)).
Download this attached asset — GitHub's automatically generated "Source code"
archives do not include the cached-score data package.

## Verified environment

- macOS arm64, Python 3.11.15, NumPy 2.4.6
- All 10 bundled tests pass; replay ends with `VERIFIED_CACHE_REPLAY`
  (96,572 scalar fields compared, 38 files verified, integers exact,
  float absolute tolerance 1e-12, no new inference executed)

Other platforms and Python versions are not claimed as verified.

## Scope of the verification

The replay regenerates the reported tables and figure data from saved scores.
It does not cover retraining, live model inference, or rebuilding the retrieval
pipeline. The package README documents optional Qwen/BGE re-inference only; it
does not provide full retraining or retrieval-rebuild tutorials.

## Repository documentation

For development documentation inside this repository, see
[docs/DOCUMENT_CATALOG.md](docs/DOCUMENT_CATALOG.md).
