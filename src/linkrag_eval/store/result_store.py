"""结果存储(简版文件后端,实现 contracts.ResultStore)。

完整文件结果后端见 :mod:`linkrag_eval.store.filesystem`;DB 台账后端见
:mod:`linkrag_eval.store.db_result_store`。本模块保留给只需快照/报告的轻量调用面。
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
        return None  # 简化后端不支持基线读取;完整文件/DB 后端支持。
