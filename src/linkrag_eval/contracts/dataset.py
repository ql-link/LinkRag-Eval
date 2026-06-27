"""Sample / Dataset 协议:黄金集样本与数据集的统一读取面。

具体的 GoldenSample(jsonl schema + 加载校验)在 golden/schema.py 实现,
须满足此处的 Sample 协议。
"""

from __future__ import annotations

from typing import Iterator, Protocol, runtime_checkable

from linkrag_eval.models import QuestionType


@runtime_checkable
class Sample(Protocol):
    id: str
    query: str
    user_id: int
    dataset_ids: list[int]
    expected_chunk_ids: list[str]
    expected_doc_ids: list[int] | None
    golden_answer: str | None
    type: QuestionType


@runtime_checkable
class Dataset(Protocol):
    def __iter__(self) -> Iterator[Sample]: ...

    def __len__(self) -> int: ...
