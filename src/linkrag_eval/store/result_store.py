"""结果存储(文件后端,实现 contracts.ResultStore)。

零基建:快照 / 报告落 ``out_dir``。DB 后端(MySQL eval_run/eval_metric_result)留作后续。
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from linkrag_eval.models import EvalResult, Snapshot


class JsonResultStore:
    """把快照与报告写进 ``out_dir`` 的文件后端。"""

    def __init__(self, out_dir: str | Path) -> None:
        self._dir = Path(out_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def save_snapshot(self, snapshot: Snapshot) -> None:
        (self._dir / f"{snapshot.run_id}.snapshot.json").write_text(
            json.dumps(dataclasses.asdict(snapshot), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save_report(self, run_id: str, content: str) -> None:
        (self._dir / f"{run_id}.report").write_text(content, encoding="utf-8")

    def load_baseline(self, run_id: str) -> EvalResult | None:
        return None  # 简化:基线对比留后续(DB 后端落地时接)
