"""一次评测 run 的上下文。"""

from __future__ import annotations

from dataclasses import dataclass, field

from linkrag_eval.contracts.store import ResultStore
from linkrag_eval.metrics.retrieval import DEFAULT_K_VALUES
from linkrag_eval.models import Snapshot


@dataclass
class RunContext:
    run_id: str          # <yyyymmdd-hhmm>-<gitsha>-<标签>
    snapshot: Snapshot
    store: ResultStore
    top_k: int           # 已由入口回填(单一真相源 RECALL_RESULT_LIMIT)
    k_values: list[int] = field(default_factory=lambda: list(DEFAULT_K_VALUES))
