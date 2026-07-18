"""Golden V2 judgments → GoldenSample 构建器。"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from linkrag_eval.golden.schema import GoldenSample
from linkrag_eval.models import QuestionType


@dataclass(frozen=True)
class GoldenV2BuildReport:
    total_queries: int
    written: dict[str, int]
    unresolved: int
    out_dir: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        return (
            f"Golden V2 构建完成: queries={self.total_queries} written={self.written} "
            f"unresolved={self.unresolved}"
        )


def build_golden_from_judgments(
    judgment_paths: Iterable[str | Path],
    *,
    out_dir: str | Path,
    user_id: int,
    tune_ratio: float = 0.70,
) -> GoldenV2BuildReport:
    judgments: list[dict[str, Any]] = []
    for path in judgment_paths:
        judgments.extend(_read_jsonl(Path(path), label="judgments"))
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in judgments:
        grouped[str(row["query_id"])].append(row)

    buckets: dict[str, list[GoldenSample]] = {
        "realistic_tune": [],
        "realistic_blind": [],
        "hard_tune": [],
        "hard_blind": [],
    }
    unresolved_rows: list[dict[str, Any]] = []
    for query_id, rows in sorted(grouped.items()):
        positives = [r for r in rows if r.get("relevant") and int(r.get("grade", 1)) > 0]
        if not positives:
            unresolved_rows.append({"query_id": query_id, "query": rows[0].get("query"), "role": rows[0].get("role")})
            continue
        role = "hard" if rows[0].get("role") == "hard" else "realistic"
        split = _split(query_id, tune_ratio=tune_ratio)
        chunk_ids = sorted({str(r["candidate"]["chunk_id"]) for r in positives})
        doc_ids = sorted({int(r["candidate"]["doc_id"]) for r in positives})
        dataset_ids = sorted({int(r["candidate"]["dataset_id"]) for r in positives})
        grades = {
            str(r["candidate"]["chunk_id"]): int(r.get("grade", 1))
            for r in positives
        }
        note = (
            f"role={role}; split={split}; source={rows[0].get('source') or ''}; "
            f"type_hint={rows[0].get('type_hint') or ''}; hard_reason={rows[0].get('hard_reason') or ''}"
        )
        sample = GoldenSample(
            id=query_id,
            query=str(rows[0]["query"]),
            user_id=user_id,
            dataset_ids=dataset_ids,
            expected_chunk_ids=chunk_ids,
            expected_doc_ids=doc_ids,
            type=_question_type(rows[0].get("type_hint"), role=role),
            note=note,
            relevance_grades=grades,
        )
        buckets[f"{role}_{split}"].append(sample)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: dict[str, int] = {}
    for name, samples in buckets.items():
        path = out / f"{name}.jsonl"
        _write_golden(path, samples)
        written[name] = len(samples)
    _write_jsonl(out / "unresolved.jsonl", unresolved_rows)
    report = GoldenV2BuildReport(
        total_queries=len(grouped),
        written=written,
        unresolved=len(unresolved_rows),
        out_dir=str(out),
    )
    (out / "build_report.json").write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def _split(query_id: str, *, tune_ratio: float) -> str:
    if not 0 < tune_ratio < 1:
        raise ValueError("tune_ratio 必须在 0 和 1 之间")
    value = int(hashlib.sha256(query_id.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "tune" if value < tune_ratio else "blind"


def _question_type(raw: Any, *, role: str) -> QuestionType:
    value = str(raw or "").strip()
    if value in {item.value for item in QuestionType}:
        return QuestionType(value)
    if role == "hard":
        return QuestionType.LONGTAIL
    return QuestionType.PARAPHRASE


def _read_jsonl(path: Path, *, label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno} {label} JSONL 非法:{exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{lineno} {label} 行必须是 object")
            rows.append(row)
    return rows


def _write_golden(path: Path, samples: list[GoldenSample]) -> None:
    path.write_text("".join(s.to_jsonl_line() + "\n" for s in samples), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
