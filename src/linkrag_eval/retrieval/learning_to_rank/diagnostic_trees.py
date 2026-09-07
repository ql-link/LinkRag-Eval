"""Offline numeric LambdaMART paths, checked against the existing Booster.

Callers compute the complete candidate matrix first. This module only inspects
the two supplied rows; no features, model parameters, or labels are changed.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from linkrag_eval.retrieval.learning_to_rank.features import FEATURE_NAMES

RECONSTRUCTION_ATOL = 1e-10
RECONSTRUCTION_RTOL = 0.0


class TreeAuditError(ValueError):
    """Unsupported structure or failed reconstruction: do not explain this pair."""


def _number(value: Any, context: str) -> float:
    if isinstance(value, (bool, str)):
        raise TreeAuditError(f"{context}: expected a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise TreeAuditError(f"{context}: expected a finite number") from exc
    if not math.isfinite(result):
        raise TreeAuditError(f"{context}: expected a finite number")
    return result


def _close(actual: float, expected: float, context: str) -> float:
    error = abs(actual - expected)
    if not math.isfinite(error) or error > RECONSTRUCTION_ATOL:
        raise TreeAuditError(
            f"{context}: reconstruction error {error!r} exceeds atol={RECONSTRUCTION_ATOL}"
        )
    return error


def _leaf_index(node: dict, *, root: bool = False) -> int:
    # LightGBM omits leaf_index for a constant, single-leaf tree.
    value = node.get("leaf_index", 0 if root else None)
    if type(value) is not int or value < 0:
        raise TreeAuditError("Invalid leaf index")
    return value


def _validate_tree(tree: dict, index: int, width: int) -> None:
    if tree.get("tree_index") != index or type(tree.get("num_leaves")) is not int:
        raise TreeAuditError(f"Tree {index}: invalid tree index or leaf count")
    if tree.get("num_cat") != 0:
        raise TreeAuditError(f"Tree {index}: categorical trees are unsupported")
    if _number(tree.get("shrinkage"), f"Tree {index} shrinkage") < 0:
        raise TreeAuditError(f"Tree {index}: negative shrinkage")
    pending = [(tree.get("tree_structure"), True)]
    visited, split_ids, leaf_ids = set(), set(), set()
    while pending:
        node, root = pending.pop()
        if not isinstance(node, dict) or id(node) in visited:
            raise TreeAuditError(f"Tree {index}: invalid or repeated node")
        visited.add(id(node))
        if any(key in node for key in ("leaf_const", "leaf_features", "leaf_coeff")):
            raise TreeAuditError(f"Tree {index}: linear leaves are unsupported")
        if "split_index" not in node:
            if "left_child" in node or "right_child" in node:
                raise TreeAuditError(f"Tree {index}: leaf has children")
            leaf_id = _leaf_index(node, root=root)
            if leaf_id in leaf_ids:
                raise TreeAuditError(f"Tree {index}: duplicate leaf index")
            leaf_ids.add(leaf_id)
            _number(node.get("leaf_value"), f"Tree {index} leaf {leaf_id}")
            continue
        split_id = node["split_index"]
        if type(split_id) is not int or split_id < 0 or split_id in split_ids:
            raise TreeAuditError(f"Tree {index}: invalid or duplicate split index")
        split_ids.add(split_id)
        if "leaf_index" in node or "leaf_value" in node:
            raise TreeAuditError(f"Tree {index}: node is both split and leaf")
        feature = node.get("split_feature")
        if type(feature) is not int or not 0 <= feature < width:
            raise TreeAuditError(f"Tree {index}: invalid split feature")
        if node.get("decision_type") != "<=":
            raise TreeAuditError(f"Tree {index}: unsupported decision type")
        if node.get("missing_type") not in {"None", "NaN", "Zero"}:
            raise TreeAuditError(f"Tree {index}: unsupported missing type")
        if type(node.get("default_left")) is not bool:
            raise TreeAuditError(f"Tree {index}: invalid default_left")
        _number(node.get("threshold"), f"Tree {index} split {split_id} threshold")
        pending.extend((node.get(key), False) for key in ("left_child", "right_child"))
    if leaf_ids != set(range(tree["num_leaves"])):
        raise TreeAuditError(f"Tree {index}: leaf count or indices disagree")
    if split_ids != set(range(max(0, tree["num_leaves"] - 1))):
        raise TreeAuditError(f"Tree {index}: split count or indices disagree")


def _path(tree: dict, row: np.ndarray, names: list[str]) -> dict:
    # These rules match the installed lightgbm.plotting numeric split helper;
    # native pred_leaf subsequently checks every traversed path independently.
    from lightgbm.basic import ZERO_THRESHOLD

    path = []
    node = tree["tree_structure"]
    while "split_index" in node:
        feature = node["split_feature"]
        value = float(row[feature])
        is_nan = math.isnan(value)
        missing_type = node["missing_type"]
        comparison_value = 0.0 if is_nan and missing_type != "NaN" else value
        is_missing = (
            missing_type == "Zero" and abs(comparison_value) <= ZERO_THRESHOLD
        ) or (missing_type == "NaN" and math.isnan(comparison_value))
        left = node["default_left"] if is_missing else comparison_value <= node["threshold"]
        branch = "left" if left else "right"
        path.append({
            "split_index": node["split_index"],
            "feature_index": feature, "feature_name": names[feature],
            "decision_type": node["decision_type"], "threshold": float(node["threshold"]),
            "feature_value": None if is_nan else value, "value_is_nan": is_nan,
            "comparison_value": None if math.isnan(comparison_value) else comparison_value,
            "missing_type": missing_type, "is_missing": is_missing,
            "default_left": node["default_left"], "branch": branch,
        })
        node = node[f"{branch}_child"]
    return {"path": path, "leaf_index": _leaf_index(node, root=not path),
            "leaf_output": float(node["leaf_value"])}


def _strict_direction(preferred: float, other: float) -> str:
    return "preferred" if preferred > other else "other" if preferred < other else "tie"


def audit_pair(
    *, booster: Any, preferred_features: np.ndarray, other_features: np.ndarray,
    feature_names: list[str], preferred_score: float, other_score: float,
    label_basis: str = "official",
) -> dict:
    """Audit all existing trees, preserving strict raw-score preference.

    Absolute tolerance 1e-10 (rtol=0) is solely a reconstruction check. Equality
    of features uses exact element values and matching NaN locations. Tree leaf
    outputs already include shrinkage; multiplying them by shrinkage again is
    incorrect. A tree delta belongs to its two complete paths, not one feature.
    """
    if list(feature_names) != FEATURE_NAMES:
        raise TreeAuditError("Expected the exact candidate_difference_v3 38-column order")
    if not isinstance(label_basis, str) or not label_basis.strip():
        raise TreeAuditError("label_basis must identify the preference source")
    names = list(feature_names)
    rows = [np.asarray(value) for value in (preferred_features, other_features)]
    if any(row.shape != (len(names),) or row.dtype not in (np.float32, np.float64) for row in rows):
        raise TreeAuditError("Features must be two 38-value float32/float64 rows")
    if rows[0].dtype != rows[1].dtype or any(np.isinf(row).any() for row in rows):
        raise TreeAuditError("Feature dtypes must match and infinite values are unsupported")
    scores = [_number(preferred_score, "preferred_score"), _number(other_score, "other_score")]
    matrix = np.stack(rows)
    try:
        width, count = booster.num_feature(), booster.num_trees()
        if width != len(names) or type(count) is not int or count <= 0:
            raise TreeAuditError("Booster feature count or tree count is invalid")
        model_names = booster.feature_name()
        if model_names not in (names, [f"Column_{index}" for index in range(width)]):
            raise TreeAuditError("Booster column order is neither the schema nor legacy Column_N")
        dump = booster.dump_model(start_iteration=0, num_iteration=-1)
        if (dump.get("num_class") != 1 or dump.get("num_tree_per_iteration") != 1
                or booster.num_model_per_iteration() != 1 or dump.get("average_output") is not False
                or dump.get("objective") != "lambdarank"):
            raise TreeAuditError("Only scalar additive LambdaMART models are supported")
        if dump.get("feature_names") != model_names:
            raise TreeAuditError("Booster and dump column names disagree")
        trees = dump.get("tree_info")
        if not isinstance(trees, list) or len(trees) != count:
            raise TreeAuditError("All-tree dump does not match actual tree count")
        for index, tree in enumerate(trees):
            _validate_tree(tree, index, width)
        kwargs = {"start_iteration": 0, "num_iteration": -1, "num_threads": 1}
        native_leaves = np.asarray(booster.predict(matrix, pred_leaf=True, **kwargs))
        native_scores = np.asarray(booster.predict(matrix, raw_score=True, **kwargs))
        if native_leaves.shape != (2, count) or native_scores.shape != (2,):
            raise TreeAuditError("Unexpected native leaf/raw-score prediction shape")
        native_scores = [_number(value, "native raw score") for value in native_scores]
        supplied_errors = [_close(a, b, "Supplied versus native raw score")
                           for a, b in zip(scores, native_scores, strict=True)]
        if _strict_direction(*scores) != _strict_direction(*native_scores):
            raise TreeAuditError("Supplied and native scores have different strict preference")
        records, leaf_errors = [], []
        for index, tree in enumerate(trees):
            paths = [_path(tree, row, names) for row in rows]
            for position, path in enumerate(paths):
                native_leaf = native_leaves[position, index]
                if not np.isfinite(native_leaf) or native_leaf != path["leaf_index"]:
                    raise TreeAuditError(f"Tree {index}: traversed leaf differs from pred_leaf")
                native_output = _number(
                    booster.get_leaf_output(index, path["leaf_index"]),
                    f"Tree {index} get_leaf_output",
                )
                leaf_errors.append(_close(path["leaf_output"], native_output,
                                          f"Tree {index}: dump versus get_leaf_output"))
                path.update({"pred_leaf_index": int(native_leaf), "get_leaf_output": native_output})
            records.append({
                "tree_index": index, "shrinkage": float(tree["shrinkage"]),
                "preferred": paths[0], "other": paths[1],
                "delta": paths[0]["leaf_output"] - paths[1]["leaf_output"],
                "different_leaf": paths[0]["leaf_index"] != paths[1]["leaf_index"],
            })
        reconstructed_scores = [sum(tree[side]["leaf_output"] for tree in records)
                                for side in ("preferred", "other")]
        reconstructed_delta = sum(tree["delta"] for tree in records)
        raw_delta = scores[0] - scores[1]
        score_errors = [_close(a, b, "Leaf sum versus native raw score")
                        for a, b in zip(reconstructed_scores, native_scores, strict=True)]
        score_errors.extend(_close(a, b, "Leaf sum versus supplied raw score")
                            for a, b in zip(reconstructed_scores, scores, strict=True))
        delta_errors = [
            _close(reconstructed_delta, raw_delta, "Tree delta sum versus supplied pair delta"),
            _close(reconstructed_delta, native_scores[0] - native_scores[1],
                   "Tree delta sum versus native pair delta"),
            _close(reconstructed_scores[0] - reconstructed_scores[1], raw_delta,
                   "Leaf score difference versus supplied pair delta"),
        ]
    except TreeAuditError:
        raise
    except Exception as exc:
        raise TreeAuditError(f"Booster/path audit failed ({type(exc).__name__}): {exc}") from exc
    return {
        "label_basis": label_basis, "feature_names": names, "input_dtype": str(matrix.dtype),
        "full_features_exactly_equal": bool(np.array_equal(*rows, equal_nan=True)),
        "feature_equality_rule": "exact_values_and_matching_nan_positions; no tolerance",
        "different_leaf_count": sum(tree["different_leaf"] for tree in records),
        "tree_count": count, "prediction_tree_range": {"start_iteration": 0, "num_iteration": -1},
        "trees": records, "raw_scores": {"preferred": scores[0], "other": scores[1]},
        "native_raw_scores": {"preferred": native_scores[0], "other": native_scores[1]},
        "reconstructed_scores": {"preferred": reconstructed_scores[0], "other": reconstructed_scores[1]},
        "raw_delta": raw_delta, "reconstructed_delta": reconstructed_delta,
        "strict_direction": _strict_direction(*scores),
        "top_positive_trees": sorted((t for t in records if t["delta"] > 0),
                                     key=lambda t: (-t["delta"], t["tree_index"]))[:3],
        "top_negative_trees": sorted((t for t in records if t["delta"] < 0),
                                     key=lambda t: (t["delta"], t["tree_index"]))[:3],
        "interpretation_limit": "Each delta belongs to two complete tree paths, not one feature",
        "verification": {
            "passed": True, "atol": RECONSTRUCTION_ATOL, "rtol": RECONSTRUCTION_RTOL,
            "max_abs_score_error": max([*supplied_errors, *score_errors]),
            "max_abs_delta_error": max(delta_errors), "max_abs_leaf_output_error": max(leaf_errors),
            "supplied_scores_exactly_replayed": scores == native_scores,
            "shrinkage_applied_again": False,
        },
    }
