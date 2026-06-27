"""golden 加载/schema/precheck:纯函数,不需 rag。"""

from __future__ import annotations

import json

import pytest

from linkrag_eval.golden import GoldenSample, load_golden, precheck
from linkrag_eval.models import QuestionType


def _write(tmp_path, rows) -> str:
    p = tmp_path / "g.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return str(p)


def test_load_doc_granularity(tmp_path) -> None:
    path = _write(tmp_path, [
        {"id": "q1", "query": "问题1", "user_id": 990001, "dataset_ids": [990131],
         "expected_doc_ids": [991310000], "type": "paraphrase"},
    ])
    [s] = load_golden(path)
    assert s.id == "q1" and s.expected_doc_ids == [991310000]
    assert s.type == QuestionType.PARAPHRASE
    assert s.expected_chunk_ids == []


def test_reject_no_reference(tmp_path) -> None:
    path = _write(tmp_path, [
        {"id": "q1", "query": "q", "user_id": 1, "dataset_ids": [1]},  # 既无 chunk 也无 doc
    ])
    with pytest.raises(ValueError, match="至少填一个"):
        load_golden(path)


def test_reject_duplicate_id(tmp_path) -> None:
    path = _write(tmp_path, [
        {"id": "q1", "query": "q", "user_id": 1, "dataset_ids": [1], "expected_doc_ids": [1]},
        {"id": "q1", "query": "q", "user_id": 1, "dataset_ids": [1], "expected_doc_ids": [2]},
    ])
    with pytest.raises(ValueError, match="id 重复"):
        load_golden(path)


def test_roundtrip() -> None:
    s = GoldenSample(id="q", query="问", user_id=1, dataset_ids=[1], expected_chunk_ids=["c1"])
    assert GoldenSample.from_dict(json.loads(s.to_jsonl_line())) == s


async def test_precheck_missing_with_doc_fallback() -> None:
    samples = [
        GoldenSample(id="q1", query="q", user_id=1, dataset_ids=[1],
                     expected_chunk_ids=["c1", "c2"], expected_doc_ids=[10]),
    ]

    async def fetch_status(chunk_ids):
        return {"c1": "ACTIVE"}  # c2 缺失

    rep = await precheck(samples, fetch_status)
    assert not rep.ok
    assert rep.missing == {"q1": ["c2"]}
    assert "q1" in rep.doc_fallback_available


async def test_precheck_all_present() -> None:
    samples = [GoldenSample(id="q1", query="q", user_id=1, dataset_ids=[1], expected_chunk_ids=["c1"])]

    async def fetch_status(chunk_ids):
        return {c: "ACTIVE" for c in chunk_ids}

    rep = await precheck(samples, fetch_status)
    assert rep.ok and rep.checked_chunk_ids == 1
