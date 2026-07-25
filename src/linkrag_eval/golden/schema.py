"""GoldenSample:黄金集条目 schema(jsonl 逐行一对象)。

满足 contracts.Sample 协议。第 1 层只依赖 expected_chunk_ids(与
dataset_ids/user_id),缺 golden_answer 也能独立跑;开源数据集来源
(doc 粒度)只填 expected_doc_ids。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from linkrag_eval.golden.provenance import QueryProvenance
from linkrag_eval.models import QuestionType


@dataclass(frozen=True)
class GoldenSample:
    id: str
    query: str
    user_id: int
    dataset_ids: list[int]
    # 第 1 层 reference(命中/不命中二值);开源 doc 粒度来源可为空列表
    expected_chunk_ids: list[str] = field(default_factory=list)
    # chunk 失效时的 doc 粒度降级;开源来源的主 reference
    expected_doc_ids: list[int] | None = None
    golden_answer: str | None = None
    type: QuestionType = QuestionType.KEYWORD
    note: str = ""
    # 分级相关性(T2Ranking 等 4 级标注):reference id(chunk_id 或 str(doc_id))→ grade。
    # 非 None 时 NDCG 走分级口径(ndcg_graded),与二值口径分名、不互比。
    relevance_grades: dict[str, int] | None = None
    provenance: QueryProvenance | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "query": self.query,
            "user_id": self.user_id,
            "dataset_ids": list(self.dataset_ids),
            "expected_chunk_ids": list(self.expected_chunk_ids),
            "expected_doc_ids": list(self.expected_doc_ids) if self.expected_doc_ids else None,
            "golden_answer": self.golden_answer,
            "type": self.type.value,
            "note": self.note,
            "relevance_grades": dict(self.relevance_grades) if self.relevance_grades else None,
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }

    def to_jsonl_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GoldenSample":
        missing = [f for f in ("id", "query", "user_id", "dataset_ids") if data.get(f) in (None, "")]
        if missing:
            raise ValueError(f"GoldenSample 缺必填字段: {missing}")
        chunk_ids = list(data.get("expected_chunk_ids") or [])
        doc_ids = data.get("expected_doc_ids")
        if not chunk_ids and not doc_ids:
            raise ValueError(
                f"GoldenSample[{data['id']}] expected_chunk_ids 与 expected_doc_ids 至少填一个"
            )
        return cls(
            id=str(data["id"]),
            query=str(data["query"]),
            user_id=int(data["user_id"]),
            dataset_ids=[int(d) for d in data["dataset_ids"]],
            expected_chunk_ids=[str(c) for c in chunk_ids],
            expected_doc_ids=[int(d) for d in doc_ids] if doc_ids else None,
            golden_answer=data.get("golden_answer"),
            type=QuestionType(data.get("type", QuestionType.KEYWORD.value)),
            note=str(data.get("note", "")),
            relevance_grades=(
                {str(k): int(v) for k, v in data["relevance_grades"].items()}
                if data.get("relevance_grades")
                else None
            ),
            provenance=(
                QueryProvenance.from_dict(data["provenance"])
                if data.get("provenance")
                else None
            ),
        )
