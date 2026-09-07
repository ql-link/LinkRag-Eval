"""冻结 ``candidate_difference_v3`` 的在线 LambdaMART 推理与发布控制。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time
from collections import Counter, deque
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np

from linkrag_eval.retrieval.learning_to_rank.experiment import _candidate_features
from linkrag_eval.retrieval.learning_to_rank.features import (
    BASELINE_THRESHOLDS,
    BASELINE_WEIGHTS,
    FEATURE_NAMES,
    FEATURE_VERSION,
    ROUTES,
    FeatureContractError,
    build_online_features,
    rules_version,
)
from linkrag_eval.retrieval.learning_to_rank.short_query_gate import (
    ShortQueryFallbackConfig,
    apply_short_query_fallback,
)

WEIGHTED_SCORE_BASELINE = "weighted-score-baseline"


def feature_signature(feature_version: str = FEATURE_VERSION) -> str:
    rule = rules_version(feature_version)
    contract = {"feature_version": feature_version, "feature_names": FEATURE_NAMES}
    if feature_version != FEATURE_VERSION:
        contract["feature_rules_version"] = rule
    return hashlib.sha256(
        json.dumps(
            contract,
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class ModelManifest:
    model_version: str
    feature_version: str
    feature_signature: str
    feature_names: list[str]
    training_data_sha256: str  # 当前模型包格式字段；新导出留空，不计算训练输入摘要。
    n_estimators: int
    latency_budget_ms: int
    timeout_ms: int
    model_format: str = "lightgbm_text_v1"
    lightgbm_version: str = ""
    training_params: dict[str, Any] = field(default_factory=dict)
    fallback_policy: str = "hybrid"
    alias_enabled: bool = False
    model_file_sha256: str = ""
    short_fallback_version: str = ""
    short_fallback_sha256: str = ""
    feature_rules_version: str | None = None

    def validate(self) -> None:
        if self.feature_signature != feature_signature(self.feature_version):
            raise ValueError("LambdaMART feature signature mismatch")
        expected_rules = rules_version(self.feature_version)
        if self.feature_rules_version != expected_rules and not (
            self.feature_version == FEATURE_VERSION and self.feature_rules_version is None
        ):
            raise ValueError("LambdaMART feature rules version mismatch")
        if self.feature_names != FEATURE_NAMES:
            raise ValueError("LambdaMART feature order mismatch")
        if self.timeout_ms <= 0 or self.latency_budget_ms <= 0:
            raise ValueError("latency budget/timeout 必须大于 0")
        if self.model_format != "lightgbm_text_v1" or not self.lightgbm_version:
            raise ValueError("LambdaMART serialization/runtime version missing")
        if self.alias_enabled:
            raise ValueError("candidate_difference_v3 不支持 Alias")


@dataclass
class RankerMonitor:
    counters: Counter[str] = field(default_factory=Counter)
    latencies_ms: deque[float] = field(default_factory=lambda: deque(maxlen=10_000))

    def record(self, *, mode: str, elapsed_ms: float) -> None:
        self.counters[mode] += 1
        self.latencies_ms.append(elapsed_ms)

    def snapshot(self) -> dict[str, Any]:
        values = sorted(self.latencies_ms)

        def percentile(q: float) -> float:
            return values[min(len(values) - 1, math.ceil(len(values) * q) - 1)] if values else 0.0

        return {
            "counters": dict(self.counters),
            "latency_p50_ms": percentile(0.50),
            "latency_p95_ms": percentile(0.95),
            "latency_p99_ms": percentile(0.99),
        }


@dataclass(frozen=True)
class OnlineRankResult:
    ranked_chunk_ids: list[str]
    mode: str
    model_version: str
    elapsed_ms: float
    shadow_ranked_chunk_ids: list[str] | None = None
    reason: str | None = None


@dataclass(frozen=True)
class RollbackPolicy:
    min_requests: int = 100
    max_fallback_rate: float = 0.02
    max_latency_p95_ms: float = 250.0

    def violations(self, snapshot: dict[str, Any]) -> list[str]:
        counters = snapshot.get("counters") or {}
        total = sum(
            int(value)
            for key, value in counters.items()
            if key
            in {
                "ltr",
                "hybrid_short_low_confidence",
                "fallback_timeout",
                "fallback_error",
                "fallback_budget_exceeded",
            }
        )
        if total < self.min_requests:
            return []
        fallback = sum(int(value) for key, value in counters.items() if key.startswith("fallback_"))
        reasons = []
        if fallback / total > self.max_fallback_rate:
            reasons.append(f"fallback_rate={fallback / total:.4f}")
        if float(snapshot.get("latency_p95_ms") or 0.0) > self.max_latency_p95_ms:
            reasons.append(f"latency_p95_ms={snapshot['latency_p95_ms']:.2f}")
        return reasons


class LambdaMartOnlineRanker:
    def __init__(
        self,
        model_dir: str | Path,
        *,
        monitor: RankerMonitor | None = None,
        shadow_model_dir: str | Path | None = None,
        prediction_num_threads: int | None = None,
        feature_version: str = FEATURE_VERSION,
    ):
        if prediction_num_threads is not None and (
            type(prediction_num_threads) is not int or prediction_num_threads <= 0
        ):
            raise ValueError("prediction_num_threads must be a positive integer")
        self.prediction_num_threads = prediction_num_threads
        self._prediction_kwargs = (
            {"num_threads": prediction_num_threads} if prediction_num_threads is not None else {}
        )
        self.model_dir = Path(model_dir)
        self.manifest = _load_manifest(self.model_dir)
        rules_version(feature_version)
        if self.manifest.feature_version != feature_version:
            raise FeatureContractError("requested feature version does not match model package")
        self.feature_version = feature_version
        self.model = _load_booster(self.model_dir, self.manifest)
        self.short_fallback = _load_short_fallback(self.model_dir, self.manifest)
        self.monitor = monitor or RankerMonitor()
        self.shadow = (
            LambdaMartOnlineRanker(
                shadow_model_dir, monitor=RankerMonitor(),
                prediction_num_threads=prediction_num_threads,
                feature_version=feature_version,
            )
            if shadow_model_dir
            else None
        )
        self._shadow_tasks: set[asyncio.Task[Any]] = set()

    @classmethod
    def from_registry(
        cls,
        registry_dir: str | Path,
        *,
        monitor: RankerMonitor | None = None,
        shadow_version: str | None = None,
        feature_version: str = FEATURE_VERSION,
    ) -> "LambdaMartOnlineRanker":
        root = Path(registry_dir)
        state = json.loads((root / "active.json").read_text(encoding="utf-8"))
        active = str(state.get("active") or "").strip()
        if not active:
            raise ValueError("LambdaMART active model 未配置")
        return cls(
            root / active,
            monitor=monitor,
            shadow_model_dir=root / shadow_version if shadow_version else None,
            feature_version=feature_version,
        )

    def predict_features(self, features: np.ndarray, *, feature_version: str) -> np.ndarray:
        """Raw prediction for an explicitly versioned matrix; cannot silently cross versions."""
        if feature_version != self.feature_version:
            raise FeatureContractError("feature matrix version does not match model")
        if (features.ndim != 2 or features.shape[1] != len(FEATURE_NAMES)
                or features.dtype != np.float32 or not np.isfinite(features).all()):
            raise FeatureContractError("invalid LTR matrix schema/dtype/values")
        return np.asarray(self.model.predict(features, **self._prediction_kwargs))

    async def rank(
        self,
        row: dict[str, Any],
        candidate_contents: dict[str, str],
    ) -> OnlineRankResult:
        started = time.perf_counter()
        if row.get("feature_version", self.feature_version) != self.feature_version:
            raise FeatureContractError("request feature version does not match model")
        chunk_ids, features = build_online_features(
            query=str(row["query"]),
            routes=row["routes"],
            candidate_contents=candidate_contents,
            feature_version=self.feature_version,
        )
        try:
            scores = await asyncio.wait_for(
                asyncio.to_thread(self.model.predict, features, **self._prediction_kwargs),
                timeout=self.manifest.timeout_ms / 1000,
            )
            ranked = _rank(chunk_ids, scores)
            elapsed_ms = (time.perf_counter() - started) * 1000
            if self.short_fallback is not None:
                ranked, short_fallback, _confidence = apply_short_query_fallback(
                    query=str(row["query"]),
                    ltr_ranked=ranked,
                    ltr_scores=[float(value) for value in scores],
                    hybrid_ranked=_hybrid_fallback(chunk_ids, features),
                    config=self.short_fallback,
                )
            else:
                short_fallback = False
            if elapsed_ms > self.manifest.latency_budget_ms:
                ranked = _hybrid_fallback(chunk_ids, features)
                mode = "fallback_budget_exceeded"
            elif short_fallback:
                mode = "hybrid_short_low_confidence"
            else:
                mode = "ltr"
            self.monitor.record(mode=mode, elapsed_ms=elapsed_ms)
        except Exception as exc:
            ranked = _hybrid_fallback(chunk_ids, features)
            elapsed_ms = (time.perf_counter() - started) * 1000
            mode = "fallback_timeout" if isinstance(exc, asyncio.TimeoutError) else "fallback_error"
            self.monitor.record(mode=mode, elapsed_ms=elapsed_ms)
            return OnlineRankResult(
                ranked_chunk_ids=ranked,
                mode=mode,
                model_version=self.manifest.model_version,
                elapsed_ms=elapsed_ms,
                reason=type(exc).__name__,
            )
        if self.shadow is not None:
            task = asyncio.create_task(self._run_shadow(row, candidate_contents, ranked))
            self._shadow_tasks.add(task)
            task.add_done_callback(self._shadow_tasks.discard)
        return OnlineRankResult(
            ranked_chunk_ids=ranked,
            mode=mode,
            model_version=self.manifest.model_version,
            elapsed_ms=elapsed_ms,
            shadow_ranked_chunk_ids=None,
        )

    async def _run_shadow(
        self,
        row: dict[str, Any],
        candidate_contents: dict[str, str],
        primary_ranked: list[str],
    ) -> None:
        assert self.shadow is not None
        try:
            shadow_result = await self.shadow.rank(row, candidate_contents)
            self.monitor.counters["shadow_completed"] += 1
            if shadow_result.ranked_chunk_ids[:10] != primary_ranked[:10]:
                self.monitor.counters["shadow_top10_changed"] += 1
        except Exception:
            self.monitor.counters["shadow_failed"] += 1

    async def drain_shadow(self) -> None:
        """验收/关停时等待已发出的 Shadow 任务，不影响单请求主链路。"""
        while self._shadow_tasks:
            await asyncio.gather(*tuple(self._shadow_tasks), return_exceptions=True)


class WeightedScoreOnlineRanker:
    """Same-contract local fallback used when no valid LambdaMART model is active."""

    def __init__(self, *, monitor: RankerMonitor | None = None, reason: str | None = None):
        self.monitor = monitor or RankerMonitor()
        self.reason = reason

    async def rank(
        self,
        row: dict[str, Any],
        candidate_contents: dict[str, str],
    ) -> OnlineRankResult:
        started = time.perf_counter()
        chunk_ids, features = build_online_features(
            query=str(row["query"]),
            routes=row["routes"],
            candidate_contents=candidate_contents,
        )
        ranked = _hybrid_fallback(chunk_ids, features)
        elapsed_ms = (time.perf_counter() - started) * 1000
        self.monitor.record(mode="fallback_weighted_score", elapsed_ms=elapsed_ms)
        return OnlineRankResult(
            ranked_chunk_ids=ranked,
            mode="fallback_weighted_score",
            model_version=WEIGHTED_SCORE_BASELINE,
            elapsed_ms=elapsed_ms,
            reason=self.reason,
        )

    async def drain_shadow(self) -> None:
        return None


def load_active_ranker(
    registry_dir: str | Path,
    *,
    monitor: RankerMonitor | None = None,
    shadow_version: str | None = None,
    feature_version: str = FEATURE_VERSION,
) -> LambdaMartOnlineRanker | WeightedScoreOnlineRanker:
    """Load the active model, degrading to weighted fusion on any startup validation error."""
    root = Path(registry_dir)
    rules_version(feature_version)
    try:
        state = json.loads((root / "active.json").read_text(encoding="utf-8"))
        if state.get("active") == WEIGHTED_SCORE_BASELINE:
            if feature_version != FEATURE_VERSION:
                raise FeatureContractError("English model requested but registry selects legacy baseline")
            return WeightedScoreOnlineRanker(monitor=monitor, reason="baseline_active")
        return LambdaMartOnlineRanker.from_registry(
            root,
            monitor=monitor,
            shadow_version=shadow_version,
            feature_version=feature_version,
        )
    except FeatureContractError:
        raise
    except Exception as exc:
        if feature_version != FEATURE_VERSION:
            raise
        fallback = WeightedScoreOnlineRanker(monitor=monitor, reason=type(exc).__name__)
        fallback.monitor.counters["startup_fallback"] += 1
        return fallback


def freeze_model(
    rows: list[dict[str, Any]],
    candidate_contents: dict[str, str],
    *,
    out_dir: str | Path,
    model_version: str,
    short_fallback_config: dict[str, Any] | None = None,
    n_estimators: int,
    latency_budget_ms: int = 250,
    timeout_ms: int = 350,
    seed: int = 20260724,
) -> ModelManifest:
    from lightgbm import LGBMRanker

    prepared = [_candidate_features(row, candidate_contents) for row in rows]
    train_x = np.concatenate([item[1] for item in prepared])
    train_y = np.concatenate([item[2] for item in prepared])
    groups = [len(item[0]) for item in prepared]
    training_params = {
        "objective": "lambdarank",
        "metric": "ndcg",
        "n_estimators": n_estimators,
        "learning_rate": 0.03,
        "num_leaves": 15,
        "max_depth": 4,
        "min_child_samples": 20,
        "feature_fraction": 0.8,
        "reg_lambda": 1.0,
        "random_state": seed,
        "verbosity": -1,
    }
    model = LGBMRanker(
        **training_params,
    )
    model.fit(train_x, train_y, group=groups, feature_name=list(FEATURE_NAMES))
    return export_trained_booster(
        model.booster_,
        out_dir=out_dir,
        model_version=model_version,
        num_iteration=min(n_estimators, model.booster_.current_iteration()),
        training_params=training_params,
        short_fallback_config=short_fallback_config,
        latency_budget_ms=latency_budget_ms,
        timeout_ms=timeout_ms,
    )


def export_trained_booster(
    booster: Any,
    *,
    out_dir: str | Path,
    model_version: str,
    num_iteration: int,
    training_params: dict[str, Any],
    short_fallback_config: dict[str, Any] | None = None,
    latency_budget_ms: int = 250,
    timeout_ms: int = 350,
    feature_version: str = FEATURE_VERSION,
) -> ModelManifest:
    """Export an already selected LambdaMART tree prefix without fitting again.

    The serialized prefix also produces the contract vectors, so early-stopping
    patience trees cannot leak into either the exported model or its expectations.
    """
    import lightgbm

    if not isinstance(booster, lightgbm.Booster):
        raise TypeError("export requires a fitted lightgbm.Booster")
    if booster.num_feature() != len(FEATURE_NAMES) or booster.feature_name() != FEATURE_NAMES:
        raise ValueError("export feature count/order mismatch")
    if booster.params.get("objective") != "lambdarank" or booster.num_model_per_iteration() != 1:
        raise ValueError("export requires a single-output lambdarank Booster")
    if type(num_iteration) is not int or not 1 <= num_iteration <= booster.current_iteration():
        raise ValueError("num_iteration must select an existing positive tree prefix")
    if short_fallback_config is not None:
        policy = ShortQueryFallbackConfig(**short_fallback_config)
        if (
            not isinstance(policy.version, str) or not policy.version
            or policy.confidence_feature != "ltr_top12_margin" or policy.fallback != "hybrid"
            or type(policy.max_query_chars) is not int or policy.max_query_chars < 0
            or type(policy.confidence_threshold) not in (int, float)
            or not math.isfinite(policy.confidence_threshold) or policy.confidence_threshold < 0
        ):
            raise ValueError("unsupported or invalid short fallback policy")
    # Constructing a Booster from its text does not retrain or consume supervision.
    model_text = booster.model_to_string(num_iteration=num_iteration)
    selected = lightgbm.Booster(model_str=model_text)
    manifest = ModelManifest(
        model_version=model_version,
        feature_version=feature_version,
        feature_signature=feature_signature(feature_version),
        feature_rules_version=rules_version(feature_version),
        feature_names=list(FEATURE_NAMES),
        training_data_sha256="",
        n_estimators=selected.num_trees(),
        latency_budget_ms=latency_budget_ms,
        timeout_ms=timeout_ms,
        lightgbm_version=lightgbm.__version__,
        training_params=dict(training_params),
    )
    manifest.validate()
    out = Path(out_dir)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise FileExistsError(f"model output must be absent or empty: {out}")
    out.mkdir(parents=True, exist_ok=True)
    model_path = out / "model.txt"
    model_path.write_text(model_text, encoding="utf-8")
    model_sha = hashlib.sha256(model_path.read_bytes()).hexdigest()
    short_version = ""
    short_sha = ""
    if short_fallback_config is not None:
        short_path = out / "short_fallback.json"
        short_path.write_text(
            json.dumps(short_fallback_config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        short_version = str(short_fallback_config.get("version") or "")
        short_sha = hashlib.sha256(short_path.read_bytes()).hexdigest()
    manifest = replace(
        manifest,
        model_file_sha256=model_sha,
        short_fallback_version=short_version,
        short_fallback_sha256=short_sha,
    )
    (out / "manifest.json").write_text(
        json.dumps(asdict(manifest), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_production_contract(
        out,
        predictor=lambda features: selected.predict(features, num_threads=1),
        feature_version=feature_version,
    )
    _write_sha256sums(out)
    return manifest


def _write_production_contract(
    out: Path,
    *,
    predictor: Any,
    feature_version: str = FEATURE_VERSION,
) -> None:
    contract = {
        "feature_version": feature_version,
        "feature_signature": feature_signature(feature_version),
        "feature_rules_version": rules_version(feature_version),
        "feature_names": FEATURE_NAMES,
        "required_request_fields": {
            "query": "string",
            "routes": {source: "ordered list[chunk_id,doc_id,dataset_id,score]" for source in ROUTES},
            "candidate_contents": "map[chunk_id,string]",
        },
        "forbidden_request_fields": ["sample_id", "scenario", "expected_chunk_ids", "qrels"],
        "fallback": {
            "type": WEIGHTED_SCORE_BASELINE,
            "weights": BASELINE_WEIGHTS,
            "thresholds": BASELINE_THRESHOLDS,
        },
        "alias_enabled": False,
    }
    (out / "feature_contract.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    vectors = []
    for index, online_input in enumerate(_contract_inputs(), 1):
        if feature_version != FEATURE_VERSION:
            online_input["query"] = ["Which item isn't approved?", "Which item costs 3.14?",
                                     "Dr. Lee is ready. Which item is not approved?"][index - 1]
            online_input["candidate_contents"] = {
                cid: ["Dr. Lee is ready. The item is not approved; cost 3.14.",
                      "Dr. Lee is ready. The item is approved; cost 13.14.",
                      "The item cannot be approved; cost 1,234.50."][i]
                for i, cid in enumerate(online_input["candidate_contents"])
            }
        chunk_ids, features = build_online_features(
            query=online_input["query"],
            routes=online_input["routes"],
            candidate_contents=online_input["candidate_contents"],
            feature_version=feature_version,
        )
        scores = predictor(features)
        vectors.append(
            {
                "id": f"contract-{index}",
                "input": online_input,
                "expected": {
                    "candidate_chunk_ids": chunk_ids,
                    "feature_matrix_sha256": hashlib.sha256(features.tobytes()).hexdigest(),
                    "ltr_ranked_chunk_ids": _rank(chunk_ids, scores),
                    "ltr_scores": [float(score) for score in scores],
                    "weighted_score_ranked_chunk_ids": _hybrid_fallback(chunk_ids, features),
                },
            }
        )
    (out / "test_vectors.json").write_text(
        json.dumps({"vectors": vectors}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _contract_inputs() -> list[dict[str, Any]]:
    def hit(chunk_id: str, doc_id: int, score: float) -> dict[str, Any]:
        return {"chunk_id": chunk_id, "doc_id": doc_id, "dataset_id": 999999, "score": score}

    return [
        {
            "query": "订单ABC-2025为什么不能退款",
            "routes": {
                "dense": [hit("contract-a", 1, 0.91), hit("contract-b", 2, 0.72)],
                "sparse": [hit("contract-b", 2, 8.5), hit("contract-a", 1, 2.1)],
                "bm25": [hit("contract-b", 2, 12.0), hit("contract-c", 3, 4.0)],
            },
            "candidate_contents": {
                "contract-a": "订单ABC-2024支持退款，具体以旧版规则为准。",
                "contract-b": "订单ABC-2025不能退款，v2.1规则明确禁止退款。",
                "contract-c": "其他订单可在七日内申请售后。",
            },
        },
        {
            "query": "年假规则",
            "routes": {
                "dense": [hit("contract-d", 4, 0.82), hit("contract-e", 5, 0.80)],
                "sparse": [hit("contract-e", 5, 6.0)],
                "bm25": [hit("contract-e", 5, 9.0), hit("contract-d", 4, 8.7)],
            },
            "candidate_contents": {
                "contract-d": "年假申请流程与审批人说明。",
                "contract-e": "员工年假天数、结转期限及适用规则。",
            },
        },
        {
            "query": "2026年3月后同时满足企业版和已认证条件的额度",
            "routes": {
                "dense": [hit("contract-f", 6, 0.88), hit("contract-g", 6, 0.84)],
                "sparse": [hit("contract-g", 6, 7.2), hit("contract-h", 7, 5.4)],
                "bm25": [hit("contract-g", 6, 11.0), hit("contract-h", 7, 8.0)],
            },
            "candidate_contents": {
                "contract-f": "企业版默认额度为1000，认证状态不影响。",
                "contract-g": "2026年3月后，企业版且已认证账户额度调整为3000。",
                "contract-h": "个人版已认证账户额度为500。",
            },
        },
    ]


def _write_sha256sums(out: Path) -> None:
    names = [
        "model.txt",
        "manifest.json",
        "short_fallback.json",
        "feature_contract.json",
        "test_vectors.json",
    ]
    lines = [
        f"{hashlib.sha256((out / name).read_bytes()).hexdigest()}  {name}"
        for name in names
        if (out / name).exists()
    ]
    (out / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_production_bundle(model_dir: str | Path) -> dict[str, Any]:
    """Verify file hashes, feature contract, and deterministic online test vectors."""
    root = Path(model_dir)
    sums = {}
    for line in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split(maxsplit=1)
        sums[name.strip()] = digest
    for name, expected in sums.items():
        actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"production bundle checksum mismatch: {name}")

    manifest = _load_manifest(root)
    contract = json.loads((root / "feature_contract.json").read_text(encoding="utf-8"))
    if contract.get("feature_signature") != manifest.feature_signature:
        raise ValueError("production feature contract signature mismatch")
    for key in ("feature_version", "feature_names"):
        if contract.get(key) != getattr(manifest, key):
            raise ValueError(f"production feature contract mismatch: {key}")
    if contract.get("feature_rules_version") != rules_version(manifest.feature_version) and not (
        manifest.feature_version == FEATURE_VERSION and contract.get("feature_rules_version") is None
    ):
        raise ValueError("production feature rules mismatch")
    if contract.get("alias_enabled") is not False:
        raise ValueError("production bundle must keep Alias disabled")

    model = _load_booster(root, manifest)
    payload = json.loads((root / "test_vectors.json").read_text(encoding="utf-8"))
    vectors = list(payload.get("vectors") or [])
    if not vectors:
        raise ValueError("production bundle test vectors are empty")
    for vector in vectors:
        online_input = vector["input"]
        expected = vector["expected"]
        chunk_ids, features = build_online_features(
            query=str(online_input["query"]),
            routes=online_input["routes"],
            candidate_contents=online_input["candidate_contents"],
            feature_version=manifest.feature_version,
        )
        if hashlib.sha256(features.tobytes()).hexdigest() != expected["feature_matrix_sha256"]:
            raise ValueError(f"feature vector mismatch: {vector['id']}")
        if chunk_ids != expected["candidate_chunk_ids"]:
            raise ValueError(f"candidate order mismatch: {vector['id']}")
        scores = model.predict(features, num_threads=1)
        if "ltr_scores" in expected and not np.array_equal(scores, expected["ltr_scores"]):
            raise ValueError(f"LambdaMART score mismatch: {vector['id']}")
        if _rank(chunk_ids, scores) != expected["ltr_ranked_chunk_ids"]:
            raise ValueError(f"LambdaMART ranking mismatch: {vector['id']}")
        if _hybrid_fallback(chunk_ids, features) != expected["weighted_score_ranked_chunk_ids"]:
            raise ValueError(f"weighted fallback mismatch: {vector['id']}")
    return {
        "model_version": manifest.model_version,
        "feature_version": manifest.feature_version,
        "feature_signature": manifest.feature_signature,
        "alias_enabled": manifest.alias_enabled,
        "verified_files": sorted(sums),
        "verified_test_vectors": len(vectors),
    }


def activate_model(registry_dir: str | Path, model_version: str) -> None:
    root = Path(registry_dir)
    root.mkdir(parents=True, exist_ok=True)
    if model_version != WEIGHTED_SCORE_BASELINE:
        _load_manifest(root / model_version)
    active_path = root / "active.json"
    previous = WEIGHTED_SCORE_BASELINE
    if active_path.exists():
        old_state = json.loads(active_path.read_text(encoding="utf-8"))
        old_active = old_state.get("active")
        previous = old_state.get("previous") if old_active == model_version else old_active
        previous = previous or WEIGHTED_SCORE_BASELINE
    history_path = root / "history.jsonl"
    with history_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"active": model_version, "previous": previous}) + "\n")
    active_path.write_text(
        json.dumps({"active": model_version, "previous": previous}, indent=2) + "\n",
        encoding="utf-8",
    )


def rollback_model(registry_dir: str | Path) -> str:
    root = Path(registry_dir)
    active_path = root / "active.json"
    state = json.loads(active_path.read_text(encoding="utf-8"))
    if state.get("active") == WEIGHTED_SCORE_BASELINE:
        return WEIGHTED_SCORE_BASELINE
    previous = state.get("previous")
    previous = previous or WEIGHTED_SCORE_BASELINE
    activate_model(root, str(previous))
    return str(previous)


def rollback_if_violated(
    registry_dir: str | Path,
    monitor: RankerMonitor,
    *,
    policy: RollbackPolicy = RollbackPolicy(),
) -> dict[str, Any]:
    snapshot = monitor.snapshot()
    reasons = policy.violations(snapshot)
    rolled_back_to = rollback_model(registry_dir) if reasons else None
    return {
        "rolled_back": bool(reasons),
        "rolled_back_to": rolled_back_to,
        "reasons": reasons,
        "monitor": snapshot,
    }


async def evaluate_frozen_model(
    ranker: LambdaMartOnlineRanker,
    rows: list[dict[str, Any]],
    candidate_contents: dict[str, str],
) -> dict[str, Any]:
    """只加载冻结模型，对未曝光 cache 评测；不会重新训练或选参。"""
    predictions = []
    for row in rows:
        if row.get("failed_sources"):
            raise ValueError(f"Blind cache 含 failed_sources:{row.get('sample_id')}")
        chunk_ids, features, _ = _candidate_features(row, candidate_contents)
        baseline_ranked = _hybrid_fallback(chunk_ids, features)
        result = await ranker.rank(row, candidate_contents)
        expected = {str(value) for value in row["expected_chunk_ids"]}

        def metrics(ranked: list[str]) -> tuple[int, float]:
            hit_rank = next(
                (index for index, chunk_id in enumerate(ranked[:10], 1) if chunk_id in expected),
                None,
            )
            return int(hit_rank is not None), 1.0 / hit_rank if hit_rank else 0.0

        baseline_hit, baseline_mrr = metrics(baseline_ranked)
        ltr_hit, ltr_mrr = metrics(result.ranked_chunk_ids)
        predictions.append(
            {
                "sample_id": row["sample_id"],
                "scenario": row.get("scenario"),
                "baseline_hit_at_10": baseline_hit,
                "baseline_mrr": baseline_mrr,
                "ltr_hit_at_10": ltr_hit,
                "ltr_mrr": ltr_mrr,
                "mode": result.mode,
                "elapsed_ms": result.elapsed_ms,
            }
        )
    n = len(predictions)
    if not n:
        raise ValueError("Blind cache 为空")
    scenario_rows: dict[str, list[dict[str, Any]]] = {}
    for row in predictions:
        scenario_rows.setdefault(str(row.get("scenario") or "unknown"), []).append(row)
    from linkrag_eval.retrieval.learning_to_rank.experiment import _paired_acceptance

    await ranker.drain_shadow()

    return {
        "model_version": ranker.manifest.model_version,
        "feature_version": ranker.manifest.feature_version,
        "feature_signature": ranker.manifest.feature_signature,
        "n": n,
        "baseline_hit_at_10": sum(row["baseline_hit_at_10"] for row in predictions) / n,
        "ltr_hit_at_10": sum(row["ltr_hit_at_10"] for row in predictions) / n,
        "baseline_mrr": sum(row["baseline_mrr"] for row in predictions) / n,
        "ltr_mrr": sum(row["ltr_mrr"] for row in predictions) / n,
        "paired_acceptance": _paired_acceptance(predictions, seed=20260724 + 5000),
        "scenario_metrics": {
            scenario: {
                "n": len(values),
                "baseline_hit_at_10": sum(row["baseline_hit_at_10"] for row in values)
                / len(values),
                "ltr_hit_at_10": sum(row["ltr_hit_at_10"] for row in values) / len(values),
            }
            for scenario, values in sorted(scenario_rows.items())
        },
        "monitor": ranker.monitor.snapshot(),
        "predictions": predictions,
    }


def _load_manifest(model_dir: Path) -> ModelManifest:
    manifest = ModelManifest(**json.loads((model_dir / "manifest.json").read_text(encoding="utf-8")))
    manifest.validate()
    model_sha = hashlib.sha256((model_dir / "model.txt").read_bytes()).hexdigest()
    if model_sha != manifest.model_file_sha256:
        raise ValueError("LambdaMART model checksum mismatch")
    return manifest


def _load_booster(model_dir: Path, manifest: ModelManifest):
    from lightgbm import Booster

    manifest.validate()
    model = Booster(model_file=str(model_dir / "model.txt"))
    known_legacy_columns = (
        manifest.feature_version == FEATURE_VERSION
        and manifest.model_version == "candidate-difference-v3-20260728-final33"
        and manifest.model_file_sha256 == "1de4d9380ae16b26e210a67280335c5ed6976001fc23641c54241e13da82de41"
        and model.feature_name() == [f"Column_{i}" for i in range(len(FEATURE_NAMES))]
    )
    if model.num_feature() != len(FEATURE_NAMES) or (
        model.feature_name() != FEATURE_NAMES and not known_legacy_columns
    ):
        raise FeatureContractError("Booster feature columns do not match declared contract")
    if model.num_trees() != manifest.n_estimators:
        raise FeatureContractError("Booster tree count does not match declared contract")
    return model


def _load_short_fallback(
    model_dir: Path, manifest: ModelManifest
) -> ShortQueryFallbackConfig | None:
    if not manifest.short_fallback_sha256:
        return None
    path = model_dir / "short_fallback.json"
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest.short_fallback_sha256:
        raise ValueError("short fallback checksum mismatch")
    payload = json.loads(path.read_text(encoding="utf-8"))
    config = ShortQueryFallbackConfig(**payload)
    if config.version != manifest.short_fallback_version:
        raise ValueError("short fallback version mismatch")
    return config


def _rank(chunk_ids: list[str], scores: Any) -> list[str]:
    return [item[0] for item in sorted(zip(chunk_ids, scores), key=lambda item: (-float(item[1]), item[0]))]


def _hybrid_fallback(chunk_ids: list[str], features: np.ndarray) -> list[str]:
    score_index = FEATURE_NAMES.index("baseline_score")
    rr_index = FEATURE_NAMES.index("baseline_rr")
    return [
        item[0]
        for item in sorted(
            zip(chunk_ids, features[:, score_index], features[:, rr_index]),
            key=lambda item: (-float(item[1]), -float(item[2]), item[0]),
        )
    ]
