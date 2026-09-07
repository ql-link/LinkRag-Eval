"""Saved English predictions must match identities, raw scores and official direction."""
from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location("english_diagnostic", Path(__file__).parents[2] / "scripts/nevir_english_diagnostics.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


def _fixture():
    row = {"source_query_id": "q", "source_group_id": "g", "pair_id": "p", "direction": "q1",
           "official_label_available": True, "structural_conflict": False,
           "semantic_uncertain": False, "semantic_review_status": "not_semantically_reviewed",
           "candidate_count": 3, "preferred_chunk_id": "preferred", "other_chunk_id": "other"}
    scores = np.array([1.0, np.nextafter(1.0, 2.0), -1.0])
    ids = ["other", "preferred", "background"]
    saved = {**row, "scores": [{"chunk_id": cid, "score": float(score)} for cid, score in zip(ids, scores, strict=True)],
             "order": ["preferred", "other", "background"], "preference_relation": "correct",
             "score_difference": float(scores[1]-scores[0])}
    return row, saved, ids, scores


def test_saved_prediction_preserves_full_pool_and_strict_near_tie():
    row, saved, ids, scores = _fixture()
    diagnostic._check_saved_prediction(row, saved, ids, scores)
    row["other_chunk_id"] = "missing"
    saved["preference_relation"] = "unavailable"
    diagnostic._check_saved_prediction(row, saved, ids, scores)


@pytest.mark.parametrize("corruption", ["association", "duplicate_candidate", "score", "direction", "order"])
def test_saved_prediction_mismatch_is_blocking(corruption):
    row, saved, ids, scores = _fixture()
    if corruption == "association":
        saved["source_group_id"] = "wrong-group"
    elif corruption == "duplicate_candidate":
        saved["scores"].append(deepcopy(saved["scores"][0]))
    elif corruption == "score":
        saved["scores"][2]["score"] = 0
    elif corruption == "direction":
        saved["preference_relation"] = "tie"
    elif corruption == "order":
        saved["order"][0], saved["order"][1] = saved["order"][1], saved["order"][0]
    with pytest.raises(ValueError):
        diagnostic._check_saved_prediction(row, saved, ids, scores)


def test_missing_inputs_record_exact_blocker_without_loading_a_model(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("model loading must not run with missing input")

    monkeypatch.setattr(diagnostic, "validate_production_bundle", forbidden)
    out = tmp_path / "output"
    with pytest.raises(FileNotFoundError, match="missing required local input"):
        diagnostic.run(experiment_dir=tmp_path / "missing-experiment", model_a=tmp_path / "missing-a",
                       model_english=tmp_path / "missing-en", saved_english_predictions=tmp_path / "missing-predictions",
                       previous_diagnostic=tmp_path / "missing-prior", out=out)
    result = json.loads((out / "manifest.json").read_text())
    assert result["status"] == result["mechanical_status"] == "blocked"
    assert "missing-experiment" in result["blocker"]["detail"]
    assert result["boundary"]["fits"] == result["boundary"]["remote_calls"] == 0
