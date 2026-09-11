#!/usr/bin/env bash
set -euo pipefail
export HF_HOME=/workspace/hf
export TMPDIR=/workspace/tmp
export VLLM_CACHE_ROOT=/workspace/vllm-cache
export OUTLINES_CACHE_DIR=/workspace/vllm-cache/outlines
export XDG_CACHE_HOME=/workspace/.cache
export VLLM_USE_FLASHINFER_SAMPLER=0
mkdir -p "$TMPDIR" "$VLLM_CACHE_ROOT" "$OUTLINES_CACHE_DIR" "$XDG_CACHE_HOME"
exec /workspace/venv/bin/vllm serve \
  /workspace/hf/hub/models--Qwen--Qwen3-14B-AWQ/snapshots/31c69efc29464b6bb0aee1398b5a7b50a99340c3 \
  --served-model-name qwen3-14b-awq --host 127.0.0.1 --port 8000 \
  --quantization awq_marlin --max-model-len 8192 --gpu-memory-utilization 0.90 \
  --reasoning-parser qwen3 --seed 0
