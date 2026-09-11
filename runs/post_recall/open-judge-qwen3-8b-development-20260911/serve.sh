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
  /workspace/hf/hub/models--Qwen--Qwen3-8B/snapshots/b968826d9c46dd6066d109eabc6255188de91218 \
  --served-model-name qwen3-8b --host 127.0.0.1 --port 8000 \
  --dtype bfloat16 --max-model-len 8192 --gpu-memory-utilization 0.90 \
  --reasoning-parser qwen3 --seed 0
