"""Three synthetic read-only audit reproductions; no real inputs or services.

Run with the existing environment, e.g.:
PYTHONPATH=/Users/kawauso/Documents/Projects/LinkRag-Eval-issue22-completion/src \
  /Users/kawauso/Documents/Projects/LinkRag-Eval/.venv/bin/python \
  /tmp/linkrag-master-audit-20260913/experiment-repro.py

All generated data is stored under a temporary directory outside the repository.
The collector's pipeline constructor is replaced with three fake retrievers.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from linkrag_eval.golden.schema import GoldenSample
from linkrag_eval.metrics.cleaning import heading_scores, image_scores, parse_blocks
from linkrag_eval.metrics.retrieval import MAP
from linkrag_eval.models import Layer, RankedHit, StageOutput
from linkrag_eval.retrieval.learning_to_rank.cache import cache_ltr_candidates
from linkrag_eval.retrieval.learning_to_rank.experiment import _candidate_features

OUTPUT = Path(__file__).with_name("experiment-reproductions.json")


async def main() -> None:
    findings = []
    sample = GoldenSample(
        id="synthetic-query", query="synthetic", user_id=990001,
        dataset_ids=[992000], expected_chunk_ids=["old"], expected_doc_ids=[1],
    )
    calls = []

    class FakeRetriever:
        def __init__(self, source):
            self.source = source

        async def recall(self, *args, **kwargs):
            calls.append(self.source)
            return [
                SimpleNamespace(chunk_id=cid, doc_id=i, dataset_id=992000, score=1.0 / i)
                for i, cid in enumerate(["old", "new"], 1)
            ]

    pipeline = SimpleNamespace(
        _retrievers=[FakeRetriever(source) for source in ("dense", "sparse", "bm25")]
    )
    settings = SimpleNamespace(
        recall_dense_top_k=2, recall_sparse_top_k=2, recall_bm25_top_k=2,
    )
    with tempfile.TemporaryDirectory(prefix="linkrag-master-audit-synthetic-") as folder:
        with patch(
            "linkrag_eval.retrieval.recall_factory.build_eval_recall_pipeline",
            return_value=pipeline,
        ):
            out = Path(folder) / "cache.jsonl"
            await cache_ltr_candidates([sample], settings=settings, out=out)
            calls.clear()
            revised = replace(sample, expected_chunk_ids=["new"], expected_doc_ids=[2])
            report = await cache_ltr_candidates([revised], settings=settings, out=out)
            saved = json.loads(out.read_text())
            ids, _, labels = _candidate_features(
                saved, {"old": "old synthetic", "new": "new synthetic"},
            )
            observed = {
                "resumed": report["resumed"], "fetched": report["fetched"],
                "second_call_fake_retriever_calls": len(calls),
                "saved_expected_chunk_ids": saved["expected_chunk_ids"],
                "saved_expected_doc_ids": saved["expected_doc_ids"],
                "downstream_training_labels": dict(zip(ids, labels.tolist())),
            }
            assert observed["resumed"] == 1 and observed["fetched"] == 0
            assert observed["saved_expected_chunk_ids"] == ["old"]
            assert observed["saved_expected_doc_ids"] == [1]
            assert observed["downstream_training_labels"] == {"old": 1, "new": 0}
            findings.append({
                "id": "stale_supervision_on_candidate_cache_reuse",
                "requested_expected_chunk_ids": revised.expected_chunk_ids,
                "requested_expected_doc_ids": revised.expected_doc_ids,
                "observed": observed,
                "expected_downstream_training_labels": {"old": 0, "new": 1},
                "status": "reproduced",
            })

    ap_sample = replace(sample, expected_chunk_ids=["old", "new"])
    output = StageOutput(
        layer=Layer.RETRIEVAL, query="synthetic",
        ranked=[RankedHit(chunk_id="old", doc_id=1, dataset_id=992000, rank=0, score=1.0)],
    )
    ap = (await MAP().compute(ap_sample, output))[0]
    assert ap.value == 1.0 and ap.k is None
    findings.append({
        "id": "map_denominator_shrinks_with_returned_length",
        "relevant_chunk_ids": ["old", "new"], "returned_chunk_ids": ["old"],
        "observed": {"metric": ap.name, "k": ap.k, "value": ap.value},
        "expected_standard_untruncated_ap": 0.5,
        "status": "reproduced",
    })

    reference = "Only text."
    extra_image = "Only text.\n\n![fabricated](imaginary.png)"
    extra_heading = "# Fabricated heading\n\nOnly text."
    ref_blocks = parse_blocks(reference)
    image = image_scores(ref_blocks, parse_blocks(extra_image))
    heading = heading_scores(ref_blocks, parse_blocks(extra_heading))
    assert image.false_rate == 0.0 and heading.false_rate == 0.0
    findings.append({
        "id": "false_positive_rate_zero_when_reference_has_no_elements",
        "reference": reference,
        "image_case": {"produced": extra_image, "observed": asdict(image)},
        "heading_case": {"produced": extra_heading, "observed": asdict(heading)},
        "expected_image_false_rate": 1.0, "expected_heading_false_rate": 1.0,
        "status": "reproduced",
    })

    result = {
        "audit_head": "a6e2cc7019c9204bb0ccf7ac64051c41afa81342",
        "repository": "/Users/kawauso/Documents/Projects/LinkRag-Eval-issue22-completion",
        "input_scope": "entirely synthetic; no official inputs read",
        "execution_scope": "pure local functions and patched fake retrieval pipeline",
        "real_model_calls": 0, "network_calls": 0,
        "historical_result_impact_confirmed": False,
        "findings": findings,
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "reproduced", "findings": len(findings), "output": str(OUTPUT)}))


if __name__ == "__main__":
    asyncio.run(main())
