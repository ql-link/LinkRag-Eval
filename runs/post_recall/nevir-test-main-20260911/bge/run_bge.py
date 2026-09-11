"""Run the fixed BGE comparison on the configured GPU; no training or retrieval."""
from __future__ import annotations

import json
import math
import time
from collections import Counter
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


def main():
    started = time.perf_counter()
    root = Path(__file__).resolve().parent
    config = json.loads((root / "execution-config.json").read_text())
    output = root / "scores.jsonl"
    partial = root / "scores.partial.jsonl"
    if any(path.exists() for path in (output, partial, root / "summary.json")):
        raise FileExistsError("refusing to overwrite BGE output")
    rows = [json.loads(line) for line in (root / "items.jsonl").read_text().splitlines()]
    keys = {(r["role"], r["source_query_id"], r["chunk_id"]) for r in rows}
    if len(rows) != config["unique_role_query_passage_items"] or len(keys) != len(rows):
        raise ValueError("BGE item count or unique keys differ from fixed config")
    if {r["role"] for r in rows} != {"test"}:
        raise ValueError("only the frozen Test role is allowed")
    runtime = config["runtime"]
    for package in ("torch", "transformers"):
        if version(package) != runtime[package]:
            raise ValueError(f"{package} version differs from fixed config")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for this run")
    torch.manual_seed(runtime["seed"])
    torch.set_num_threads(4)
    torch.cuda.set_per_process_memory_fraction(runtime["gpu_memory_fraction_limit"], 0)
    torch.backends.cuda.matmul.allow_tf32 = False
    revision = config["model"]["revision"]
    model_path = Path(runtime["model_path"])
    if model_path.name != revision:
        raise ValueError("BGE model directory differs from the fixed revision")
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    encoded = tokenizer([r["query"] for r in rows], [r["passage"] for r in rows],
                        padding=False, truncation=False)
    lengths = [len(value) for value in encoded["input_ids"]]
    if max(lengths) > runtime["max_input_tokens"]:
        raise ValueError("input exceeds fixed token limit; no silent truncation allowed")
    model = AutoModelForSequenceClassification.from_pretrained(
        model_path, local_files_only=True, dtype=torch.float16,
        attn_implementation=runtime["attention_implementation"],
    ).to("cuda").eval()
    torch.cuda.synchronize()
    inference_started = time.perf_counter()
    print(json.dumps({"status": "scoring", "items": len(rows),
                      "max_input_tokens_observed": max(lengths)}), flush=True)
    with partial.open("x") as stream, torch.inference_mode():
        batch_size = runtime["batch_size"]
        for offset in range(0, len(rows), batch_size):
            batch_rows = rows[offset:offset + batch_size]
            features = [{key: values[i] for key, values in encoded.items()}
                        for i in range(offset, offset + len(batch_rows))]
            batch = tokenizer.pad(features, padding=True, return_tensors="pt").to("cuda")
            scores = model(**batch, return_dict=True).logits.reshape(-1).float().cpu().tolist()
            if len(scores) != len(batch_rows) or not all(math.isfinite(s) for s in scores):
                raise ValueError("BGE returned invalid score count or non-finite logits")
            for row, score in zip(batch_rows, scores, strict=True):
                record = {key: row[key] for key in
                          ("role", "source_query_id", "chunk_id", "levels")}
                record.update(score=score, status="available", model=config["model"]["repository"],
                              revision=revision, dtype="float16")
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            if (offset + len(batch_rows)) % 250 == 0:
                stream.flush()
                print(json.dumps({"completed": offset + len(batch_rows),
                                  "total": len(rows)}), flush=True)
    torch.cuda.synchronize()
    inference_seconds = time.perf_counter() - inference_started
    partial.rename(output)
    summary = {
        "status": "completed", "completed_at": datetime.now(UTC).isoformat(),
        "model": config["model"], "runtime": runtime, "items": len(rows),
        "items_by_role": dict(Counter(r["role"] for r in rows)), "unavailable": 0,
        "input_tokens": {"min": min(lengths), "max": max(lengths),
                         "mean": sum(lengths) / len(lengths), "truncated_items": 0},
        "gpu": torch.cuda.get_device_name(0),
        "peak_cuda_allocated_bytes": torch.cuda.max_memory_allocated(0),
        "inference_wall_seconds": inference_seconds,
        "total_wall_seconds": time.perf_counter() - started,
        "timing_scope": "Total includes input loading, tokenization, model loading and inference; "
                        "excludes imports, model download and SSH file transfers. "
                        "Inference includes GPU work and incremental output serialization.",
    }
    (root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
