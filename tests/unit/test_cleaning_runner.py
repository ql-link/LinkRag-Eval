"""run_cleaning 编排单测:注入 fake evaluable(不碰 rag parser),验证比对+分桶链路。"""

from __future__ import annotations

from linkrag_eval.cleaning.adapter import RenderedRef
from linkrag_eval.models import CleaningPair, Layer, StageOutput
from linkrag_eval.runners.cleaning_runner import run_cleaning

REF = "# 标题\n正文一。\n\n## 小节\n正文二。\n"


class _FakeEvaluable:
    """按 sample_id 回放预设 produced md,绕开 ParserFactory 活栈。"""

    layer = Layer.CLEANING

    def __init__(self, produced_by_id: dict[str, str]):
        self._by_id = produced_by_id

    async def run(self, rendered: RenderedRef, *, upstream=None) -> StageOutput:
        produced = self._by_id[rendered.sample_id]
        return StageOutput(
            layer=self.layer,
            query=rendered.sample_id,
            ranked=[],
            elapsed_ms=12,
            raw=CleaningPair(ref=REF, produced=produced, ok=True),
        )


def _ref(sample_id: str, fmt: str, backend: str | None = None) -> RenderedRef:
    return RenderedRef(
        sample_id=sample_id, fmt=fmt, rendered_path="/x", md_ref_path="/y", pdf_backend=backend
    )


async def test_run_cleaning_buckets_and_details() -> None:
    refs = [_ref("a", "pdf", "mineru"), _ref("b", "pdf", "mineru"), _ref("c", "docx")]
    evaluable = _FakeEvaluable({"a": REF, "b": REF, "c": REF})  # 完美清洗

    report, items = await run_cleaning(refs, evaluable, run_id="run-1")

    assert len(items) == 3
    assert {it.sample_id for it in items} == {"a", "b", "c"}
    buckets = {(b.format, b.pdf_backend): b for b in report.buckets}
    assert buckets[("pdf", "mineru")].n == 2
    assert buckets[("docx", None)].n == 1
    # 完美清洗 → 文本完整性满分进聚合
    assert buckets[("docx", None)].metrics["text_completeness"] == 1.0


async def test_run_cleaning_propagates_degraded_quality() -> None:
    refs = [_ref("a", "md")]
    evaluable = _FakeEvaluable({"a": "# 标题\n正文一。\n"})  # 漏了「正文二」+小节

    report, items = await run_cleaning(refs, evaluable, run_id="run-2")

    assert items[0].text.completeness < 1.0
    assert report.buckets[0].metrics["text_completeness"] < 1.0
