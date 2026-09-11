"""Start the fixed Qwen service on the owner-provided replacement GPU."""

from __future__ import annotations

import argparse
import json
import os
from importlib.metadata import version
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    server = config["server"]
    for package in ("vllm", "torch", "transformers"):
        if version(package) != server[package]:
            raise ValueError(f"{package} differs from the fixed runtime")
    model = Path(server["model_path"])
    if not (model / "model.safetensors.index.json").is_file():
        raise FileNotFoundError("The pinned Qwen model is not available")
    data = Path(server["data_root"])
    runtime = Path(server["runtime_root"])
    if sum(p.stat().st_size for root in (data, runtime) for p in root.rglob("*")
           if p.is_file() and not p.is_symlink()) > config["storage"]["max_new_disk_bytes"]:
        raise RuntimeError("Task storage exceeds the owner's 35 GB budget")
    environment = {
        "HF_HOME": data / "hf",
        "TMPDIR": data / "tmp",
        "VLLM_CACHE_ROOT": data / "vllm-cache",
        "OUTLINES_CACHE_DIR": data / "vllm-cache/outlines",
        "XDG_CACHE_HOME": data / "cache",
    }
    for name, path in environment.items():
        path.mkdir(parents=True, exist_ok=True)
        os.environ[name] = str(path)
    os.environ["VLLM_USE_FLASHINFER_SAMPLER"] = "0"
    binary = Path(server["python"]).parent / "vllm"
    argv = [
        str(binary), "serve", str(model), "--served-model-name", config["model"]["served_name"],
        "--host", "127.0.0.1", "--port", "8000", "--quantization", config["model"]["format"],
        "--max-model-len", str(server["context_length"]),
        "--gpu-memory-utilization", str(server["gpu_memory_utilization"]),
        "--reasoning-parser", server["reasoning_parser"], "--seed", str(server["seed"]),
    ]
    os.execv(binary, argv)


if __name__ == "__main__":
    main()
