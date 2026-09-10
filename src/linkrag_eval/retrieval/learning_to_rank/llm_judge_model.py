"""Strict offline English38 + judge availability/score bundles for the fixed top-K pilot."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from .features import ENGLISH_FEATURE_VERSION, FEATURE_NAMES, rules_version
from .llm_judge import PROMPT_VERSION, STAGE1_FEATURE, check_judged_scope, write_json

PILOT_VERSION = "candidate_difference_v3_en_llm_judge_v2"


def contract(*, model, effort="low", top_k=20):
    if not isinstance(model, str) or not model or effort not in {"low", "medium"}:
        raise ValueError("invalid judge model/effort contract")
    if type(top_k) is not int or top_k < 1:
        raise ValueError("invalid top K contract")
    return {"feature_version": PILOT_VERSION, "base_feature_version": ENGLISH_FEATURE_VERSION,
            "base_rules_version": rules_version(ENGLISH_FEATURE_VERSION),
            "feature_names": [*FEATURE_NAMES, "judge_available", "judge_score"],
            "prompt_version": PROMPT_VERSION, "model": model, "effort": effort, "top_k": top_k,
            "stage1_feature": STAGE1_FEATURE,
            "dtype": "float32", "missing_value": "judge_available=0; judge_score=NaN",
            "candidate_scope": "fixed hybrid stage1 top K only, in training and inference; full-pool base features"}


def validate_contract(schema):
    if schema != contract(**{k: schema.get(k) for k in ("model", "effort", "top_k")}):
        raise ValueError("judge feature/version contract mismatch")


def validate_matrix(features):
    if features.ndim != 2 or features.shape[1] != len(FEATURE_NAMES) + 2:
        raise ValueError("judge column contract mismatch")
    if features.dtype != np.float32 or not np.isfinite(features[:, :38]).all():
        raise ValueError("expected finite float32 English38 base")
    available, score = features[:, -2], features[:, -1]
    if (not np.isin(available, [0, 1]).all() or
            not np.isnan(score[available == 0]).all() or
            not np.isin(score[available == 1], range(5)).all()):
        raise ValueError("invalid judge availability/score matrix")


def augment(base, chunk_ids, stage1, judged, *, base_feature_version, feature_contract):
    validate_contract(feature_contract)
    if base_feature_version != ENGLISH_FEATURE_VERSION:
        raise ValueError("judge augmentation requires English feature contract")
    if base.shape != (len(chunk_ids), len(FEATURE_NAMES)) or len(set(chunk_ids)) != len(chunk_ids):
        raise ValueError("expected complete English38 matrix with unique candidates")
    if set(stage1) != set(chunk_ids) or not np.isfinite(list(stage1.values())).all():
        raise ValueError("stage1 must cover complete candidate pool")
    if not np.array_equal(base[:, FEATURE_NAMES.index(STAGE1_FEATURE)], [stage1[cid] for cid in chunk_ids]):
        raise ValueError("stage1 scores differ from the English baseline_score feature column")
    selected = check_judged_scope({"query": judged}, {"query": stage1}, top_k=feature_contract["top_k"])["query"]
    extras = []
    for cid in chunk_ids:
        score = selected.get(cid)
        if score is not None and (type(score) is not int or not 0 <= score <= 4):
            raise ValueError("invalid pointwise judge score")
        extras.append([int(score is not None), np.nan if score is None else score])
    result = np.concatenate([base, np.asarray(extras, dtype=np.float32).reshape(-1, 2)], axis=1)
    validate_matrix(result)
    return result


def augmented_dataset(dataset, stage1, judged, *, feature_contract):
    if set(stage1) != {q.query_id for q in dataset.queries} or not set(judged) <= set(stage1):
        raise ValueError("augmentation query population mismatch")
    queries = [replace(q, features=augment(q.features, q.chunk_ids, stage1[q.query_id],
                judged.get(q.query_id, {}), base_feature_version=dataset.feature_version,
                feature_contract=feature_contract)) for q in dataset.queries]
    blocks = [q for q in queries if not q.exclusion_reasons]
    return replace(dataset, queries=queries, blocks=blocks,
                   x=np.concatenate([q.features[q.selected_indices] for q in blocks]),
                   feature_version=PILOT_VERSION)


def judge_split_counts(booster):
    counts = dict(zip(booster.feature_name(), booster.feature_importance(importance_type="split"), strict=True))
    return {name: int(counts[name]) for name in ("judge_available", "judge_score")}


def save_bundle(path: Path, model_text: str, *, feature_contract, fit):
    import lightgbm as lgb
    validate_contract(feature_contract)
    booster = lgb.Booster(model_str=model_text)
    if booster.feature_name() != feature_contract["feature_names"]:
        raise ValueError("trained feature column order differs from contract")
    path.mkdir(parents=True, exist_ok=False)
    (path / "model.txt").write_text(model_text)
    manifest = {"format": "llm_judge_offline_lgbm_v1", "contract": feature_contract,
                "model_sha256": hashlib.sha256(model_text.encode()).hexdigest(),
                "lightgbm_version": lgb.__version__, "actual_trees": booster.num_trees(), "fit": fit}
    write_json(path / "manifest.json", manifest)
    return manifest


class OfflineJudgeModel:
    def __init__(self, path: Path, *, expected_contract):
        import lightgbm as lgb
        validate_contract(expected_contract)
        manifest = json.loads((path / "manifest.json").read_text())
        if manifest.get("format") != "llm_judge_offline_lgbm_v1" or manifest.get("contract") != expected_contract:
            raise ValueError("offline judge model contract mismatch")
        text = (path / "model.txt").read_text()
        if (manifest["model_sha256"] != hashlib.sha256(text.encode()).hexdigest()
                or manifest["lightgbm_version"] != lgb.__version__):
            raise ValueError("offline judge model integrity/runtime mismatch")
        self.schema = expected_contract
        self.booster = lgb.Booster(model_str=text)
        if (self.booster.feature_name() != expected_contract["feature_names"]
                or self.booster.num_trees() != manifest["actual_trees"]):
            raise ValueError("offline judge model columns/tree count mismatch")

    def predict(self, features, *, feature_contract):
        if feature_contract != self.schema:
            raise ValueError("offline prediction contract mismatch")
        validate_matrix(features)
        return self.booster.predict(features, num_threads=1)
