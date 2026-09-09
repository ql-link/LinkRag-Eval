"""Training eligibility must follow current within-query information, before any fit."""
from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from linkrag_eval.retrieval.learning_to_rank.subject_binding import (
    REPAIRED_RULE_VERSION,
    training_signal_gate,
)


def signal(loose=None, sentence=None, entity=None, **flags):
    return {"loose": loose, "sentence": sentence, "entity": entity,
            "query_structure_supported": int(loose is not None), "extraction_incomplete": 1,
            "availability": "available" if loose is not None else "query_unsupported", **flags}


@pytest.mark.parametrize("pools,reason", [
    ({"a": [signal(), signal()], "b": [signal(0, 0, 0), signal(0, 0, 0)]},
     "no_within_query_numeric_contrast"),
    ({"a": [signal(), signal(0, 0, 0)]}, "no_within_query_numeric_contrast"),
    ({"a": [signal(.5, .5, .5), signal(1, 1, 1)]}, "no_within_query_aggregation_contrast"),
    ({"a": [signal(.4, .1, .1), signal(.5, .2, .2)]}, "no_within_query_aggregation_contrast"),
])
def test_flags_missingness_and_identical_aggregations_do_not_admit_training(pools, reason):
    result = training_signal_gate(pools)
    assert not result["allowed"] and result["stop_reason"] == reason


def test_within_query_aggregation_contrast_allows_training_without_labels():
    result = training_signal_gate({"q": [signal(1, 1, .5), signal(1, .5, 1)]})
    assert result["allowed"]
    assert result["numeric_contrast_queries"] == result["aggregation_contrast_queries"] == ["q"]


def test_basic_matching_does_not_require_binding_difference():
    pools = {"q": [signal(1, 1, 1), signal(.5, .5, .5)]}
    assert training_signal_gate(pools, purpose="basic_matching")["allowed"]
    assert not training_signal_gate(pools, purpose="binding")["allowed"]
    assert not training_signal_gate({"q": [signal(), signal(0, 0, 0)]}, purpose="basic_matching")["allowed"]
    with pytest.raises(ValueError, match="purpose"):
        training_signal_gate(pools, purpose="disable_checks")


@pytest.mark.parametrize("row", [signal(1, None, 1), signal(float("nan"), 1, 1),
                                  signal(1, 1, 1, query_structure_supported=0)])
def test_invalid_numeric_signals_cannot_admit_training(row):
    with pytest.raises(ValueError, match="invalid numeric"):
        training_signal_gate({"q": [row]})


def test_actual_training_entry_stops_before_fit_when_only_background_varies(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    runner = importlib.import_module("subject_binding_training")
    monkeypatch.setattr(runner, "rules_from_config", lambda _: REPAIRED_RULE_VERSION)
    params = runner.training_parameters(runner.GRID[0])
    old = {"seed": runner.SEED, "maximum_iterations_per_fit": runner.MAX_ITERATIONS,
           "patience": runner.PATIENCE, "grid": [{"config_id": "fixed", "params": params}],
           "selected_config_id": "fixed",
           "versions": {"numpy": runner.importlib.metadata.version("numpy")},
           "train": {}, "development": {}}
    monkeypatch.setattr(runner, "read_json", lambda _: old)
    query = SimpleNamespace(query_id="q", selected_indices=[0, 1])
    dataset = SimpleNamespace(queries=[query], blocks=[query], summary={})
    monkeypatch.setattr(runner, "load_dataset", lambda **_: dataset)
    monkeypatch.setattr(runner, "assert_disjoint_roles", lambda *_: None)
    pools = {"q": [signal(0, 0, 0), signal(0, 0, 0), signal(1, 1, .5)]}
    received_versions = []

    def compute_current_scores(*args, rules_version):
        received_versions.append(rules_version)
        assert rules_version == REPAIRED_RULE_VERSION
        return pools, {}

    monkeypatch.setattr(runner, "compute_scores", compute_current_scores)

    def forbidden(*args, **kwargs):
        pytest.fail("fit called before current supervised contrast gate")

    monkeypatch.setattr(runner, "train_and_select", forbidden)
    monkeypatch.setattr(runner, "fit_arm", forbidden)
    out = tmp_path / "run"
    runner.run({"english_selection": "unused", "config_id": runner.GRID[0]["config_id"],
                "inputs": {"train": {}, "development": {}}}, tmp_path / "cache", out)
    saved = json.loads((out / "results.json").read_text())
    assert saved["status"] == "stopped_before_fit" and saved["arms"] == {}
    assert saved["training_signal_gates"]["development_full_pools"]["allowed"]
    assert not saved["training_signal_gates"]["train_supervised_rows"]["allowed"]
    assert not (out / "E0").exists()
    assert received_versions == [REPAIRED_RULE_VERSION, REPAIRED_RULE_VERSION]
    assert saved["rules_version"] == REPAIRED_RULE_VERSION
