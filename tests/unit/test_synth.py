"""Track B 单测：规格矩阵、事实/锚点、编织校验、渲染、回定位三档、QA 防泄漏、重定位。"""

from __future__ import annotations

import pytest

from linkrag_eval.golden.synth.compose import (
    DocumentComposer,
    check_anchors,
)
from linkrag_eval.golden.synth.facts import (
    FactUnit,
    deterministic_facts,
    load_facts,
    save_facts,
    validate_facts,
)
from linkrag_eval.golden.synth.locate import (
    TIER_EXACT,
    TIER_FUZZY,
    TIER_MISS,
    TIER_NORMALIZED,
    locate_facts,
    match_anchor,
    normalize,
)
from linkrag_eval.golden.synth.qa import QAGenerator, anchor_leaked
from linkrag_eval.golden.synth.relocate import relocate_samples
from linkrag_eval.golden.synth.render import render
from linkrag_eval.golden.synth.spec import DocSpec, default_matrix


def fact(anchor: str = "编号 ZX-204A 的组件额定值为 37 单位", fact_id: str = "f1") -> FactUnit:
    return FactUnit(
        fact_id=fact_id,
        statement=f"在测试中，{anchor}，超出需降载。",
        anchor=anchor,
        section_hint="第一节",
        answer="37 单位",
    )


class TestSpec:
    def test_default_matrix_covers_formats_and_backends(self):
        matrix = default_matrix()
        fmts = {s.fmt for s in matrix}
        assert fmts == {"md", "html", "docx", "pdf"}
        pdf_backends = {s.pdf_backend for s in matrix if s.fmt == "pdf"}
        assert {"mineru", "opendataloader", "naive"} <= pdf_backends
        assert any(s.length == "long" and s.fact_distribution == "cross_section" for s in matrix)

    def test_key_and_n_facts(self):
        s = DocSpec("pdf", "headings", "long", "scattered", "mineru")
        assert s.key == "pdfxmineru-headings-long-scattered"
        assert s.n_facts == 10


class TestFacts:
    def test_deterministic_facts_have_embedded_anchor(self):
        facts = deterministic_facts(DocSpec("md", "headings", "medium", "scattered"))
        assert len(facts) == 6
        for f in facts:
            assert f.anchor in f.statement

    def test_validate_rejects_nested_anchors(self):
        f1 = fact("编号 ZX-1 额定 10", "f1")
        f2 = fact("编号 ZX-1 额定 10 单位", "f2")  # 包含 f1 锚点
        assert validate_facts([f1, f2]) == [f1]

    def test_save_load_roundtrip(self, tmp_path):
        facts = [fact()]
        path = save_facts(facts, tmp_path / "facts.jsonl")
        assert load_facts(path) == facts


class FakeLLM:
    def __init__(self, outputs: list[str]):
        self.outputs = list(outputs)

    async def generate(self, prompt, system_prompt=None, temperature=0.7,
                       max_tokens=None, **kw):
        class R:
            pass

        r = R()
        r.content = self.outputs.pop(0)
        return r


class TestCompose:
    def test_check_anchors(self):
        f = fact()
        assert check_anchors(f"前文 {f.anchor} 后文", [f]) == []
        assert check_anchors("没有锚点的文本", [f]) == ["f1"]

    async def test_composer_retries_until_anchor_present(self):
        f = fact()
        llm = FakeLLM(["缺锚点的初稿", f"# 文档\n\n{f.anchor} 出现了。"])
        composer = DocumentComposer(llm, "compose-m", max_retries=1)
        result = await composer.compose(
            DocSpec("md", "headings", "short", "concentrated"), "测试", [f]
        )
        assert result.missing_anchors == []
        assert result.planted_facts == [f]

    async def test_composer_reports_missing(self):
        f = fact()
        llm = FakeLLM(["没有", "还是没有"])
        composer = DocumentComposer(llm, "m", max_retries=1)
        result = await composer.compose(
            DocSpec("md", "headings", "short", "concentrated"), "测试", [f]
        )
        assert result.missing_anchors == ["f1"]
        assert result.planted_facts == []


class TestRender:
    def test_md_passthrough(self):
        content, suffix = render("md", "# 标题\n\n正文")
        assert suffix == ".md" and "标题".encode() in content

    def test_html_contains_body(self):
        content, suffix = render("html", "# 标题\n\n正文段落", title="t")
        text = content.decode()
        assert suffix == ".html"
        assert "标题" in text and "正文段落" in text
        assert text.startswith("<!DOCTYPE html>")

    def test_unknown_format(self):
        with pytest.raises(ValueError, match="不支持"):
            render("rtf", "x")


class TestLocate:
    def test_exact(self):
        assert match_anchor("额定功率 3.7 千瓦", "本设备额定功率 3.7 千瓦运行") == TIER_EXACT

    def test_normalized_fullwidth_and_spaces(self):
        # 解析改写：全角数字、空白差异 → 归一化命中
        assert (
            match_anchor("额定功率 3.7 千瓦", "额定功率３.７千  瓦（注）") == TIER_NORMALIZED
        )

    def test_fuzzy_single_char_loss(self):
        anchor = "编号 ZX-204A 的组件额定值为 37 单位"
        mangled = "编号 ZX204A 的组件额值为 37 单位"  # 解析丢一字
        assert match_anchor(anchor, f"前文。{mangled}。后文") in (TIER_FUZZY, TIER_NORMALIZED)

    def test_miss(self):
        assert match_anchor("完全不存在的锚点串 XYZW-99", "无关内容") == TIER_MISS

    def test_normalize_nfkc(self):
        assert normalize("ＡＢＣ １２３") == "abc123"

    def test_locate_multi_chunk_takes_all(self):
        f = fact()
        chunks = {
            "c1": f"上半句 {f.anchor}",
            "c2": f"{f.anchor} 下半句",  # 事实切到边界 → 双命中
            "c3": "无关",
        }
        report = locate_facts([f], chunks, bucket="md")
        assert report.results[0].chunk_ids == ["c1", "c2"]
        assert report.results[0].tier == TIER_EXACT

    def test_miss_bucketed(self):
        f = fact("绝不出现的锚点 QQQ-000")
        report = locate_facts([f], {"c1": "无关"}, bucket="pdf×mineru")
        assert report.miss_by_bucket == {"pdf×mineru": 1}
        assert report.miss_rate == 1.0
        assert "pdf×mineru" in report.summary()


class TestQA:
    def test_anchor_leak_detection(self):
        anchor = "编号 ZX-204A 的组件额定值为 37 单位"
        assert anchor_leaked("ZX-204A 的额定值是多少", anchor)  # ngram 片段泄漏
        assert not anchor_leaked("该组件超载时应如何处理", anchor)

    async def test_generates_and_blocks_leak(self):
        f = fact()
        from linkrag_eval.golden.synth.locate import LocateResult

        located = LocateResult(fact_id="f1", chunk_ids=["c1"], tier=TIER_EXACT)
        llm = FakeLLM(
            ['{"query": "编号 ZX-204A 的额定值是多少"}', '{"query": "该组件的额定值是多少"}']
        )
        gen = QAGenerator(
            client=llm, qa_model="qa-m", user_id=990001, dataset_id=990102,
            doc_id=990000020, max_retries=1,
        )
        sample = await gen.generate_one(f, located)
        assert sample is not None
        assert not anchor_leaked(sample.query, f.anchor)
        assert sample.golden_answer == "37 单位"
        assert sample.expected_chunk_ids == ["c1"]
        assert "fact_id=f1" in sample.note

    async def test_unlocated_returns_none(self):
        from linkrag_eval.golden.synth.locate import LocateResult

        gen = QAGenerator(
            client=FakeLLM([]), qa_model="m", user_id=1, dataset_id=1, doc_id=1,
        )
        assert await gen.generate_one(fact(), LocateResult(fact_id="f1")) is None


class TestRelocate:
    async def test_rebuilds_chunk_ids_after_rechunk(self):
        f = fact()
        from linkrag_eval.golden.synth.locate import LocateResult

        llm = FakeLLM(['{"query": "该组件的额定值是多少"}'])
        gen = QAGenerator(
            client=llm, qa_model="m", user_id=990001, dataset_id=990102, doc_id=77,
        )
        sample = await gen.generate_one(
            f, LocateResult(fact_id="f1", chunk_ids=["old-c1"], tier=TIER_EXACT)
        )
        new_chunks = {77: {"new-c9": f"重分块后的正文 {f.anchor} 仍在"}}
        relocated, report = relocate_samples([sample], {"f1": f}, new_chunks)
        assert report.relocated == 1
        assert relocated[0].expected_chunk_ids == ["new-c9"]
        assert relocated[0].id == sample.id  # 其余字段保留

    async def test_lost_when_anchor_gone(self):
        f = fact()
        from linkrag_eval.golden.synth.locate import LocateResult

        llm = FakeLLM(['{"query": "该组件的额定值是多少"}'])
        gen = QAGenerator(
            client=llm, qa_model="m", user_id=990001, dataset_id=990102, doc_id=77,
        )
        sample = await gen.generate_one(
            f, LocateResult(fact_id="f1", chunk_ids=["old-c1"], tier=TIER_EXACT)
        )
        relocated, report = relocate_samples(
            [sample], {"f1": f}, {77: {"c": "锚点不在了"}}
        )
        assert relocated == []
        assert report.lost == [sample.id]
        assert "丢失" in report.summary()
