#!/usr/bin/env python3
"""Qualify two preselected, independent multilingual Reranker families.

The candidate pair and all sanity checks are fixed in this source before the
probe is run.  Only synthetic Chinese/English pairs are used; Dev, Gate A,
Blind, qrels, candidate snapshots and historical ranking outputs are never
read.  The output is a qualification recommendation, not P3-05 completion or
Gate A authorization.

Run in an isolated environment, for example:

    uv run --no-project --python 3.11 \
      --with sentence-transformers==5.7.0 \
      --with transformers==4.57.6 \
      --with einops==0.8.1 \
      scripts/qualify_robust_fusion_rerankers.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import shutil
import struct
import sys
import time
from pathlib import Path
from typing import Any

import einops
import numpy as np
import sentence_transformers
import torch
import transformers
from huggingface_hub import snapshot_download
from sentence_transformers import CrossEncoder

ARTIFACT_VERSION = "ROBUST-FUSION-RERANKER-QUALIFICATION-2026-08-28-v2"
SCIENTIFIC_PROTOCOL = "ROBUST-FUSION-RESEARCH-2026-08-28-v19"
PROGRESS_RECORD = "ROBUST-FUSION-PROGRESS-2026-08-28-v19"

MODEL_SPECS: tuple[dict[str, Any], ...] = (
    {
        "role": "generative_instruction_reranker",
        "model_id": "Qwen/Qwen3-Reranker-0.6B",
        "revision": "e61197ed45024b0ed8a2d74b80b4d909f1255473",
        "license": "Apache-2.0",
        "architecture_family": "Qwen3 decoder-only causal LM true-vs-false reranker",
        "parameter_class": "0.6B",
        "trust_remote_code": False,
        "max_length": 1024,
        "weight_files": {
            "model.safetensors": {
                "size_bytes": 1_191_588_280,
                "sha256": "27cd75a405b9c1b46b59abfd88aaa209e6fed2a1972cde9b70e7659537c5e65b",
            }
        },
        "selection_basis": (
            "modern instruction-aware generative ranking family, 100+ language model card, "
            "Apache-2.0, ungated exact local weights and student-scale smallest published size"
        ),
    },
    {
        "role": "discriminative_cross_encoder",
        "model_id": "jinaai/jina-reranker-v2-base-multilingual",
        "revision": "9cfeff2df7d40d1b78e75e5e9cebec92a99813c9",
        "license": "CC-BY-NC-4.0",
        "architecture_family": "XLM-RoBERTa sequence-classification cross-encoder",
        "parameter_class": "0.3B",
        "trust_remote_code": True,
        "max_length": 1024,
        "weight_files": {
            "model.safetensors": {
                "size_bytes": 556_892_306,
                "sha256": "ab2595ab9f34bdeffe645431d64c6e4aabe2ff5a57cfcacfef0727a97434238f",
            }
        },
        "selection_basis": (
            "conventional multilingual pointwise cross-encoder from an independent producer and "
            "architecture family; independently used in FEVER 2025 multi-reranker research; "
            "non-commercial license accepted by the research lead"
        ),
    },
)

DOWNLOAD_PATTERNS = (
    "README.md",
    "config.json",
    "config_sentence_transformers.json",
    "generation_config.json",
    "modules.json",
    "sentence_bert_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "chat_template.jinja",
    "vocab.json",
    "merges.txt",
    "model.safetensors",
    "1_LogitScore/*",
    "*.py",
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def score_sha256(scores: np.ndarray) -> str:
    digest = hashlib.sha256()
    for value in scores.astype(np.float32, copy=False):
        if not math.isfinite(float(value)):
            raise RuntimeError("Reranker produced NaN or Inf")
        digest.update(struct.pack("<f", float(value)))
    return digest.hexdigest()


def fixed_pairs() -> list[tuple[str, str, str]]:
    return [
        (
            "zh_correct",
            "认证企业账户从2026年3月起每月额度是多少？",
            "认证企业账户自2026年3月起，每月额度为3000元。",
        ),
        (
            "zh_numeric_conflict",
            "认证企业账户从2026年3月起每月额度是多少？",
            "认证企业账户自2026年3月起，每月额度为1000元。",
        ),
        (
            "zh_negation_conflict",
            "认证企业账户从2026年3月起每月额度是多少？",
            "认证企业账户在2026年3月后仍不能使用月度额度。",
        ),
        (
            "zh_unrelated",
            "认证企业账户从2026年3月起每月额度是多少？",
            "海豚通过回声定位感知水下环境。",
        ),
        (
            "en_correct",
            "What is the monthly limit for verified enterprise accounts after March 2026?",
            "Verified enterprise accounts have a monthly limit of 3000 after March 2026.",
        ),
        (
            "en_numeric_conflict",
            "What is the monthly limit for verified enterprise accounts after March 2026?",
            "Verified enterprise accounts have a monthly limit of 1000 after March 2026.",
        ),
        (
            "en_unrelated",
            "What is the monthly limit for verified enterprise accounts after March 2026?",
            "Dolphins use echolocation to perceive their underwater environment.",
        ),
    ]


def verify_weights(snapshot: Path, spec: dict[str, Any]) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    for relative, expected in spec["weight_files"].items():
        path = snapshot / relative
        if not path.is_file():
            raise RuntimeError(f"missing pinned weight: {spec['model_id']}:{relative}")
        size = path.stat().st_size
        digest = sha256_file(path)
        if size != expected["size_bytes"] or digest != expected["sha256"]:
            raise RuntimeError(
                f"weight drift: {spec['model_id']}:{relative}:{size}/{digest}"
            )
        verified.append({"relative_path": relative, "size_bytes": size, "sha256": digest})
    return verified


def metadata_files(snapshot: Path) -> list[dict[str, Any]]:
    paths = sorted(
        path
        for path in snapshot.rglob("*")
        if path.is_file() and path.name != "model.safetensors"
    )
    return [
        {
            "relative_path": str(path.relative_to(snapshot)),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in paths
    ]


def qualify_model(spec: dict[str, Any], cache_dir: Path) -> dict[str, Any]:
    snapshot = Path(
        snapshot_download(
            repo_id=spec["model_id"],
            revision=spec["revision"],
            cache_dir=cache_dir,
            allow_patterns=list(DOWNLOAD_PATTERNS),
        )
    )
    verified_weights = verify_weights(snapshot, spec)
    started = time.perf_counter()
    model = CrossEncoder(
        str(snapshot),
        device="cpu",
        max_length=spec["max_length"],
        trust_remote_code=spec["trust_remote_code"],
        activation_fn=torch.nn.Identity(),
        processor_kwargs={"fix_mistral_regex": True},
    )
    load_seconds = time.perf_counter() - started

    rows = fixed_pairs()
    pairs = [(query, passage) for _, query, passage in rows]
    started = time.perf_counter()
    first = np.asarray(
        model.predict(
            pairs,
            batch_size=len(pairs),
            show_progress_bar=False,
            convert_to_numpy=True,
        ),
        dtype=np.float32,
    ).reshape(-1)
    first_seconds = time.perf_counter() - started
    started = time.perf_counter()
    reverse = np.asarray(
        model.predict(
            list(reversed(pairs)),
            batch_size=len(pairs),
            show_progress_bar=False,
            convert_to_numpy=True,
        ),
        dtype=np.float32,
    ).reshape(-1)
    replay_seconds = time.perf_counter() - started
    second = np.flip(reverse)

    if first.shape != (len(rows),) or second.shape != first.shape:
        raise RuntimeError(f"score shape drift: {spec['model_id']}:{first.shape}/{second.shape}")
    if score_sha256(first) != score_sha256(second):
        maximum = float(np.max(np.abs(first.astype(np.float64) - second.astype(np.float64))))
        raise RuntimeError(f"order/replay score drift: {spec['model_id']}:{maximum}")

    by_id = {probe_id: float(first[index]) for index, (probe_id, _, _) in enumerate(rows)}
    sanity = {
        "zh_correct_gt_unrelated": by_id["zh_correct"] > by_id["zh_unrelated"],
        "en_correct_gt_unrelated": by_id["en_correct"] > by_id["en_unrelated"],
    }
    if not all(sanity.values()):
        raise RuntimeError(f"basic relevance sanity failed: {spec['model_id']}:{sanity}")

    score_rows = [
        {
            "probe_id": probe_id,
            "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
            "passage_sha256": hashlib.sha256(passage.encode("utf-8")).hexdigest(),
            "raw_score_float32": float(first[index]),
        }
        for index, (probe_id, query, passage) in enumerate(rows)
    ]
    del model
    return {
        **spec,
        "local_snapshot_identity": spec["revision"],
        "weight_files_verified": verified_weights,
        "metadata_files": metadata_files(snapshot),
        "score_contract": {
            "activation": "identity",
            "stored_dtype": "float32",
            "ranking_direction": "higher_is_better",
            "tie_break": "candidate_chunk_id_utf8_ascending",
            "pair_order": "query_then_passage",
            "max_length": spec["max_length"],
            "truncation": "longest_first",
            "tokenizer_fix_mistral_regex": True,
        },
        "probe_scores": score_rows,
        "score_vector_float32_sha256": score_sha256(first),
        "exact_replay_across_request_order": True,
        "sanity_checks": sanity,
        "timing_seconds": {
            "load": load_seconds,
            "first_batch": first_seconds,
            "reverse_order_replay_batch": replay_seconds,
            "batch_size": len(rows),
            "device": "cpu",
        },
        "qualification_status": "PASS",
    }


def build(cache_dir: Path) -> dict[str, Any]:
    torch.manual_seed(0)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    models = [qualify_model(spec, cache_dir) for spec in MODEL_SPECS]
    if models[0]["architecture_family"] == models[1]["architecture_family"]:
        raise RuntimeError("Reranker architecture families are not independent")
    return {
        "artifact_version": ARTIFACT_VERSION,
        "scientific_protocol": SCIENTIFIC_PROTOCOL,
        "progress_record": PROGRESS_RECORD,
        "status": "QUALIFIED_SELECTION_FROZEN_PENDING_RESOURCE_AND_DEV_CONTRACT",
        "p3_05_complete": False,
        "gate_a_executed": False,
        "outcome_data_read": False,
        "selection_fixed_before_probe": True,
        "selection_frozen_before_dev_and_gate_outcomes": True,
        "research_lead_confirmation": {
            "confirmed": True,
            "confirmed_on": "2026-08-28",
            "decision": (
                "freeze Qwen/Qwen3-Reranker-0.6B and "
                "jinaai/jina-reranker-v2-base-multilingual as the two Gate A families"
            ),
            "non_commercial_jina_use_confirmed": True,
        },
        "academic_support": {
            "jina_official_model_card": (
                "https://huggingface.co/jinaai/jina-reranker-v2-base-multilingual/tree/"
                "9cfeff2df7d40d1b78e75e5e9cebec92a99813c9"
            ),
            "independent_academic_use": {
                "title": "Language Model Re-rankers are Fooled by Lexical Similarities",
                "venue": "FEVER 2025, Association for Computational Linguistics",
                "doi": "10.18653/v1/2025.fever-1.2",
                "role": "the pinned Jina family appears in an independent six-reranker study",
            },
            "claim_boundary": (
                "Jina v2 is defined primarily by its official public model artifact/card; the "
                "independent paper supports academic adoption, not superiority or the present C1 result"
            ),
        },
        "models": models,
        "family_independence": {
            "different_architecture": True,
            "different_producer": True,
            "different_scoring_head": True,
            "same_model_artifact": False,
            "shares_similarity_encoder_artifact": False,
        },
        "implementation": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "sentence_transformers": sentence_transformers.__version__,
            "transformers": transformers.__version__,
            "torch": torch.__version__,
            "numpy": np.__version__,
            "einops": einops.__version__,
            "deterministic_algorithms": True,
            "torch_num_threads": torch.get_num_threads(),
        },
        "rejected_before_probe": [
            {
                "model_id": "BAAI/bge-reranker-v2-m3",
                "reason": "BGE/M3 naming and family were excluded after the research lead retired BGE-M3",
            },
            {
                "model_id": "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
                "reason": (
                    "lower-cost reserve only; its XLM-R-distilled tokenizer is identical to the main "
                    "E5 tokenizer artifact and it is weaker as the sole conventional confirmatory family"
                ),
            },
            {
                "model_id": "Alibaba-NLP/gte-multilingual-reranker-base",
                "reason": "custom remote code plus same-producer coupling with the Qwen family",
            },
        ],
        "qualification_attempt_history": [
            {
                "attempt": 1,
                "manifest_written": False,
                "failure": "pinned Jina custom code dependency einops was absent",
                "resolution": "pin einops==0.8.1 in the isolated runtime",
            },
            {
                "attempt": 2,
                "manifest_written": False,
                "failure": (
                    "Jina pinned custom code imports a symbol removed by transformers 5.16.1"
                ),
                "resolution": "pin transformers==4.57.6, which also satisfies Qwen3 requirements",
            },
            {
                "attempt": 3,
                "manifest_written": False,
                "failure": "tokenizer compatibility warning requested fix_mistral_regex=True",
                "resolution": "set processor_kwargs.fix_mistral_regex=true and replay both models",
            },
        ],
        "remaining_hard_gates": [
            "freeze formal batch size, precision and hardware after the P2-06 resource cap",
            "validate 1024-token truncation coverage and score replay on Dev without changing families",
            "seal exact model/code/tokenizer/config hashes with the candidate snapshot",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("data/robust_fusion/models/huggingface"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runs/robust_fusion/contracts/reranker-qualification-v2"),
    )
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    cache_dir = args.cache_dir if args.cache_dir.is_absolute() else repository_root / args.cache_dir
    output_root = (
        args.output_root if args.output_root.is_absolute() else repository_root / args.output_root
    )
    if output_root.exists():
        if not args.replace:
            raise RuntimeError(f"refusing to overwrite output: {output_root}")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    report = build(cache_dir)
    script_path = Path(__file__).resolve()
    report["generator"] = {
        "relative_path": str(script_path.relative_to(repository_root)),
        "sha256": sha256_file(script_path),
    }
    manifest_path = output_root / "manifest.json"
    manifest_path.write_text(canonical_json(report) + "\n", encoding="utf-8")
    (output_root / "manifest.sha256").write_text(
        f"{sha256_file(manifest_path)}  manifest.json\n", encoding="utf-8"
    )
    print(
        canonical_json(
            {
                "artifact_version": report["artifact_version"],
                "status": report["status"],
                "output_root": str(output_root),
                "manifest_sha256": sha256_file(manifest_path),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
