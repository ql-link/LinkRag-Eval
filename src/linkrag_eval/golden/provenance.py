"""Query 来源元数据与真实性门禁。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal


QuerySourceKind = Literal["production_log", "support", "business", "opensource", "synthetic"]
REAL_QUERY_SOURCE_KINDS = frozenset({"production_log", "support", "business", "opensource"})


@dataclass(frozen=True)
class QueryProvenance:
    source_kind: QuerySourceKind
    source_name: str
    source_record_id: str
    domain: str
    scenario: str
    canonical_query: str
    collected_at: str | None = None
    dataset_version: str | None = None
    license: str | None = None
    generator_model: str | None = None
    pii_redacted: bool = False

    @property
    def is_real_query(self) -> bool:
        return self.source_kind in REAL_QUERY_SOURCE_KINDS and self.generator_model is None

    def validate(self) -> None:
        required = {
            "source_name": self.source_name,
            "source_record_id": self.source_record_id,
            "domain": self.domain,
            "scenario": self.scenario,
            "canonical_query": self.canonical_query,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError(f"query provenance 缺少字段: {missing}")
        if self.source_kind == "synthetic" and not self.generator_model:
            raise ValueError("synthetic query 必须记录 generator_model")
        if self.source_kind == "opensource" and (not self.dataset_version or not self.license):
            raise ValueError("opensource query 必须记录 dataset_version 与 license")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueryProvenance":
        value = cls(**data)
        value.validate()
        return value
