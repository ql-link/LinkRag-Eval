"""冻结 ``candidate_difference_v2`` 的在线 LambdaMART 推理与发布控制。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time
from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from linkrag_eval.retrieval.learning_to_rank.experiment import (
    FEATURE_NAMES,
    FEATURE_VERSION,
    _candidate_features,
)
from linkrag_eval.retrieval.learning_to_rank.short_query_gate import (
    ShortQueryFallbackConfig,
    apply_short_query_fallback,
)


def feature_signature() -> str:
    return hashlib.sha256(
        json.dumps(
            {"feature_version": FEATURE_VERSION, "feature_names": FEATURE_NAMES},
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
    training_data_sha256: str
    alias_registry_version: str
    n_estimators: int
    latency_budget_ms: int
    timeout_ms: int
    fallback_policy: str = "hybrid"
    model_file_sha256: str = ""
    alias_registry_sha256: str = ""
    short_fallback_version: str = ""
    short_fallback_sha256: str = ""

    def validate(self) -> None:
        if self.feature_version != FEATURE_VERSION or self.feature_signature != feature_signature():
            raise ValueError("LambdaMART feature signature mismatch")
        if self.feature_names != FEATURE_NAMES:
            raise ValueError("LambdaMART feature order mismatch")
        if self.timeout_ms <= 0 or self.latency_budget_ms <= 0:
            raise ValueError("latency budget/timeout 必须大于 0")


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
    max_latency_p95_ms: float = 25.0

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
    ):
        self.model_dir = Path(model_dir)
        self.manifest = _load_manifest(self.model_dir)
        self.model = _load_booster(self.model_dir, self.manifest)
        self.short_fallback = _load_short_fallback(self.model_dir, self.manifest)
        self.monitor = monitor or RankerMonitor()
        self.shadow = (
            LambdaMartOnlineRanker(shadow_model_dir, monitor=RankerMonitor())
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
        )

    async def rank(
        self,
        row: dict[str, Any],
        candidate_contents: dict[str, str],
    ) -> OnlineRankResult:
        started = time.perf_counter()
        chunk_ids, features, _ = _candidate_features(row, candidate_contents)
        try:
            scores = await asyncio.wait_for(
                asyncio.to_thread(self.model.predict, features),
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


def freeze_model(
    rows: list[dict[str, Any]],
    candidate_contents: dict[str, str],
    *,
    out_dir: str | Path,
    model_version: str,
    training_data_sha256: str,
    alias_registry_version: str,
    alias_registry_sha256: str = "",
    alias_registry_payload: dict[str, Any] | None = None,
    short_fallback_config: dict[str, Any] | None = None,
    n_estimators: int,
    latency_budget_ms: int = 25,
    timeout_ms: int = 40,
    seed: int = 20260724,
) -> ModelManifest:
    from lightgbm import LGBMRanker

    prepared = [_candidate_features(row, candidate_contents) for row in rows]
    train_x = np.concatenate([item[1] for item in prepared])
    train_y = np.concatenate([item[2] for item in prepared])
    groups = [len(item[0]) for item in prepared]
    model = LGBMRanker(
        objective="lambdarank",
        metric="ndcg",
        n_estimators=n_estimators,
        learning_rate=0.03,
        num_leaves=15,
        max_depth=4,
        min_child_samples=20,
        feature_fraction=0.8,
        reg_lambda=1.0,
        random_state=seed,
        verbosity=-1,
    )
    model.fit(train_x, train_y, group=groups)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    model_path = out / "model.txt"
    model.booster_.save_model(str(model_path), num_iteration=n_estimators)
    model_sha = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if alias_registry_payload is not None:
        alias_path = out / "alias_registry.json"
        alias_path.write_text(
            json.dumps(alias_registry_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        alias_registry_sha256 = hashlib.sha256(alias_path.read_bytes()).hexdigest()
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
    manifest = ModelManifest(
        model_version=model_version,
        feature_version=FEATURE_VERSION,
        feature_signature=feature_signature(),
        feature_names=list(FEATURE_NAMES),
        training_data_sha256=training_data_sha256,
        alias_registry_version=alias_registry_version,
        n_estimators=n_estimators,
        latency_budget_ms=latency_budget_ms,
        timeout_ms=timeout_ms,
        model_file_sha256=model_sha,
        alias_registry_sha256=alias_registry_sha256,
        short_fallback_version=short_version,
        short_fallback_sha256=short_sha,
    )
    (out / "manifest.json").write_text(
        json.dumps(asdict(manifest), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def activate_model(registry_dir: str | Path, model_version: str) -> None:
    root = Path(registry_dir)
    target = root / model_version
    _load_manifest(target)
    active_path = root / "active.json"
    previous = None
    if active_path.exists():
        previous = json.loads(active_path.read_text(encoding="utf-8")).get("active")
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
    previous = state.get("previous")
    if not previous:
        raise ValueError("没有可回滚的 previous model")
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
    if manifest.alias_registry_sha256:
        alias_sha = hashlib.sha256((model_dir / "alias_registry.json").read_bytes()).hexdigest()
        if alias_sha != manifest.alias_registry_sha256:
            raise ValueError("alias registry checksum mismatch")
    return manifest


def _load_booster(model_dir: Path, manifest: ModelManifest):
    from lightgbm import Booster

    manifest.validate()
    return Booster(model_file=str(model_dir / "model.txt"))


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
