"""run_opensource_golden 编排单测(fake indexer,不连活栈):

- 端到端:灌段落 → manifest → 转标注 → 写 golden,doc_id 由 doc_id_base 连号。
- skip_ingest:仅读已有 manifest 转换,不调 indexer。
"""

from __future__ import annotations

from linkrag_eval.golden.corpus_io import write_manifest, ManifestRecord
from linkrag_eval.golden.loader import load_golden
from linkrag_eval.golden.opensource.datasets import PassageCorpus, QueryJudgment
from linkrag_eval.runners import run_opensource_golden
from linkrag_eval.store.indexer import EvalPassage


class _FakeIndexer:
    def __init__(self):
        self.calls = []

    async def index_passages(self, dataset_id, passages):
        ps = list(passages)
        self.calls.append((dataset_id, ps))
        return len(ps)


def _data():
    corpus = PassageCorpus(passages={"p1": "正文一", "p2": "正文二", "p3": "正文三"})
    judgments = [
        QueryJudgment(qid="q1", query="问一", judged={"p1": 1}),
        QueryJudgment(qid="q2", query="问二", judged={"p2": 1, "p3": 1}),
        QueryJudgment(qid="q3", query="问三", judged={"pX": 1}),  # 正例未灌 → 跳过
    ]
    return corpus, judgments


class TestOpensourceRunner:
    async def test_end_to_end_ingest_and_convert(self, tmp_path):
        corpus, judgments = _data()
        indexer = _FakeIndexer()
        report = await run_opensource_golden(
            corpus, judgments,
            dataset_id=990201, user_id=990001, dataset_name="dur-pilot",
            indexer=indexer, manifest_path=tmp_path / "m.jsonl",
            golden_out=tmp_path / "golden.jsonl", doc_id_base=990300000,
        )
        assert report.ingested_docs == 3
        assert report.convert.converted == 2          # q1, q2
        assert report.convert.skipped_no_positive == 1  # q3
        golden = load_golden(tmp_path / "golden.jsonl")
        assert {g.id for g in golden} == {"dur-pilot-q1", "dur-pilot-q2"}
        # doc_id 连号映射:p1→base, p2→base+1
        q1 = next(g for g in golden if g.id == "dur-pilot-q1")
        assert q1.expected_doc_ids == [990300000]

    async def test_skip_ingest_reads_manifest(self, tmp_path):
        corpus, judgments = _data()
        # 预置 manifest(模拟语料已灌)
        write_manifest(
            [ManifestRecord("p1", 990300000, "success"),
             ManifestRecord("p2", 990300001, "success"),
             ManifestRecord("p3", 990300002, "success")],
            tmp_path / "m.jsonl",
        )
        indexer = _FakeIndexer()
        report = await run_opensource_golden(
            corpus, judgments,
            dataset_id=990201, user_id=990001, dataset_name="dur",
            indexer=indexer, manifest_path=tmp_path / "m.jsonl",
            golden_out=tmp_path / "g.jsonl", doc_id_base=990300000,
            skip_ingest=True,
        )
        assert indexer.calls == []          # 没碰 indexer
        assert report.ingested_docs == 3
        assert report.convert.converted == 2
