"""Strict offline-only 41-column pilot bundles; production 38-column loaders stay unchanged."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from linkrag_eval.retrieval.learning_to_rank.features import (
    ENGLISH_FEATURE_VERSION,
    FEATURE_NAMES,
    rules_version,
)
from linkrag_eval.retrieval.learning_to_rank.subject_binding import parser_contract, text_hash

PILOT_VERSION = "candidate_difference_v3_en_subject_binding_v1"
SHARED_FLAGS = ("query_structure_supported", "extraction_incomplete")
ARM_SCORES = {"EM": "constant_zero", "E1": "loose", "E2": "sentence", "E3": "entity"}


def contract(arm):
    if arm not in ARM_SCORES:
        raise ValueError("unknown pilot arm")
    return {"feature_version": PILOT_VERSION, "base_feature_version": ENGLISH_FEATURE_VERSION,
            "base_rules_version": rules_version(ENGLISH_FEATURE_VERSION), "parser": parser_contract(),
            "arm": arm, "score": ARM_SCORES[arm], "shared_flags": list(SHARED_FLAGS),
            "feature_names": [*FEATURE_NAMES, *SHARED_FLAGS, "condition_support"],
            "missing_value": "NaN; common availability for loose/sentence/entity; EM last column always zero",
            "dtype": "float32", "candidate_scope": "complete saved pool before supervised row selection"}


def augment(base, rows, *, arm, base_feature_version):
    schema = contract(arm)
    if base_feature_version != ENGLISH_FEATURE_VERSION:
        raise ValueError("pilot augmentation requires the explicit English feature contract")
    if base.shape != (len(rows), len(FEATURE_NAMES)) or not np.isfinite(base).all():
        raise ValueError("expected complete English38 base matrix")
    extras = np.asarray([[r[k] for k in SHARED_FLAGS] + [0.0 if arm == "EM" else r[ARM_SCORES[arm]]]
                         for r in rows], dtype=np.float32)
    if not np.isin(extras[:, :2], [0, 1]).all():
        raise ValueError("invalid shared flags")
    result = np.concatenate([base, extras], axis=1)
    if result.shape[1] != len(schema["feature_names"]) or np.isinf(result).any():
        raise ValueError("invalid pilot feature matrix")
    return result


def save_bundle(path: Path, model_text: str, *, arm: str, fit: dict):
    import lightgbm as lgb
    path.mkdir(parents=True, exist_ok=False)
    schema = contract(arm)
    booster = lgb.Booster(model_str=model_text)
    if booster.feature_name() != schema["feature_names"]:
        raise ValueError("trained feature order differs from bundle contract")
    (path / "model.txt").write_text(model_text)
    manifest = {"format": "subject_binding_offline_lgbm_v1", "contract": schema,
                "model_sha256": text_hash(model_text), "lightgbm_version": lgb.__version__,
                "actual_trees": booster.num_trees(), "fit": fit}
    (path / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


class OfflineBindingModel:
    def __init__(self, path: Path, *, expected_contract: dict):
        import lightgbm as lgb
        saved = json.loads((path / "manifest.json").read_text())
        if (saved.get("format") != "subject_binding_offline_lgbm_v1"
                or saved.get("contract") != expected_contract
                or expected_contract != contract(expected_contract.get("arm"))):
            raise ValueError("offline pilot model feature/version contract mismatch")
        content = (path / "model.txt").read_text()
        if saved["model_sha256"] != text_hash(content) or saved["lightgbm_version"] != lgb.__version__:
            raise ValueError("offline pilot model integrity/runtime mismatch")
        self.schema = expected_contract
        self.booster = lgb.Booster(model_str=content)
        if self.booster.feature_name() != expected_contract["feature_names"]:
            raise ValueError("offline pilot model column order mismatch")

    def predict(self, features, *, feature_contract: dict):
        if feature_contract != self.schema or features.shape[1] != len(self.schema["feature_names"]):
            raise ValueError("offline prediction feature/version contract mismatch")
        if np.isinf(features).any():
            raise ValueError("infinite pilot input")
        return self.booster.predict(features, num_threads=1)
