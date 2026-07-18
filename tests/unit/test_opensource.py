"""Track A:数据集解析 + 标注转换单测(小 fixture,无网络无 DB)。

搬迁自源仓库 test_opensource.py;manifest 改用 eval ``ManifestRecord``,convert 的
``dataset_id``/``user_id`` 改为显式传参(解耦改动,见 convert.py docstring)。
"""

from __future__ import annotations

import json

import pytest

from linkrag_eval.golden.corpus_io import ManifestRecord
from linkrag_eval.golden.loader import load_golden
from linkrag_eval.golden.opensource import (
    convert_to_golden,
    load_dureader_retrieval,
    load_t2ranking,
)
from linkrag_eval.golden.opensource.convert import write_golden_jsonl

_DATASET_ID = 990101
_USER_ID = 990001


def make_record(pid: str, doc_id: int, status: str = "success") -> ManifestRecord:
    return ManifestRecord(source_id=pid, doc_id=doc_id, status=status)


def _convert(judgments, manifest, **kw):
    return convert_to_golden(
        judgments, manifest, dataset_id=_DATASET_ID, user_id=_USER_ID, **kw
    )


@pytest.fixture
def t2_files(tmp_path):
    (tmp_path / "collection.tsv").write_text(
        "p1\t向量检索基于稠密向量近邻搜索。\np2\tBM25 是经典词法检索算法。\n",
        encoding="utf-8",
    )
    (tmp_path / "queries.tsv").write_text(
        "q1\t什么是向量检索\nq2\tBM25 原理\n", encoding="utf-8"
    )
    (tmp_path / "qrels.tsv").write_text(
        "q1\t0\tp1\t3\nq1\t0\tp2\t0\nq2\t0\tp2\t2\n", encoding="utf-8"
    )
    return tmp_path


class TestT2Ranking:
    def test_load(self, t2_files):
        corpus, judgments = load_t2ranking(
            t2_files / "collection.tsv", t2_files / "queries.tsv", t2_files / "qrels.tsv"
        )
        assert len(corpus) == 2
        assert len(judgments) == 2
        j1 = judgments[0]
        assert j1.query == "什么是向量检索"
        assert j1.judged == {"p1": 3, "p2": 0}
        assert j1.positive_pids == ["p1"]  # grade 0 不算正例

    def test_duplicate_pid_rejected(self, t2_files):
        (t2_files / "collection.tsv").write_text("p1\ta\np1\tb\n", encoding="utf-8")
        with pytest.raises(ValueError, match="重复"):
            load_t2ranking(
                t2_files / "collection.tsv", t2_files / "queries.tsv", t2_files / "qrels.tsv"
            )

    def test_bad_qrels_line(self, t2_files):
        (t2_files / "qrels.tsv").write_text("q1\tp1\n", encoding="utf-8")
        with pytest.raises(ValueError, match="qrels"):
            load_t2ranking(
                t2_files / "collection.tsv", t2_files / "queries.tsv", t2_files / "qrels.tsv"
            )


class TestDuReader:
    def test_json_qrels(self, tmp_path):
        (tmp_path / "collection.tsv").write_text("p1\t正文一\np2\t正文二\n", encoding="utf-8")
        (tmp_path / "queries.tsv").write_text("q1\t问题一\n", encoding="utf-8")
        (tmp_path / "qrels.json").write_text(
            json.dumps({"q1": ["p1", "p2"]}), encoding="utf-8"
        )
        _, judgments = load_dureader_retrieval(
            tmp_path / "collection.tsv", tmp_path / "queries.tsv", tmp_path / "qrels.json"
        )
        assert judgments[0].judged == {"p1": 1, "p2": 1}


class TestConvert:
    def test_binary_conversion(self):
        from linkrag_eval.golden.opensource.datasets import QueryJudgment

        judgments = [QueryJudgment(qid="q1", query="问题一", judged={"p1": 1, "p2": 1})]
        manifest = [make_record("p1", 990000010), make_record("p2", 990000012)]
        samples, report = _convert(judgments, manifest, dataset_name="dureader")
        assert report.converted == 1
        s = samples[0]
        assert s.id == "dureader-q1"
        assert s.expected_doc_ids == [990000010, 990000012]
        assert s.expected_chunk_ids == []
        assert s.relevance_grades is None
        assert s.user_id == 990001

    def test_binary_conversion_chunk_granularity(self):
        from linkrag_eval.golden.opensource.datasets import QueryJudgment

        judgments = [QueryJudgment(qid="q1", query="问题一", judged={"p1": 1, "p2": 1})]
        manifest = [make_record("p1", 990000010), make_record("p2", 990000012)]
        samples, report = _convert(
            judgments,
            manifest,
            dataset_name="dureader",
            reference_granularity="chunk",
            chunks_by_doc={
                990000010: ["c10a", "c10b"],
                990000012: ["c12a"],
            },
        )
        assert report.converted == 1
        assert report.reference_granularity == "chunk"
        s = samples[0]
        assert s.expected_doc_ids == [990000010, 990000012]
        assert s.expected_chunk_ids == ["c10a", "c10b", "c12a"]

    def test_graded_conversion(self):
        from linkrag_eval.golden.opensource.datasets import QueryJudgment

        judgments = [QueryJudgment(qid="q1", query="问", judged={"p1": 3, "p2": 0})]
        manifest = [make_record("p1", 990000010), make_record("p2", 990000012)]
        samples, _ = _convert(judgments, manifest, dataset_name="t2", graded=True)
        assert samples[0].relevance_grades == {"990000010": 3}

    def test_graded_conversion_chunk_granularity(self):
        from linkrag_eval.golden.opensource.datasets import QueryJudgment

        judgments = [QueryJudgment(qid="q1", query="问", judged={"p1": 3, "p2": 0})]
        manifest = [make_record("p1", 990000010), make_record("p2", 990000012)]
        samples, _ = _convert(
            judgments,
            manifest,
            dataset_name="t2",
            graded=True,
            reference_granularity="chunk",
            chunks_by_doc={990000010: ["c10a", "c10b"], 990000012: ["c12a"]},
        )
        assert samples[0].expected_chunk_ids == ["c10a", "c10b"]
        assert samples[0].relevance_grades == {"c10a": 3, "c10b": 3}

    def test_chunk_conversion_skips_when_no_chunks(self):
        from linkrag_eval.golden.opensource.datasets import QueryJudgment

        judgments = [QueryJudgment(qid="q1", query="问", judged={"p1": 1})]
        manifest = [make_record("p1", 990000010)]
        samples, report = _convert(
            judgments,
            manifest,
            dataset_name="d",
            reference_granularity="chunk",
            chunks_by_doc={990000010: []},
        )
        assert samples == []
        assert report.skipped_no_chunks == 1

    def test_skip_when_no_positive_ingested(self):
        from linkrag_eval.golden.opensource.datasets import QueryJudgment

        judgments = [QueryJudgment(qid="q1", query="问", judged={"p9": 1})]
        samples, report = _convert(judgments, [], dataset_name="d")
        assert samples == []
        assert report.skipped_no_positive == 1
        assert report.dropped_pids == ["p9"]

    def test_failed_ingest_excluded(self):
        from linkrag_eval.golden.opensource.datasets import QueryJudgment

        judgments = [QueryJudgment(qid="q1", query="问", judged={"p1": 1, "p2": 1})]
        manifest = [make_record("p1", 990000010), make_record("p2", -1, status="failed")]
        samples, report = _convert(judgments, manifest, dataset_name="d")
        assert samples[0].expected_doc_ids == [990000010]
        assert report.skipped_partial_missing == 1
        assert "missing_pids" in samples[0].note

    def test_jsonl_roundtrip_loadable(self, tmp_path):
        from linkrag_eval.golden.opensource.datasets import QueryJudgment

        judgments = [QueryJudgment(qid="q1", query="问", judged={"p1": 2})]
        manifest = [make_record("p1", 990000010)]
        samples, _ = _convert(judgments, manifest, dataset_name="t2", graded=True)
        path = write_golden_jsonl(samples, tmp_path / "golden" / "t2.jsonl")
        loaded = load_golden(path)
        assert loaded[0].relevance_grades == {"990000010": 2}
