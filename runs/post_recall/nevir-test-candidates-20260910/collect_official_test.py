"""Run the established NevIR collector with a Test-only eval identity."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "nevir_ltr_collect_test", ROOT / "scripts/nevir_ltr_collect.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load established NevIR collector")
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)

collector.IDENTITY = {
    "dataset_id": 995301,
    "doc_id_base": 9953010000000,
    "qdrant_prefix": "eval_nevir_test_20260910",
    "corpus_count": 2081,
}
collector.LIMITS = {"ingestion": 2600, "test": 6000}
collector.QUERY_COUNTS = {"test": 2766}


def bound_settings(root: Path):
    """Bind the same runtime contract from the restored main NevIR manifest."""
    from linkrag_eval.config import get_settings
    from linkrag_eval.runners.t2_workflow import encoder_semantics

    settings = get_settings()
    historical = collector.read_json(
        ROOT
        / "runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment/run.json"
    )["collection_runtime"]
    if encoder_semantics(settings) != historical["encoders"]:
        raise ValueError("current encoder/BM25 semantics differ from the frozen NevIR run")
    expected = {
        "embed_batch_size": 10,
        "embed_concurrency": 4,
        "sparse_concurrency": 8,
        "user_id": 990001,
        "sparse_vector_name": "sparse_text",
    }
    expected.update({f"recall_{key}_top_k": value for key, value in collector.DEPTHS.items()})
    expected.update(
        {f"recall_{key}_score_threshold": value for key, value in collector.THRESHOLDS.items()}
    )
    expected.update({f"recall_{key}_weight": value for key, value in collector.WEIGHTS.items()})
    if any(getattr(settings, key) != value for key, value in expected.items()):
        raise ValueError("current route/batch settings differ from the frozen NevIR run")
    return settings.model_copy(
        update={
            "db_url": f"sqlite+aiosqlite:///{root / 'storage/corpus.sqlite3'}",
            "bm25_sqlite_path": str(root / "storage/bm25.sqlite3"),
            "qdrant_prefix": collector.IDENTITY["qdrant_prefix"],
        }
    )


collector.bound_settings = bound_settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--stage", choices=("ingestion", "test"), required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(
        collector.run(args.run_dir, args.stage, resume=args.resume)
    )
    print(collector.json.dumps(result, ensure_ascii=False))
    return 0 if result.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
