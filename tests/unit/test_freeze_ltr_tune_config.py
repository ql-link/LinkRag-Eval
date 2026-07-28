from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "freeze_ltr_tune_config", ROOT / "scripts/freeze_ltr_tune_config.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_freeze_config_uses_median_iteration_and_tune_predictions(monkeypatch) -> None:
    monkeypatch.setattr(
        MODULE,
        "tune_hybrid_protection",
        lambda _predictions: {
            "best": {"blend_alpha": 0.75, "protect_baseline_top_k": 2},
            "results": [],
        },
    )
    config = MODULE.freeze_config(
        {
            "feature_version": "v2",
            "fold_reports": [
                {"best_iteration": 5},
                {"best_iteration": 20},
                {"best_iteration": 30},
            ],
            "predictions": [{"sample_id": "q1"}],
        },
        seed=7,
    )

    assert config["n_estimators"] == 20
    assert config["blend_alpha"] == 0.75
    assert config["protect_baseline_top_k"] == 2
    assert config["selection_source"] == "Tune OOF only"
