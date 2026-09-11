"""Three synthetic transport/schema checks, excluded from evaluation caches."""

import argparse
import json
from pathlib import Path

import httpx
from run_frozen import SingleRequestRunner, single_pass, utcnow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    settings = config["judge_arguments"]
    items = [{"source_query_id": f"synthetic-{i}", "chunk_id": f"synthetic-passage-{i}",
              "pair_id": f"synthetic-pair-{i}", "query": query, "passage": passage,
              "level": "l1", "prompt_version": settings["prompt_version"],
              "model": None, "effort": None, "codex_version": None}
             for i, (query, passage) in enumerate([
                 ("What color is the test beacon?", "The test beacon is blue."),
                 ("When does the test library open?", "The test library opens at nine."),
                 ("Which key opens the test cabinet?", "The brass key opens the test cabinet."),
             ], 1)]
    with httpx.Client(timeout=15, trust_env=False) as client:
        response = client.get(settings["endpoint"].rstrip("/") + "/v1/models")
        response.raise_for_status()
        served = response.json()
    assert config["model"]["served_name"] in {x["id"] for x in served["data"]}
    runner = SingleRequestRunner(settings["endpoint"], config["model"]["served_name"],
                                 think=settings["think"], max_tokens=settings["max_tokens"],
                                 num_ctx=settings["num_ctx"], timeout=settings["timeout_seconds"])
    summary = single_pass(items, runner, args.config.parent / "engineering-smoke",
                          workers=3, seed=settings["batch_shuffle_seed"])
    with (args.config.parent / "runtime-check.json").open("x") as stream:
        json.dump({"recorded_at": utcnow(), "served_models": served,
                   "smoke": summary, "scope": config["engineering_smoke"]["scope"]},
                  stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    assert summary["unavailable"] == 0, "Synthetic schema/transport smoke failed"


if __name__ == "__main__":
    main()
