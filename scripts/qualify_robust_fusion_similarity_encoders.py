#!/usr/bin/env python3
"""Qualify the pinned non-BGE similarity encoders for Robust Fusion.

Selection is fixed in this source before any probe is run.  The script uses
synthetic, outcome-free Chinese/English inputs and records only hashes, token
counts, dimensions, norms, predetermined cosine checks and runtime metadata.
It never reads Dev, Gate A or Blind data.

Run in an isolated environment, for example:

    uv run --no-project --python 3.11 \
      --with sentence-transformers==5.7.0 \
      scripts/qualify_robust_fusion_similarity_encoders.py
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

import numpy as np
import sentence_transformers
import torch
import transformers
from huggingface_hub import snapshot_download
from sentence_transformers import SentenceTransformer

ARTIFACT_VERSION = "ROBUST-FUSION-SIMILARITY-ENCODER-QUALIFICATION-2026-08-28-v3"
SCIENTIFIC_PROTOCOL = "ROBUST-FUSION-RESEARCH-2026-08-28-v19"
SIMILARITY_MANIFEST = "ROBUST-FUSION-SIMILARITY-MANIFEST-2026-08-28-v5"

MODELS: tuple[dict[str, Any], ...] = (
    {
        "role": "main_similarity_encoder",
        "model_id": "intfloat/multilingual-e5-base",
        "revision": "d128750597153bb5987e10b1c3493a34e5a4502a",
        "license": "MIT",
        "architecture_family": "XLM-RoBERTa multilingual E5",
        "dimension": 768,
        "max_tokens": 512,
        "input_prefix": "query: ",
        "tokenizer_id": "intfloat/multilingual-e5-base",
        "tokenizer_revision": "d128750597153bb5987e10b1c3493a34e5a4502a",
        "pooling": "attention-mask mean pooling followed by sentence-transformers Normalize",
        "output_layer": "last_hidden_state",
        "weight_files": {
            "model.safetensors": {
                "size_bytes": 1_112_201_288,
                "sha256": "a18a44fad1d0b46ded15928144138cff1135d5cc8233bdd90be5f18822de09a7",
            }
        },
        "selection_basis": (
            "predeclared multilingual Chinese/English coverage, symmetric-similarity guidance, "
            "512-token input, local pinned weights, MIT license and student-scale base size"
        ),
    },
    {
        "role": "independent_audit_encoder",
        "model_id": "sentence-transformers/distiluse-base-multilingual-cased-v2",
        "revision": "bfe45d0732ca50787611c0fe107ba278c7f3f889",
        "license": "Apache-2.0",
        "architecture_family": "multilingual DistilBERT distilled sentence encoder",
        "dimension": 512,
        "max_tokens": 128,
        "input_prefix": "",
        "tokenizer_id": "sentence-transformers/distiluse-base-multilingual-cased-v2",
        "tokenizer_revision": "bfe45d0732ca50787611c0fe107ba278c7f3f889",
        "pooling": "attention-mask mean pooling then Dense(768,512,bias=True,Tanh)",
        "output_layer": "last_hidden_state followed by pinned sentence-transformers Dense module",
        "weight_files": {
            "model.safetensors": {
                "size_bytes": 538_947_416,
                "sha256": "e8c2aed21297045330bd7c36ad1fee2ca8a7c527ac94cf19d20c3dd2bee564d7",
            },
            "2_Dense/model.safetensors": {
                "size_bytes": 1_575_104,
                "sha256": "0a21b1ce908e772ebf09f93c20ca09524c32706e9918d9c0169a3f0663b191ed",
            },
        },
        "selection_basis": (
            "predeclared low-cost independent architecture/training family, Chinese/English support, "
            "local pinned weights and Apache-2.0 license; audit only, with length-stratified reporting"
        ),
    },
)

DOWNLOAD_PATTERNS = (
    "config.json",
    "config_sentence_transformers.json",
    "modules.json",
    "sentence_bert_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "sentencepiece.bpe.model",
    "model.safetensors",
    "1_Pooling/*",
    "2_Dense/*",
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def vector_sha256(vector: np.ndarray) -> str:
    digest = hashlib.sha256()
    for value in vector.astype(np.float32, copy=False):
        if not math.isfinite(float(value)):
            raise RuntimeError("encoder produced NaN or Inf")
        digest.update(struct.pack("<f", float(value)))
    return digest.hexdigest()


def fixed_inputs() -> list[tuple[str, str]]:
    return [
        ("zh_equivalent_a", "已认证企业版账户自2026年3月起，每月额度为3000元。"),
        ("zh_equivalent_b", "从2026年3月开始，认证企业账户的月度限额是3000元。"),
        ("zh_numeric_conflict", "已认证企业版账户自2026年3月起，每月额度为1000元。"),
        ("zh_negation_conflict", "已认证企业版账户在2026年3月后仍不能使用该额度。"),
        ("en_equivalent_a", "Verified enterprise accounts have a monthly limit of 3000 after March 2026."),
        ("en_equivalent_b", "From March 2026, an authenticated enterprise account is capped at 3000 per month."),
        ("en_conflict", "Verified enterprise accounts have a monthly limit of 1000 after March 2026."),
        ("identifier", "订单 ABC-2025 的最终退款截止日期是 2026-03-31。"),
        ("unrelated", "海豚通过回声定位感知水下环境。"),
    ]


def normalize_probe_text(value: str) -> str:
    """Use the production measurement primitive without installing this project."""

    repository_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository_root / "src"))
    from linkrag_eval.robust_fusion.similarity import normalize_similarity_text

    return normalize_similarity_text(value)


def verify_weight_files(snapshot: Path, model_spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relative, expected in model_spec["weight_files"].items():
        path = snapshot / relative
        if not path.is_file():
            raise RuntimeError(f"missing pinned weight file: {model_spec['model_id']}:{relative}")
        actual_size = path.stat().st_size
        actual_sha = sha256_file(path)
        if actual_size != expected["size_bytes"] or actual_sha != expected["sha256"]:
            raise RuntimeError(
                f"weight drift: {model_spec['model_id']}:{relative}: "
                f"{actual_size}/{actual_sha}"
            )
        rows.append(
            {
                "relative_path": relative,
                "size_bytes": actual_size,
                "sha256": actual_sha,
            }
        )
    return rows


def metadata_files(snapshot: Path) -> list[dict[str, Any]]:
    names = (
        "modules.json",
        "config.json",
        "sentence_bert_config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "sentencepiece.bpe.model",
        "1_Pooling/config.json",
        "2_Dense/config.json",
    )
    return [
        {
            "relative_path": relative,
            "size_bytes": (snapshot / relative).stat().st_size,
            "sha256": sha256_file(snapshot / relative),
        }
        for relative in names
        if (snapshot / relative).is_file()
    ]


def qualify_model(model_spec: dict[str, Any], cache_dir: Path) -> dict[str, Any]:
    snapshot = Path(
        snapshot_download(
            repo_id=model_spec["model_id"],
            revision=model_spec["revision"],
            cache_dir=cache_dir,
            allow_patterns=list(DOWNLOAD_PATTERNS),
        )
    )
    weights = verify_weight_files(snapshot, model_spec)
    model = SentenceTransformer(str(snapshot), device="cpu", trust_remote_code=False)
    if model.max_seq_length != model_spec["max_tokens"]:
        raise RuntimeError(
            f"max token drift: {model_spec['model_id']}: "
            f"{model.max_seq_length} != {model_spec['max_tokens']}"
        )

    inputs = fixed_inputs()
    normalized_inputs = [
        model_spec["input_prefix"] + normalize_probe_text(text) for _, text in inputs
    ]
    token_counts = [
        len(
            model.tokenizer(
                text,
                add_special_tokens=True,
                truncation=False,
            )["input_ids"]
        )
        for text in normalized_inputs
    ]

    started = time.perf_counter()
    first = model.encode(
        normalized_inputs,
        batch_size=len(inputs),
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).astype(np.float32, copy=False)
    first_seconds = time.perf_counter() - started
    started = time.perf_counter()
    reversed_vectors = model.encode(
        list(reversed(normalized_inputs)),
        batch_size=len(inputs),
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).astype(np.float32, copy=False)
    replay_seconds = time.perf_counter() - started
    second = np.flip(reversed_vectors, axis=0)

    expected_shape = (len(inputs), model_spec["dimension"])
    if first.shape != expected_shape or second.shape != expected_shape:
        raise RuntimeError(
            f"embedding shape drift: {model_spec['model_id']}: "
            f"{first.shape}/{second.shape} != {expected_shape}"
        )
    norms = np.linalg.norm(first.astype(np.float64), axis=1)
    if not np.allclose(norms, 1.0, atol=1e-5, rtol=0.0):
        raise RuntimeError(f"non-unit embeddings: {model_spec['model_id']}: {norms.tolist()}")

    vector_rows = []
    for index, ((probe_id, text), left, right) in enumerate(zip(inputs, first, second)):
        left_hash = vector_sha256(left)
        right_hash = vector_sha256(right)
        if left_hash != right_hash:
            max_abs = float(np.max(np.abs(left.astype(np.float64) - right.astype(np.float64))))
            raise RuntimeError(
                f"order/replay vector drift: {model_spec['model_id']}:{probe_id}: {max_abs}"
            )
        vector_rows.append(
            {
                "probe_id": probe_id,
                "raw_input_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "normalized_input_sha256": hashlib.sha256(
                    normalized_inputs[index].encode("utf-8")
                ).hexdigest(),
                "untruncated_token_count": token_counts[index],
                "vector_float32_sha256": left_hash,
                "l2_norm_float64": float(norms[index]),
            }
        )

    by_id = {probe_id: index for index, (probe_id, _) in enumerate(inputs)}
    predetermined_pairs = (
        ("zh_equivalent_a", "zh_equivalent_b"),
        ("zh_equivalent_a", "zh_numeric_conflict"),
        ("zh_equivalent_a", "zh_negation_conflict"),
        ("en_equivalent_a", "en_equivalent_b"),
        ("en_equivalent_a", "en_conflict"),
        ("zh_equivalent_a", "unrelated"),
    )
    cosine_rows = []
    for left_id, right_id in predetermined_pairs:
        value = float(
            np.dot(
                first[by_id[left_id]].astype(np.float64),
                first[by_id[right_id]].astype(np.float64),
            )
        )
        if not -1.000001 <= value <= 1.000001:
            raise RuntimeError(f"cosine out of range: {model_spec['model_id']}:{value}")
        cosine_rows.append({"left": left_id, "right": right_id, "cosine_float64": value})

    truncation_side = model.tokenizer.truncation_side
    del model
    return {
        **model_spec,
        "local_snapshot_identity": model_spec["revision"],
        "weight_files_verified": weights,
        "metadata_files": metadata_files(snapshot),
        "l2_normalize": True,
        "pre_normalization_dtype": "float32",
        "stored_dtype": "float32",
        "cosine_accumulation_dtype": "float64",
        "device_class": "cpu",
        "input_contract": {
            "unicode_normalization": "NFKC",
            "html_policy": "unescape; BR/IMG/tag to text-space",
            "whitespace_policy": "Unicode whitespace collapse then strip",
            "truncation_side": truncation_side,
            "add_special_tokens": True,
            "max_tokens": model_spec["max_tokens"],
            "query_or_passage_prefix": model_spec["input_prefix"],
        },
        "probe_vectors": vector_rows,
        "predetermined_cosine_checks": cosine_rows,
        "timing_seconds": {
            "first_batch": first_seconds,
            "reverse_order_replay_batch": replay_seconds,
            "batch_size": len(inputs),
        },
        "qualification_status": "PASS",
    }


def build(cache_dir: Path) -> dict[str, Any]:
    torch.manual_seed(0)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    qualified = [qualify_model(model_spec, cache_dir) for model_spec in MODELS]
    if qualified[0]["architecture_family"] == qualified[1]["architecture_family"]:
        raise RuntimeError("main and audit encoder families are not independent")
    return {
        "artifact_version": ARTIFACT_VERSION,
        "scientific_protocol": SCIENTIFIC_PROTOCOL,
        "similarity_manifest": SIMILARITY_MANIFEST,
        "status": "QUALIFIED_PRESELECTED_PENDING_DEV_CALIBRATION",
        "gate_a_executed": False,
        "outcome_data_read": False,
        "selection_fixed_before_probe": True,
        "bge_m3": "RETIRED_FORBIDDEN",
        "models": qualified,
        "implementation": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "sentence_transformers": sentence_transformers.__version__,
            "transformers": transformers.__version__,
            "torch": torch.__version__,
            "numpy": np.__version__,
            "deterministic_algorithms": True,
            "torch_num_threads": torch.get_num_threads(),
        },
        "rejected_before_probe": [
            {
                "model_id": "Alibaba-NLP/gte-multilingual-base",
                "reason": "requires custom remote code and adds avoidable code-identity risk",
            },
            {
                "model_id": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
                "reason": "128-token audit ceiling at roughly main-model storage cost",
            },
            {
                "model_id": "sentence-transformers/LaBSE",
                "reason": "larger 1.88 GB main weight; unnecessary for the low-cost audit role",
            },
        ],
        "remaining_hard_gates": [
            "verify the frozen Qwen/Jina Reranker manifest shares neither encoder artifact",
            "run length-stratified independent-encoder and blinded-human similarity audit on Dev",
            "freeze per-dataset standardization, common support, coverage and bands on Dev",
            "seal reference-set membership, normalized input hashes, vector hashes and code/config hashes",
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
        default=Path("runs/robust_fusion/contracts/similarity-encoder-qualification-v3"),
    )
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    cache_dir = args.cache_dir if args.cache_dir.is_absolute() else repository_root / args.cache_dir
    output_root = (
        args.output_root
        if args.output_root.is_absolute()
        else repository_root / args.output_root
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
    primitive_path = repository_root / "src/linkrag_eval/robust_fusion/similarity.py"
    report["measurement_primitive"] = {
        "relative_path": str(primitive_path.relative_to(repository_root)),
        "sha256": sha256_file(primitive_path),
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
