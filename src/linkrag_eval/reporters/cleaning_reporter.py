"""数据清洗质检 HTML 报告：逐 (格式×PDF后端) 出表，分标题/表格/图片/清洗时间四区。

与 .specs/rag-quality-eval/templates/cleaning_report_template.html 同源风格；
引擎不依赖 git-ignored 的 .specs，故复用 html_reporter 的 _CSS / _esc。
"""

from __future__ import annotations

from datetime import datetime

from linkrag_eval.models import CleaningBucket, CleaningQcReport
from linkrag_eval.reporters.html_reporter import _CSS, _esc

_SMALL_BUCKET_N = 15


def _bucket_label(b: CleaningBucket) -> str:
    return f"{b.format} / {b.pdf_backend}" if b.pdf_backend else b.format


def _cell(b: CleaningBucket, key: str, *, pct: bool = False, suffix: str = "") -> str:
    if key not in b.metrics:
        return "<td>—</td>"
    v = b.metrics[key]
    text = f"{v * 100:.0f}%" if pct else f"{v:.2f}{suffix}"
    return f"<td>{text}</td>"


class CleaningHtmlReporter:
    def __init__(self, *, dataset: str = "default"):
        self.dataset = dataset

    def render(self, report: CleaningQcReport) -> str:
        buckets = report.buckets
        snap = report.snapshot
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        renderer = _esc(snap.get("renderer", "—"))

        chips = "".join(
            f'<span class="chip">{label} <b>{_esc(value)}</b></span>'
            for label, value in [
                ("语料", snap.get("corpus", self.dataset)),
                ("样本桶", len(buckets)),
                ("PDF 后端", snap.get("pdf_backend", "—")),
            ]
        )
        cards = self._cards(buckets)
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>数据清洗质检报告 · {_esc(report.run_id)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="head">
    <div>
      <div class="title">数据清洗质检报告</div>
      <div class="sub">数据集 <b>{_esc(self.dataset)}</b> · run <code>{_esc(report.run_id)}</code> · {timestamp} · 渲染器 <code>{renderer}</code></div>
    </div>
  </div>
  <div class="chips">{chips}</div>
  <div class="cards">{cards}</div>
  {self._heading_section(buckets)}
  {self._table_section(buckets)}
  {self._image_section(buckets)}
  {self._timing_section(buckets)}
  <div class="foot">
    <b>口径与说明：</b>核心依据=清洗产出 md 与原始标准 md 的一致性（round-trip 联合保真，含渲染失真）；
    DOCX 样式标题 / HTML <code>&lt;h1-6&gt;</code> 有元数据标题树，作 PDF 推断的对照基线/上界；
    md 直输入为基准线（score≈1.0）；表格先检测模式（md/图片/JSON）再比对；
    图片/表转图按上下文锚点判位置；指标逐 (格式×后端) 分桶，小样本桶（n&lt;{_SMALL_BUCKET_N}）仅作定性参考。
  </div>
</div>
</body>
</html>
"""

    def _cards(self, buckets: list[CleaningBucket]) -> str:
        if not buckets:
            return ""
        # 优先展示 PDF 桶作首屏概览（清洗最易失真处）
        pdf = next((b for b in buckets if b.format == "pdf"), buckets[0])
        items = [
            ("文本完整性", pdf.metrics.get("text_completeness"), False, ""),
            ("标题识别完整率", pdf.metrics.get("heading_recall"), False, ""),
            ("表格单元格 F1", pdf.metrics.get("table_md_cell_f1"), False, ""),
            ("清洗时间 p50", pdf.metrics.get("clean_ms_p50"), False, "ms"),
        ]
        cards = []
        for label, val, _pct, suffix in items:
            if val is None:
                continue
            shown = f"{val:.0f}{suffix}" if suffix else f"{val:.2f}"
            cards.append(
                f'<div class="card"><div class="k">{label}（{_bucket_label(pdf)}）</div>'
                f'<div class="v">{shown}</div></div>'
            )
        return "".join(cards)

    def _heading_section(self, buckets: list[CleaningBucket]) -> str:
        rows = "".join(
            f"<tr><td>{_esc(_bucket_label(b))}</td>{_cell(b, 'heading_recall')}"
            f"{_cell(b, 'heading_false_rate')}{_cell(b, 'heading_level_consistency_rel')}"
            f'<td class="n">{b.n}</td></tr>'
            for b in buckets
        )
        return f"""
  <section>
    <h2>标题识别 <span class="badge">heading · 两情况 · 逐 (格式×后端)</span></h2>
    <p class="h-note">recall=是否识别到所有标题；层级一致=识别到的层级是否与原一致。PDF 无标题树元数据、靠版面推断，差异最大。</p>
    <table>
      <thead><tr><th>格式 / 后端</th><th>识别完整率</th><th>误识别率</th><th>层级一致(相对)</th><th>n</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </section>"""

    def _table_section(self, buckets: list[CleaningBucket]) -> str:
        rows = "".join(
            f"<tr><td>{_esc(_bucket_label(b))}</td>"
            f"{_cell(b, 'table_mode_image_ratio', pct=True)}{_cell(b, 'table_md_cell_f1')}"
            f"{_cell(b, 'table_json_corr_f1')}{_cell(b, 'table_image_position_ok')}"
            f'<td class="n">{b.n}</td></tr>'
            for b in buckets
        )
        return f"""
  <section>
    <h2>表格识别 <span class="badge">table · 先检测模式</span></h2>
    <p class="h-note">解析可能产出 md表/图片/JSON 三模式，先报分布再按模式评；三模式都先判位置正确。</p>
    <table>
      <thead><tr><th>格式 / 后端</th><th>转图片占比</th><th>md单元格F1</th><th>JSON对应F1</th><th>图位置正确</th><th>n</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </section>"""

    def _image_section(self, buckets: list[CleaningBucket]) -> str:
        rows = "".join(
            f"<tr><td>{_esc(_bucket_label(b))}</td>{_cell(b, 'image_recall')}"
            f"{_cell(b, 'image_false_rate')}{_cell(b, 'image_context_position_ok')}"
            f'<td class="n">{b.n}</td></tr>'
            for b in buckets
        )
        return f"""
  <section>
    <h2>图片识别 <span class="badge">image · 上下文位置</span></h2>
    <p class="h-note">解析后为 md 引用；重点判前驱/后继文本块锚点是否一致（位置正确）。</p>
    <table>
      <thead><tr><th>格式 / 后端</th><th>识别完整率</th><th>误识别率</th><th>上下文位置正确率</th><th>n</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </section>"""

    def _timing_section(self, buckets: list[CleaningBucket]) -> str:
        def ms(b: CleaningBucket, key: str) -> str:
            return f"{b.metrics[key] / 1000:.2f}s" if key in b.metrics else "—"

        rows = "".join(
            f"<tr><td>{_esc(_bucket_label(b))}</td><td>{ms(b, 'clean_ms_p50')}</td>"
            f"<td>{ms(b, 'clean_ms_p95')}</td>{_cell(b, 'stability')}"
            f'<td class="n">{b.n}</td></tr>'
            for b in buckets
        )
        return f"""
  <section>
    <h2>数据清洗时间与稳定性 <span class="badge">clean_ms · stability</span></h2>
    <p class="h-note">清洗时间是一等指标（后端选型成本）；稳定性=同输入多次清洗一致率，非确定后端（mineru/VLM）&lt;1。</p>
    <table>
      <thead><tr><th>格式 / 后端</th><th>p50</th><th>p95</th><th>稳定性</th><th>n</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </section>"""
