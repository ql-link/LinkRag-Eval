"""Check the deployed transport and schema on three synthetic, non-NevIR inputs."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[2]


def main():
    config = json.loads((FOLDER / "frozen-config.json").read_text())
    spec = importlib.util.spec_from_file_location("strict_driver", ROOT / config["experiment_driver"])
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    settings = config["judge_arguments"]
    runner = driver.SingleRequestRunner(
        settings["endpoint"], config["model"]["served_name"], think=settings["think"],
        max_tokens=settings["max_tokens"], num_ctx=settings["num_ctx"],
        timeout=settings["timeout_seconds"],
    )
    examples = [
        ("Where is the brass key?", "The brass key is inside the green box in the attic."),
        ("When does the fictional garden open?", "The fictional garden opens at nine each morning."),
        ("Which drawer contains a wooden spoon?", "A wooden spoon is kept in the second drawer."),
    ]
    items = [
        {"source_query_id": f"synthetic-{i}", "chunk_id": f"synthetic-passage-{i}",
         "pair_id": f"synthetic-pair-{i}", "query": query, "passage": passage,
         "level": "engineering-smoke"}
        for i, (query, passage) in enumerate(examples, 1)
    ]
    summary = driver.single_pass(
        items, runner, FOLDER / "synthetic-smoke", workers=settings["workers"],
        seed=settings["batch_shuffle_seed"],
    )
    print(json.dumps(summary))
    if summary["unavailable"]:
        raise RuntimeError("Synthetic smoke failed; retain artifacts and do not start Test")


if __name__ == "__main__":
    main()
