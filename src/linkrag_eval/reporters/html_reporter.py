"""HTML 报告：自包含、离线可开、涨绿跌红，样式与 .specs 模版一致。

引擎代码不能依赖 git-ignored 的 .specs，故模版骨架（CSS + 布局）内嵌本模块，
与 .specs/rag-quality-eval/templates/eval_report_template.html 保持同源风格。
"""

from __future__ import annotations

import html
import statistics
from collections import Counter
from datetime import datetime

from linkrag_eval.models import EvalResult, Layer, MetricResult
from linkrag_eval.reporters.base import RegressionCriteria, diff_metrics

_CSS = """
  :root{
    --bg:#f7f8fa; --card:#fff; --ink:#1f2328; --muted:#656d76; --line:#e4e7eb;
    --accent:#2f6feb; --up:#1a7f37; --down:#cf222e; --warn:#9a6700; --warnbg:#fff8c5;
    --chipbg:#eef1f4; --radius:10px;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
    -webkit-font-smoothing:antialiased}
  .wrap{max-width:1040px;margin:0 auto;padding:28px 20px 56px}
  .head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap;margin-bottom:18px}
  .title{font-size:20px;font-weight:650;letter-spacing:.2px}
  .sub{color:var(--muted);font-size:13px;margin-top:4px}
  .verdict{font-size:13px;font-weight:650;padding:6px 14px;border-radius:999px;white-space:nowrap}
  .v-pass{background:#dafbe1;color:var(--up)}
  .v-regress{background:#ffebe9;color:var(--down)}
  .chips{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 24px}
  .chip{background:var(--chipbg);color:#3a424a;border-radius:6px;padding:4px 10px;font-size:12px}
  .chip b{color:var(--ink);font-weight:600}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:28px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:14px 16px}
  .card .k{color:var(--muted);font-size:12px}
  .card .v{font-size:24px;font-weight:680;margin-top:6px;letter-spacing:.3px}
  .card .d{font-size:12px;font-weight:600;margin-top:4px}
  .up{color:var(--up)} .down{color:var(--down)} .flat{color:var(--muted)}
  section{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
    padding:18px 18px 6px;margin-bottom:20px}
  h2{font-size:15px;font-weight:650;margin:0 0 4px;display:flex;align-items:center;gap:8px}
  .h-note{color:var(--muted);font-size:12px;font-weight:400;margin:0 0 14px}
  table{width:100%;border-collapse:collapse;font-size:13px;margin-bottom:12px}
  th,td{text-align:right;padding:8px 10px;border-bottom:1px solid var(--line)}
  th:first-child,td:first-child{text-align:left}
  thead th{color:var(--muted);font-weight:600;font-size:12px;border-bottom:1px solid var(--line)}
  tbody tr:hover{background:#fafbfc}
  .delta{font-weight:600}
  .badge{display:inline-block;font-size:11px;padding:1px 7px;border-radius:5px;background:var(--chipbg);color:#444}
  .regress-row{background:#fff5f5}
  .n{color:var(--muted);font-size:12px}
  .banner{border-radius:var(--radius);padding:12px 16px;margin-bottom:20px;font-size:13px}
  .banner.warn{background:var(--warnbg);color:var(--warn);border:1px solid #eedc82}
  .foot{color:var(--muted);font-size:12px;line-height:1.7;border-top:1px solid var(--line);padding-top:16px;margin-top:8px}
  .foot b{color:#3a424a}
  .gloss-desc{text-align:left;color:#3a424a;font-size:12.5px;line-height:1.6}
  abbr[title]{text-decoration:underline dotted;text-underline-offset:2px;cursor:help}
"""

_SMALL_BUCKET_N = 15

# 指标释义：base 名 → (展示名, 一句话含义)。用于报告内"指标含义"区块与表格悬停提示，
# 让不熟悉检索评测口径的读者无需外查文档即可读懂数字。
_GLOSSARY: dict[str, tuple[str, str]] = {
    "recall": (
        "Recall@k",
        "前 k 条召回里，标准答案 chunk 被捞回来的比例。检索层最该看的总指标，越高越好。",
    ),
    "precision": (
        "Precision@k",
        "前 k 条里属于标准答案的比例。每个问题通常只有 1 个金标 chunk，故天然偏低，不宜单看。",
    ),
    "hit_rate": (
        "Hit Rate@k",
        "前 k 条里“至少命中一个标准答案”的问题占比，即命中率。只问“中没中”，不看排第几。",
    ),
    "ndcg_binary": (
        "NDCG@k（二值）",
        "兼顾“是否命中”和“排得多靠前”的排序质量分，相关性按 0/1 计；命中越靠前得分越高，满分 1。",
    ),
    "ndcg_graded": (
        "NDCG@k（分级）",
        "同 NDCG，但相关性分多个等级而非 0/1。与二值 NDCG 口径不同、数值不可互比。",
    ),
    "mrr": (
        "MRR",
        "首个命中结果排名的倒数的平均值（命中在第 1 位=1，第 2 位=0.5，以此类推）。衡量第一个正确答案有多靠前。",
    ),
    "map": (
        "MAP",
        "平均精度均值，综合所有命中位置的排序质量。每问仅 1 个金标时与 MRR 等价。",
    ),
}


def _split_granularity_metric(name: str) -> tuple[str, str | None]:
    if name.endswith("_chunk"):
        return name.removesuffix("_chunk"), "chunk"
    if name.endswith("_doc"):
        return name.removesuffix("_doc"), "doc"
    return name, None


def _metric_label(name: str) -> str:
    base, gran = _split_granularity_metric(name)
    suffix = {"chunk": "（chunk）", "doc": "（doc）"}.get(gran, "")
    return f"{base}{suffix}"


def _metric_sort_key(name: str) -> tuple[int, int, str]:
    base, gran = _split_granularity_metric(name)
    order = {
        "recall": 0,
        "precision": 1,
        "hit_rate": 2,
        "ndcg_binary": 3,
        "ndcg_graded": 4,
        "mrr": 5,
        "map": 6,
    }
    gran_order = {"chunk": 0, None: 1, "doc": 2}
    return (order.get(base, 99), gran_order.get(gran, 9), name)


def _esc(value) -> str:
    return html.escape(str(value))


def _metric_name_cell(name: str) -> str:
    """指标名单元格：命中术语表时加 title 悬停提示。"""
    base, gran = _split_granularity_metric(name)
    entry = _GLOSSARY.get(base)
    if entry is None:
        return _esc(_metric_label(name))
    _, desc = entry
    if gran == "chunk":
        desc = f"{desc} 当前行为 chunk 粒度: 必须命中标准证据片段。"
    elif gran == "doc":
        desc = f"{desc} 当前行为 doc 粒度: 命中正确文档的任意 chunk 即算命中,口径更宽。"
    return f'<abbr title="{_esc(desc)}">{_esc(_metric_label(name))}</abbr>'


def _fmt(value: float) -> str:
    return f"{value:.3f}"


def _run_quality(result: EvalResult) -> dict[str, object]:
    failed_counter: Counter[str] = Counter()
    failed_samples = 0
    zero_ranked = 0
    for row in result.per_sample:
        failed = list(row.get("failed_sources") or [])
        if failed:
            failed_samples += 1
            failed_counter.update(failed)
        if row.get("n_ranked") == 0:
            zero_ranked += 1
    return {
        "total": len(result.per_sample),
        "failed_samples": failed_samples,
        "failed_sources": dict(failed_counter),
        "zero_ranked": zero_ranked,
        "clean": failed_samples == 0 and zero_ranked == 0,
    }


def _delta_cell(delta: float | None) -> str:
    if delta is None:
        return '<td class="delta flat">—</td>'
    if abs(delta) < 0.0005:
        return '<td class="delta flat">±0.000</td>'
    cls = "up" if delta > 0 else "down"
    sign = "+" if delta > 0 else "−"
    return f'<td class="delta {cls}">{sign}{abs(delta):.3f}</td>'


class HtmlReporter:
    def __init__(
        self,
        *,
        dataset: str = "default",
        criteria: RegressionCriteria = RegressionCriteria(),
    ):
        self.dataset = dataset
        self.criteria = criteria

    def render(self, result: EvalResult, baseline: EvalResult | None = None) -> str:
        diff = diff_metrics(result, baseline, self.criteria) if baseline else None
        snap = result.snapshot
        delta_by_key = {(d.name, d.k): d for d in (diff.deltas if diff else [])}

        verdict = (
            f'<div class="verdict v-regress">⚠ 检出回归 · {len(diff.regressions)} 项</div>'
            if diff and diff.regressions
            else '<div class="verdict v-pass">PASS</div>'
        )

        chips = "".join(
            f'<span class="chip">{label} <b>{_esc(value)}</b></span>'
            for label, value in [
                ("sparse provider", snap.sparse_vector_provider),
                ("top_k", snap.top_k),
                ("thresholds", ",".join(
                    f"{k}:{v:g}" for k, v in sorted(snap.route_score_thresholds.items())
                ) or snap.score_threshold),
                ("route top_k", ",".join(
                    f"{k}:{v}" for k, v in sorted(snap.route_top_ks.items())
                ) or "—"),
                ("fusion", snap.fusion_strategy),
                ("weights", ",".join(
                    f"{k}:{v:g}" for k, v in sorted(snap.fusion_weights.items())
                ) or "—"),
                ("enabled", ",".join(snap.enabled_sources)),
                ("rrf_k", snap.rrf_k),
                ("rerank top_n", snap.rerank_top_n),
                ("chat", snap.chat_model),
                ("judge", snap.judge_model),
                ("baseline", baseline.run_id if baseline else "—"),
            ]
        )

        banners = []
        if diff and diff.incomparable_reasons:
            reasons = "；".join(_esc(r) for r in diff.incomparable_reasons)
            banners.append(
                f'<div class="banner warn">⚠ 口径与基线不一致，diff 仅供参考、不触发回归判定：{reasons}</div>'
            )
        if diff and diff.regressions:
            items = "、".join(
                f"<b>{_esc(d.name)}{f'@{d.k}' if d.k else ''} {d.delta:+.3f}</b>"
                for d in diff.regressions
            )
            banners.append(
                f'<div class="banner warn">检出 {len(diff.regressions)} 项回归（同口径对比基线）：{items}。'
                f"判据：Recall@k 跌&gt;{self.criteria.recall_drop * 100:.0f}pp / "
                f"NDCG 跌&gt;{self.criteria.ndcg_drop}（n&ge;{self.criteria.min_n} 才触发）。</div>"
            )

        retrieval = [m for m in result.metrics if m.layer == Layer.RETRIEVAL]
        headline = self._headline_cards(retrieval, delta_by_key)
        retrieval_section = self._retrieval_section(retrieval, delta_by_key)
        quality_section = self._run_quality_section(result)
        overlap_note = self._overlap_latency_note(result, retrieval)
        bucket_section = self._bucket_section(retrieval)
        domain_section = self._domain_section(retrieval)
        glossary_section = self._glossary_section(retrieval)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        baseline_id = _esc(baseline.run_id) if baseline else "—"
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>评测报告 · {_esc(result.run_id)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="head">
    <div>
      <div class="title">RAG 评测报告</div>
      <div class="sub">数据集 <b>{_esc(self.dataset)}</b> · run <code>{_esc(result.run_id)}</code> · {timestamp} · git <code>{_esc(snap.git_sha)}</code></div>
    </div>
    {verdict}
  </div>
  <div class="chips">{chips}</div>
  {"".join(banners)}
  <div class="cards">{headline}</div>
  {retrieval_section}
  {quality_section}
  {overlap_note}
  {bucket_section}
  {domain_section}
  {glossary_section}
  <div class="foot">
    <b>口径与说明：</b>top_k={snap.top_k}（=RECALL_RESULT_LIMIT，融合口径）；NDCG 标注 binary/graded 口径，
    二值与分级数值不可比、不互比；基线 <code>{baseline_id}</code> 同 config 对比，不同 provider/top_k 不互比；
    回归判据 Recall@k 跌&gt;{self.criteria.recall_drop * 100:.0f}pp、NDCG 跌&gt;{self.criteria.ndcg_drop}
    （入配置可调，非 PR 门禁，正式判据待噪声地板校准）；小样本桶（n&lt;{_SMALL_BUCKET_N}）仅作定性参考。
    数据可复现 &gt; 指标好看。
  </div>
</div>
</body>
</html>
"""

    def _headline_cards(self, metrics: list[MetricResult], delta_by_key: dict) -> str:
        cards = []
        preferred = [
            (["recall_chunk", "recall", "recall_doc"], "Recall"),
            (["ndcg_binary_chunk", "ndcg_binary", "ndcg_binary_doc"], "NDCG"),
            (["mrr_chunk", "mrr", "mrr_doc"], "MRR"),
        ]
        for names, label in preferred:
            candidates = [m for m in metrics if m.name in names]
            if not candidates:
                continue
            priority = {name: i for i, name in enumerate(names)}
            m = min(
                candidates,
                key=lambda x: (
                    priority.get(x.name, 99),
                    -(x.k if x.k is not None else 0),
                ),
            )
            d = delta_by_key.get((m.name, m.k))
            suffix = f"@{m.k}" if m.k else ""
            gran = _split_granularity_metric(m.name)[1]
            gran_label = f" · {gran}" if gran else ""
            if d is None:
                delta_html = '<div class="d flat">无基线</div>'
            elif abs(d.delta) < 0.0005:
                delta_html = '<div class="d flat">±0.000 vs 基线</div>'
            else:
                cls = "up" if d.delta > 0 else "down"
                arrow = "▲" if d.delta > 0 else "▼"
                delta_html = f'<div class="d {cls}">{arrow} {abs(d.delta):.3f} vs 基线</div>'
            cards.append(
                f'<div class="card"><div class="k">{label}{suffix}{gran_label}</div>'
                f'<div class="v">{_fmt(m.mean)}</div>{delta_html}</div>'
            )
        return "".join(cards)

    def _retrieval_section(self, metrics: list[MetricResult], delta_by_key: dict) -> str:
        if not metrics:
            return ""
        k_metric_bases = {"recall", "precision", "hit_rate", "ndcg_binary", "ndcg_graded"}
        scalar_bases = {"mrr", "map"}
        ks = sorted({m.k for m in metrics if m.k is not None})
        rows = []
        k_metrics = sorted(
            {
                m.name for m in metrics
                if m.k is not None and _split_granularity_metric(m.name)[0] in k_metric_bases
            },
            key=_metric_sort_key,
        )
        for name in k_metrics:
            per_k = {m.k: m for m in metrics if m.name == name}
            if not per_k:
                continue
            max_k = max(per_k)
            d = delta_by_key.get((name, max_k))
            n = per_k[max_k].n
            cells = "".join(
                f"<td>{_fmt(per_k[k].mean) if k in per_k else '—'}</td>" for k in ks
            )
            regress = ' class="regress-row"' if d and d.is_regression else ""
            rows.append(
                f"<tr{regress}><td>{_metric_name_cell(name)}</td>{cells}"
                f"{_delta_cell(d.delta if d else None)}<td class=\"n\">{n}</td></tr>"
            )
        scalar_metrics = sorted(
            {
                m.name for m in metrics
                if m.k is None and _split_granularity_metric(m.name)[0] in scalar_bases
            },
            key=_metric_sort_key,
        )
        for name in scalar_metrics:
            ms = [m for m in metrics if m.name == name and m.k is None]
            if not ms:
                continue
            m = ms[0]
            d = delta_by_key.get((name, None))
            rows.append(
                f'<tr><td>{_metric_name_cell(name)}</td><td colspan="{len(ks)}">{_fmt(m.mean)}</td>'
                f"{_delta_cell(d.delta if d else None)}<td class=\"n\">{m.n}</td></tr>"
            )
        header_ks = "".join(f"<th>@{k}</th>" for k in ks)
        return f"""
  <section>
    <h2>检索层 <span class="badge">retrieval · 自研 · 二值/分级 NDCG 分名</span></h2>
    <p class="h-note">依据 expected_chunk/doc_ids；主看 Recall@k。Δ 为对基线同口径涨跌（取最大 k）。</p>
    <table>
      <thead><tr><th>指标</th>{header_ks}<th>Δ@{max(ks) if ks else "-"}</th><th>n</th></tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
  </section>"""

    def _overlap_latency_note(self, result: EvalResult, metrics: list[MetricResult]) -> str:
        parts = []
        overlaps = [m for m in metrics if m.name.startswith("overlap_")]
        for m in overlaps:
            label = m.name.replace("overlap_", "").replace("_only", " 独有")
            label = label.replace("all_sources", "全路共有")
            parts.append(f"{_esc(label)} {m.mean * 100:.0f}%")
        latencies = [
            d["elapsed_ms"] for d in result.per_sample if d.get("elapsed_ms")
        ]
        if latencies:
            parts.append(f"召回延迟（中位）{statistics.median(latencies):.0f}ms")
        if not parts:
            return ""
        return f'<section><h2>三路重叠与延迟</h2><p class="h-note">{" · ".join(parts)}（重叠率读归一化 sources，延迟为诊断信息不进指标）</p></section>'

    def _run_quality_section(self, result: EvalResult) -> str:
        quality = _run_quality(result)
        if not quality["total"]:
            return ""
        failed_sources = quality["failed_sources"]
        failed_text = (
            "、".join(f"{_esc(k)}={v}" for k, v in sorted(failed_sources.items()))
            if failed_sources else "无"
        )
        badge = "clean run" if quality["clean"] else "non-clean run"
        note = (
            "无单路失败且无零结果样本,可作为稳定基线候选。"
            if quality["clean"]
            else "存在远端或分路检索失败,本轮指标会受活栈波动影响,不宜直接作为稳定基线。"
        )
        return f"""
  <section>
    <h2>运行质量 <span class="badge">{badge}</span></h2>
    <p class="h-note">{_esc(note)}</p>
    <table>
      <thead><tr><th>样本数</th><th>failed source 样本</th><th>失败来源</th><th>零结果样本</th></tr></thead>
      <tbody><tr>
        <td>{quality["total"]}</td>
        <td>{quality["failed_samples"]}</td>
        <td>{failed_text}</td>
        <td>{quality["zero_ranked"]}</td>
      </tr></tbody>
    </table>
  </section>"""

    def _glossary_section(self, metrics: list[MetricResult]) -> str:
        """报告内"指标含义"区块：只列本次实际出现的指标，避免无关条目。"""
        present = {_split_granularity_metric(m.name)[0] for m in metrics}
        rows = []
        for name, (label, desc) in _GLOSSARY.items():
            if name not in present:
                continue
            rows.append(
                f'<tr><td><b>{_esc(label)}</b></td><td class="gloss-desc">{_esc(desc)}</td></tr>'
            )
        # overlap_* 不在 _GLOSSARY（动态命名），单列一条总说明。
        if any(m.name.startswith("overlap_") for m in metrics):
            rows.append(
                '<tr><td><b>三路重叠</b></td>'
                '<td class="gloss-desc">各召回路结果的重叠/独有占比，诊断多路是否冗余或互补，非质量分。</td></tr>'
            )
        if not rows:
            return ""
        return f"""
  <section>
    <h2>指标含义 <span class="badge">读数对照</span></h2>
    <p class="h-note">仅列出本次报告出现的指标；表格中指标名亦可悬停查看。@k 表示只看排名前 k 条结果。</p>
    <table>
      <thead><tr><th>指标</th><th>含义</th></tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
  </section>"""

    def _bucket_section(self, metrics: list[MetricResult]) -> str:
        keyed = [m for m in metrics if m.by_type]
        if not keyed:
            return ""
        show = [
            m for m in keyed
            if (m.name, m.k) in {
                ("recall_chunk", 10),
                ("ndcg_binary_chunk", 10),
                ("mrr_chunk", None),
            }
        ] or keyed[:3]
        types = sorted(
            {t for m in show for t in m.by_type}, key=lambda t: t.value
        )
        header = "".join(
            f"<th>{_esc(m.name)}{f'@{m.k}' if m.k else ''}</th>" for m in show
        )
        rows = []
        for t in types:
            n = max((m.by_type_n.get(t, 0) for m in show), default=0)
            small = "（样本不足，仅定性）" if n < _SMALL_BUCKET_N else ""
            cells = "".join(
                f"<td>{_fmt(m.by_type[t]) if t in m.by_type else '—'}</td>" for m in show
            )
            rows.append(
                f'<tr><td>{_esc(t.value)}{small}</td><td class="n">{n}</td>{cells}</tr>'
            )
        return f"""
  <section>
    <h2>分桶归因 <span class="badge">by type · 小样本仅供定性</span></h2>
    <table>
      <thead><tr><th>类型</th><th>n</th>{header}</tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
  </section>"""

    def _domain_section(self, metrics: list[MetricResult]) -> str:
        """按语料垂域（eval_dataset.domain）分桶；单域退化为一行，多域可横向对比。"""
        keyed = [m for m in metrics if m.by_domain]
        if not keyed:
            return ""
        show = [
            m for m in keyed
            if (m.name, m.k) in {
                ("recall_chunk", 10),
                ("ndcg_binary_chunk", 10),
                ("mrr_chunk", None),
            }
        ] or keyed[:3]
        domains = sorted({d for m in show for d in m.by_domain})
        header = "".join(
            f"<th>{_esc(m.name)}{f'@{m.k}' if m.k else ''}</th>" for m in show
        )
        rows = []
        for d in domains:
            n = max((m.by_domain_n.get(d, 0) for m in show), default=0)
            small = "（样本不足，仅定性）" if n < _SMALL_BUCKET_N else ""
            cells = "".join(
                f"<td>{_fmt(m.by_domain[d]) if d in m.by_domain else '—'}</td>" for m in show
            )
            rows.append(
                f'<tr><td>{_esc(d)}{small}</td><td class="n">{n}</td>{cells}</tr>'
            )
        return f"""
  <section>
    <h2>垂域归因 <span class="badge">by domain · 跨领域可比</span></h2>
    <table>
      <thead><tr><th>垂域</th><th>n</th>{header}</tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
  </section>"""
