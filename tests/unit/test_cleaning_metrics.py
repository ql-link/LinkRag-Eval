"""数据清洗质检指标单测(纯函数、进 PR 门禁):md 块解析 + 各专项口径 + 聚合。

搬迁自源仓库 test_cleaning.py 的指标部分;cleaning_dataset 的 prepare/registry 测试随
那部分 golden 生成代码后续迁移,本文件只覆盖 metrics/cleaning.py。
"""

from __future__ import annotations

from linkrag_eval.metrics import cleaning as M
from linkrag_eval.models import CleaningPair

REF = """# 标题一
正文段落一，介绍背景。

## 小节 A
正文段落二，包含关键数据。

| 名称 | 值 |
| --- | --- |
| 甲 | 1 |
| 乙 | 2 |

![图1](img/a.png)

- 项目一
- 项目二
"""


class TestParseBlocks:
    def test_block_kinds(self):
        blocks = M.parse_blocks(REF)
        kinds = [b.kind for b in blocks]
        assert kinds.count("heading") == 2
        assert "table" in kinds and "image" in kinds and "list" in kinds
        headings = [b for b in blocks if b.kind == "heading"]
        assert (headings[0].level, headings[1].level) == (1, 2)

    def test_table_rows_parsed(self):
        table = next(b for b in M.parse_blocks(REF) if b.kind == "table")
        rows = table.meta["rows"]
        assert rows[0] == ["名称", "值"]
        assert ["甲", "1"] in rows

    def test_json_code_block(self):
        blocks = M.parse_blocks('```json\n[{"a": 1}]\n```')
        assert blocks[0].kind == "code" and blocks[0].meta["lang"] == "json"


class TestIdentity:
    """参考 == 产出：各项应接近满分（清洗无失真的上界）。"""

    def test_perfect_scores(self):
        item = M.score_pair(CleaningPair(ref=REF, produced=REF), sample_id="d1", fmt="md")
        assert item.text.completeness == 1.0
        assert item.heading.recall == 1.0 and item.heading.level_consistency_abs == 1.0
        assert item.table.md_cell_f1 == 1.0
        assert item.image.recall == 1.0 and item.image.context_position_ok == 1.0
        assert item.list_fidelity == 1.0 and item.order_fidelity == 1.0
        assert item.table.mode_dist == {"md": 1, "image": 0, "json": 0}


class TestHeading:
    def test_missed_heading(self):
        produced = REF.replace("## 小节 A\n", "")  # 漏识别一个标题
        h = M.heading_scores(M.parse_blocks(REF), M.parse_blocks(produced))
        assert h.recall == 0.5
        assert "小节 A" in h.missed[0]

    def test_level_shift_uniform(self):
        # 全体层级 +1：绝对一致差，相对结构一致仍为 1（同构、统一偏移）
        produced = REF.replace("# 标题一", "## 标题一").replace("## 小节 A", "### 小节 A")
        h = M.heading_scores(M.parse_blocks(REF), M.parse_blocks(produced))
        assert h.level_consistency_abs == 0.0
        assert h.level_consistency_rel == 1.0

    def test_false_heading(self):
        produced = REF + "\n# 多出来的标题\n"
        h = M.heading_scores(M.parse_blocks(REF), M.parse_blocks(produced))
        assert h.false_rate > 0


class TestText:
    def test_noise_from_extra_content(self):
        produced = REF + "\n页眉页脚水印乱码内容混入文本。\n"
        t = M.text_scores(M.parse_blocks(REF), M.parse_blocks(produced))
        assert t.completeness == 1.0
        assert t.noise > 0

    def test_completeness_drop_on_missing_text(self):
        produced = REF.replace("正文段落二，包含关键数据。", "")
        t = M.text_scores(M.parse_blocks(REF), M.parse_blocks(produced))
        assert t.completeness < 1.0


class TestTableModes:
    def test_mode_image(self):
        produced = REF.replace(
            "| 名称 | 值 |\n| --- | --- |\n| 甲 | 1 |\n| 乙 | 2 |",
            "![表格图](img/t.png)",
        )
        t = M.table_scores(M.parse_blocks(REF), M.parse_blocks(produced))
        assert t.mode_dist["image"] == 1
        assert t.md_cell_f1 is None
        assert t.image_position_ok == 1.0  # 锚点位置对

    def test_mode_json(self):
        produced = REF.replace(
            "| 名称 | 值 |\n| --- | --- |\n| 甲 | 1 |\n| 乙 | 2 |",
            '```json\n[{"名称": "甲", "值": "1"}, {"名称": "乙", "值": "2"}]\n```',
        )
        t = M.table_scores(M.parse_blocks(REF), M.parse_blocks(produced))
        assert t.mode_dist["json"] == 1
        assert t.json_corr_f1 == 1.0

    def test_mode_md_cell_mismatch(self):
        produced = REF.replace("| 乙 | 2 |", "| 乙 | 9 |")  # 单元格值错
        t = M.table_scores(M.parse_blocks(REF), M.parse_blocks(produced))
        assert t.mode_dist["md"] == 1
        assert 0 < t.md_cell_f1 < 1.0


class TestImage:
    def test_misplaced_image(self):
        # 图片漂到文首（上下文锚点全变）
        produced = "![图1](img/a.png)\n\n" + REF.replace("![图1](img/a.png)\n\n", "")
        img = M.image_scores(M.parse_blocks(REF), M.parse_blocks(produced))
        assert img.recall == 1.0
        assert img.context_position_ok < 1.0

    def test_missing_image(self):
        produced = REF.replace("![图1](img/a.png)\n\n", "")
        img = M.image_scores(M.parse_blocks(REF), M.parse_blocks(produced))
        assert img.recall == 0.0


class TestListOrderStability:
    def test_list_fidelity_item_loss(self):
        produced = REF.replace("- 项目二\n", "")
        assert M.list_fidelity(M.parse_blocks(REF), M.parse_blocks(produced)) < 1.0

    def test_order_inversion(self):
        blocks_ref = M.parse_blocks("# A\n\n正文甲\n\n正文乙")
        blocks_prod = M.parse_blocks("正文乙\n\n正文甲\n\n# A")
        assert M.order_fidelity(blocks_ref, blocks_prod) < 1.0

    def test_stability_identical_runs(self):
        assert M.stability(["abc", "abc", "abc"]) == 1.0

    def test_stability_divergent_runs(self):
        assert M.stability(["abc", "abd"]) < 1.0

    def test_stability_single_run(self):
        assert M.stability(["abc"]) == 1.0


class TestAggregate:
    def _item(self, fmt, backend, clean_ms, completeness):
        return M.score_pair(
            CleaningPair(ref=REF, produced=REF),
            sample_id=f"{fmt}-{clean_ms}", fmt=fmt, pdf_backend=backend, clean_ms=clean_ms,
        )

    def test_bucketing_and_percentile(self):
        items = [
            self._item("pdf", "mineru", 1000, 1.0),
            self._item("pdf", "mineru", 3000, 1.0),
            self._item("docx", None, 150, 1.0),
        ]
        report = M.aggregate(items, run_id="run-x")
        buckets = {(b.format, b.pdf_backend): b for b in report.buckets}
        assert buckets[("pdf", "mineru")].n == 2
        assert buckets[("pdf", "mineru")].metrics["clean_ms_p50"] in (1000, 3000)
        assert buckets[("docx", None)].n == 1

