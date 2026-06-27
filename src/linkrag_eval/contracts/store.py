"""ResultStore 协议:评测产物读写。

两个并列协议:
- :class:`ResultStore`:**同步**,文件后端(filesystem)实现,零基建/可回退。
- :class:`AsyncResultStore`:**异步**,评测自持 DB 后端(``store/`` 的 MySQL/EvalBase)实现。
  评测库走异步驱动,runner 本就 async,同步协议套异步库不干净,故另立异步协议。

两者方法对齐(snapshot/report/baseline),调用方按后端选其一;报告 HTML 是 blob,
DB 后端仍落文件。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from linkrag_eval.models import EvalResult, Snapshot


@runtime_checkable
class ResultStore(Protocol):
    def save_snapshot(self, snapshot: Snapshot) -> None: ...

    def save_report(self, run_id: str, content: str) -> None: ...

    def load_baseline(self, run_id: str) -> EvalResult | None: ...


@runtime_checkable
class AsyncResultStore(Protocol):
    async def save_snapshot(self, snapshot: Snapshot) -> None: ...

    async def save_report(self, run_id: str, content: str) -> None: ...

    async def load_baseline(self, run_id: str) -> EvalResult | None: ...
