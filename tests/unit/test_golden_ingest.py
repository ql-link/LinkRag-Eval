"""灌库编排单测(注入 fake indexer/computer/parser,不碰活栈):

- opensource.ingest_passages:段落→doc_id 映射、manifest 落盘、批级容错。
- synth.ingest_and_locate:渲染→解析→分块→灌库→锚点回定位链路。
"""

from __future__ import annotations

from linkrag_eval.compute.protocol import EvalChunk
from linkrag_eval.golden.corpus_io import load_manifest
from linkrag_eval.golden.opensource.datasets import PassageCorpus
from linkrag_eval.golden.opensource.ingest import ingest_passages
from linkrag_eval.golden.synth.compose import ComposeResult
from linkrag_eval.golden.synth.facts import FactUnit
from linkrag_eval.golden.synth.ingest import ingest_and_locate
from linkrag_eval.golden.synth.spec import DocSpec
from linkrag_eval.store.ids import eval_chunk_id
from linkrag_eval.store.indexer import EvalPassage


class _FakeIndexer:
    """记录每次 index_passages 的入参;可设 fail_once 模拟批级重试。"""

    def __init__(self, *, fail_first_batch: bool = False):
        self.calls: list[tuple[int, list[EvalPassage]]] = []
        self._fail_first = fail_first_batch

    async def index_passages(self, dataset_id, passages):
        if self._fail_first and not self.calls:
            self.calls.append((dataset_id, list(passages)))  # 记录失败的那次
            raise RuntimeError("transient 502")
        self.calls.append((dataset_id, list(passages)))
        return len(list(passages))


class TestOpensourceIngest:
    async def test_maps_passages_and_writes_manifest(self, tmp_path):
        corpus = PassageCorpus(passages={"p1": "正文一", "p2": "正文二", "p3": "正文三"})
        indexer = _FakeIndexer()
        manifest = tmp_path / "manifest.jsonl"
        records = await ingest_passages(
            corpus, dataset_id=990101, indexer=indexer,
            manifest_path=manifest, doc_id_base=990000000, batch=2,
        )
        assert [r.status for r in records] == ["success"] * 3
        assert [r.doc_id for r in records] == [990000000, 990000001, 990000002]
        # 落盘可被 load_manifest 读回
        loaded = load_manifest(manifest)
        assert {r.source_id for r in loaded} == {"p1", "p2", "p3"}
        # 2+1 两批
        assert len(indexer.calls) == 2

    async def test_limit_caps_passages(self, tmp_path):
        corpus = PassageCorpus(passages={f"p{i}": f"t{i}" for i in range(10)})
        records = await ingest_passages(
            corpus, dataset_id=1, indexer=_FakeIndexer(),
            manifest_path=tmp_path / "m.jsonl", doc_id_base=100, limit=3,
        )
        assert len(records) == 3

    async def test_batch_retry_then_success(self, tmp_path):
        corpus = PassageCorpus(passages={"p1": "a", "p2": "b"})
        indexer = _FakeIndexer(fail_first_batch=True)
        records = await ingest_passages(
            corpus, dataset_id=1, indexer=indexer,
            manifest_path=tmp_path / "m.jsonl", doc_id_base=10, batch=10, retries=3,
        )
        assert [r.status for r in records] == ["success", "success"]


class _FakeComputer:
    """compute_chunks 把文本按行切成 EvalChunk(ordinal 递增)。"""

    async def compute_chunks(self, text, *, source_file=None):
        lines = [ln for ln in text.splitlines() if ln.strip()]
        return [EvalChunk(content=ln, ordinal=i) for i, ln in enumerate(lines)]


def _fake_parse(path, fmt, pdf_backend):
    # 模拟 parser:直接读回渲染件文本(md/html 等已是文本)
    return path.read_text(encoding="utf-8")


class TestSynthIngest:
    def _composed(self) -> ComposeResult:
        facts = [
            FactUnit("f1", "锚点甲 ZX-1 出现在此句中。", "锚点甲 ZX-1", "第一节", "答1"),
            FactUnit("f2", "锚点乙 ZX-2 出现在此句中。", "锚点乙 ZX-2", "第二节", "答2"),
        ]
        markdown = "锚点甲 ZX-1 出现在此句中。\n锚点乙 ZX-2 出现在此句中。\n"
        spec = DocSpec("md", "headings", "short", "scattered")
        return ComposeResult(markdown=markdown, spec=spec, facts=facts, missing_anchors=[])

    async def test_ingest_locates_facts_to_chunks(self):
        indexer = _FakeIndexer()
        result = await ingest_and_locate(
            self._composed(), dataset_id=7, doc_id=700,
            indexer=indexer, computer=_FakeComputer(), parse_fn=_fake_parse,
        )
        assert result.record.status == "success"
        assert result.record.doc_id == 700
        assert result.bucket == "md"
        # 两个事实各定位到一个 chunk(确定性 chunk_id)
        located = result.locate_report.located
        assert len(located) == 2
        cid0 = eval_chunk_id(7, 700, 0)
        assert cid0 in result.chunks
        assert any(cid0 in r.chunk_ids for r in located)

    async def test_render_or_parse_failure_marks_failed(self):
        def boom_parse(path, fmt, pdf_backend):
            raise RuntimeError("parser crashed")

        result = await ingest_and_locate(
            self._composed(), dataset_id=7, doc_id=700,
            indexer=_FakeIndexer(), computer=_FakeComputer(), parse_fn=boom_parse,
        )
        assert result.record.status == "failed"
        assert result.chunks == {}
