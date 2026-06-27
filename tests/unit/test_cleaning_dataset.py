"""清洗评测数据集准备单测:参考 md 归一化 + 对应关系表往返(搬迁自源 test_cleaning.py)。"""

from __future__ import annotations

from linkrag_eval.golden.cleaning_dataset.prepare import normalize_reference_md
from linkrag_eval.golden.cleaning_dataset.registry import (
    CleaningDoc,
    CleaningRegistry,
    RenderedDoc,
)


class TestPrepare:
    def test_strips_frontmatter_and_badge(self):
        raw = (
            "---\ntitle: x\n---\n"
            "[![build](https://img.shields.io/x.svg)](https://ci)\n\n"
            "# 真标题\n\n" + "正文内容很充实。" * 40
        )
        out = normalize_reference_md(raw)
        assert out is not None
        assert "title: x" not in out and "shields.io" not in out
        assert "# 真标题" in out

    def test_rejects_too_short(self):
        assert normalize_reference_md("# 标题\n短") is None

    def test_rejects_no_heading(self):
        assert normalize_reference_md("正文内容。" * 50) is None


class TestRegistryRoundtrip:
    def test_save_load_and_refs(self, tmp_path):
        reg = CleaningRegistry(
            docs=[CleaningDoc("d1", "chinese-markdown", str(tmp_path / "d1.md"), "h1")],
            rendered=[
                RenderedDoc("d1", "pdf", str(tmp_path / "d1.pdf"), "fh", "weasyprint", "x"),
                RenderedDoc("d1", "docx", str(tmp_path / "d1.docx"), "fh2", "python-docx", "y"),
            ],
        )
        reg.save(tmp_path / "manifest")
        loaded = CleaningRegistry.load(tmp_path / "manifest")
        assert loaded == reg

        refs = list(loaded.iter_rendered_refs(pdf_backends=["mineru", "naive"]))
        # PDF 件按 2 个 backend 展开 + docx 1 个 = 3
        assert len(refs) == 3
        pdf_backends = {r.pdf_backend for r in refs if r.fmt == "pdf"}
        assert pdf_backends == {"mineru", "naive"}
