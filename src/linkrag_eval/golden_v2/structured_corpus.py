"""多 Chunk / 跨段落 / 精确标识符 eval-only 语料构建。"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from linkrag_eval.golden.provenance import QueryProvenance
from linkrag_eval.store.ids import content_hash, eval_chunk_id


REQUIRED_SCENARIOS = frozenset({"cross_chunk", "exact_identifier", "date", "version"})


@dataclass(frozen=True)
class StructuredCorpusReport:
    documents: int
    chunks: int
    queries: int
    multi_positive_queries: int
    scenario_counts: dict[str, int]
    dataset_id: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_structured_corpus(
    specs_path: str | Path,
    *,
    dataset_id: int,
    doc_id_base: int,
    chunks_out: str | Path,
    qrels_out: str | Path,
    report_out: str | Path | None = None,
    require_all_scenarios: bool = True,
) -> StructuredCorpusReport:
    specs = _read_jsonl(Path(specs_path))
    chunks: list[dict[str, Any]] = []
    qrels: list[dict[str, Any]] = []
    scenario_counts: Counter[str] = Counter()
    for doc_index, spec in enumerate(specs):
        doc_id = doc_id_base + doc_index
        sections = list(spec.get("sections") or [])
        if len(sections) < 2:
            raise ValueError(f"{spec.get('doc_key')} 必须至少包含两个 sections")
        chunk_by_ordinal: dict[int, str] = {}
        for ordinal, section in enumerate(sections):
            content = str(section.get("content") or "").strip()
            if not content:
                raise ValueError(f"{spec.get('doc_key')} section[{ordinal}] content 为空")
            chunk_id = eval_chunk_id(dataset_id, doc_id, ordinal)
            chunk_by_ordinal[ordinal] = chunk_id
            chunks.append(
                {
                    "dataset_id": dataset_id,
                    "doc_id": doc_id,
                    "ordinal": ordinal,
                    "content": content,
                    "content_hash": content_hash(content),
                    "chunk_id": chunk_id,
                    "metadata": {
                        "generator": "structured_eval_corpus_v1",
                        "doc_key": spec.get("doc_key"),
                        "domain": spec.get("domain"),
                        "heading": section.get("heading"),
                        "source_uri": spec.get("source_uri"),
                        "source_version": spec.get("source_version"),
                    },
                }
            )
        for question in spec.get("questions") or []:
            scenario = str(question.get("scenario") or "").strip()
            scenario_counts[scenario] += 1
            ordinals = sorted({int(value) for value in question.get("answer_ordinals") or []})
            if not ordinals or any(value not in chunk_by_ordinal for value in ordinals):
                raise ValueError(f"{question.get('id')} answer_ordinals 非法")
            query = str(question.get("query") or "").strip()
            provenance = QueryProvenance.from_dict(question["provenance"])
            qrels.append(
                {
                    "id": str(question["id"]),
                    "query": query,
                    "user_id": 990001,
                    "dataset_ids": [dataset_id],
                    "expected_chunk_ids": [chunk_by_ordinal[value] for value in ordinals],
                    "expected_doc_ids": [doc_id],
                    "golden_answer": question.get("golden_answer"),
                    "type": "cross_doc" if len(ordinals) > 1 else "keyword",
                    "note": f"structured_corpus_v1;type_hint={scenario}",
                    "relevance_grades": {
                        chunk_by_ordinal[value]: int(question.get("grade", 3)) for value in ordinals
                    },
                    "provenance": provenance.to_dict(),
                    "scenario": scenario,
                }
            )
    if require_all_scenarios:
        missing = sorted(REQUIRED_SCENARIOS - set(scenario_counts))
        if missing:
            raise ValueError(f"结构化语料缺少必需场景:{missing}")
    _write_jsonl(Path(chunks_out), chunks)
    _write_jsonl(Path(qrels_out), qrels)
    report = StructuredCorpusReport(
        documents=len(specs),
        chunks=len(chunks),
        queries=len(qrels),
        multi_positive_queries=sum(len(row["expected_chunk_ids"]) > 1 for row in qrels),
        scenario_counts=dict(sorted(scenario_counts.items())),
        dataset_id=dataset_id,
    )
    if report_out:
        path = Path(report_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
