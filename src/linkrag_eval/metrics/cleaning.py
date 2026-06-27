"""数据清洗质检指标（CLEANING 层）：produced_md vs 参考 md 的一致性比对。

核心依据（phase0_5 §一）：清洗产出的 md 与原始标准 md 越一致，数据清洗质量越好。
做法：把两份 md 解析成块序列（heading/paragraph/table/list/image/code），归一化后
按指标比对。全部为**纯函数**——不碰像素 / 不读 IO / 确定性，可单测、进 PR 门禁。

不走 Metric 协议（那是 Sample + ranked 形状，面向检索/生成）：清洗指标天然是
"两份 md 文本"的函数，独立成模块，由 cleaning 专用 runner 调 `score_pair`。

口径分布在 phase0_5：
- 文本完整性/噪声 §4.2
- 标题识别完整率 + 层级一致 §4.3
- 表格三模式（md/图片/JSON）§4.4
- 图片识别 + 上下文位置 §4.5
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Sequence

from linkrag_eval.models import (
    CleaningBucket,
    CleaningHeadingScore,
    CleaningImageScore,
    CleaningPair,
    CleaningQcItem,
    CleaningQcReport,
    CleaningTableScore,
    CleaningTextScore,
)

# 相似度阈值：标题/图片锚点匹配容忍清洗的微小改写（去标点、全半角、空白）。
_MATCH_THRESHOLD = 0.6
_ANCHOR_THRESHOLD = 0.6

_IMAGE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<path>[^)]*)\)")
_CJK_RUN_RE = re.compile(r"[一-鿿]+")
_LATIN_RE = re.compile(r"[a-zA-Z0-9]+")
_PUNCT_RE = re.compile(r"[\s　，。、；：？！“”‘’（）【】《》〈〉,.;:?!\"'()\[\]{}<>—\-_*`#>|]+")


# ---------------------------------------------------------------------------
# 归一化与分词
# ---------------------------------------------------------------------------


def normalize(text: str) -> str:
    """NFKC + 小写 + 去空白/标点：用于相似度与等值判定（容忍清洗噪声）。"""
    text = unicodedata.normalize("NFKC", text).lower()
    return _PUNCT_RE.sub("", text)


def tokens(text: str) -> list[str]:
    """文本完整性/噪声用的 token：中文按字 + 英文/数字按词（NFKC、小写）。"""
    text = unicodedata.normalize("NFKC", text).lower()
    out = _LATIN_RE.findall(text)
    for run in _CJK_RUN_RE.findall(text):
        out.extend(run)
    return out


def _similar(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------------
# Markdown 块解析（行级、务实）
# ---------------------------------------------------------------------------


@dataclass
class Block:
    kind: str                 # heading/paragraph/table/list/image/code/blockquote
    text: str                 # 原始文本（用于锚点/相似度，比对时再归一化）
    level: int = 0            # heading 级别
    meta: dict = field(default_factory=dict)


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")
_LIST_RE = re.compile(r"^(?P<indent>\s*)(?P<bullet>[-*+]|\d+[.)])\s+(?P<body>.*)$")


def parse_blocks(markdown: str) -> list[Block]:
    """把 md 拆成块序列。务实实现：覆盖清洗质检关心的结构，不求完备 CommonMark。"""
    lines = markdown.splitlines()
    blocks: list[Block] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # 代码围栏（可能是 JSON 表格）
        if stripped.startswith("```"):
            lang = stripped[3:].strip().lower()
            body: list[str] = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1  # 跳过闭合围栏
            blocks.append(Block("code", "\n".join(body), meta={"lang": lang}))
            continue

        # 标题
        m = _HEADING_RE.match(line)
        if m:
            blocks.append(Block("heading", m.group(2).strip(), level=len(m.group(1))))
            i += 1
            continue

        # 独立图片行（整行就是一个图片引用）
        if _IMAGE_RE.fullmatch(stripped):
            im = _IMAGE_RE.match(stripped)
            blocks.append(
                Block("image", stripped, meta={"alt": im.group("alt"), "path": im.group("path")})
            )
            i += 1
            continue

        # md 表格：当前行含 | 且下一行是分隔行
        if "|" in line and i + 1 < n and _TABLE_SEP_RE.match(lines[i + 1]):
            rows: list[list[str]] = [_split_row(line)]
            i += 2  # 跳过表头 + 分隔
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(_split_row(lines[i]))
                i += 1
            blocks.append(Block("table", line, meta={"rows": rows}))
            continue

        # 列表
        if _LIST_RE.match(line):
            items: list[tuple[int, str]] = []
            while i < n and _LIST_RE.match(lines[i]):
                lm = _LIST_RE.match(lines[i])
                depth = len(lm.group("indent")) // 2
                items.append((depth, lm.group("body").strip()))
                i += 1
            blocks.append(
                Block("list", "\n".join(b for _, b in items), meta={"items": items})
            )
            continue

        # 引用
        if stripped.startswith(">"):
            blocks.append(Block("blockquote", stripped.lstrip("> ").strip()))
            i += 1
            continue

        # 段落：聚合连续非空行
        para: list[str] = [stripped]
        i += 1
        while i < n and lines[i].strip() and not _is_block_start(lines[i], lines, i):
            para.append(lines[i].strip())
            i += 1
        blocks.append(Block("paragraph", " ".join(para)))
    return blocks


def _split_row(line: str) -> list[str]:
    cells = line.strip().strip("|").split("|")
    return [c.strip() for c in cells]


def _is_block_start(line: str, lines: list[str], idx: int) -> bool:
    s = line.strip()
    if _HEADING_RE.match(line) or s.startswith("```") or s.startswith(">"):
        return True
    if _LIST_RE.match(line) or _IMAGE_RE.fullmatch(s):
        return True
    if "|" in line and idx + 1 < len(lines) and _TABLE_SEP_RE.match(lines[idx + 1]):
        return True
    return False


# ---------------------------------------------------------------------------
# 文本完整性 / 噪声（§4.2）
# ---------------------------------------------------------------------------


def _text_corpus(blocks: Sequence[Block]) -> str:
    """汇总所有可读文本（不含纯结构标记）用于 token 级 recall/precision。"""
    parts: list[str] = []
    for b in blocks:
        if b.kind == "image":
            parts.append(b.meta.get("alt", ""))
        elif b.kind == "table":
            for row in b.meta.get("rows", []):
                parts.extend(row)
        else:
            parts.append(b.text)
    return " ".join(parts)


def text_scores(ref_blocks: Sequence[Block], prod_blocks: Sequence[Block]) -> CleaningTextScore:
    ref_tok = tokens(_text_corpus(ref_blocks))
    prod_tok = tokens(_text_corpus(prod_blocks))
    from collections import Counter

    ref_c, prod_c = Counter(ref_tok), Counter(prod_tok)
    if not ref_tok:
        return CleaningTextScore(completeness=1.0, noise=0.0)
    kept = sum((ref_c & prod_c).values())          # 参考 token 被保留的数量（取小）
    completeness = kept / len(ref_tok)
    extra = sum((prod_c - ref_c).values())         # produced 中多出的（非参考）
    noise = extra / len(prod_tok) if prod_tok else 0.0
    return CleaningTextScore(completeness=round(completeness, 4), noise=round(noise, 4))


# ---------------------------------------------------------------------------
# 标题识别（§4.3）
# ---------------------------------------------------------------------------


def heading_scores(ref_blocks: Sequence[Block], prod_blocks: Sequence[Block]) -> CleaningHeadingScore:
    ref_h = [b for b in ref_blocks if b.kind == "heading"]
    prod_h = [b for b in prod_blocks if b.kind == "heading"]
    if not ref_h:
        return CleaningHeadingScore(1.0, 0.0, 1.0, 1.0, [])

    matches = _align_by_text(ref_h, prod_h)        # list[(ref_idx, prod_idx)]
    matched_ref = {r for r, _ in matches}
    recall = len(matches) / len(ref_h)
    false_rate = (len(prod_h) - len(matches)) / len(prod_h) if prod_h else 0.0

    if matches:
        abs_ok = sum(1 for r, p in matches if ref_h[r].level == prod_h[p].level)
        level_abs = abs_ok / len(matches)
        deltas = [prod_h[p].level - ref_h[r].level for r, p in matches]
        from collections import Counter

        top = Counter(deltas).most_common(1)[0][1]  # 最常见偏移的命中数
        level_rel = top / len(matches)              # 整体层级树同构（允许统一偏移）
    else:
        level_abs = level_rel = 0.0

    missed = [ref_h[r].text for r in range(len(ref_h)) if r not in matched_ref]
    return CleaningHeadingScore(
        recall=round(recall, 4),
        false_rate=round(false_rate, 4),
        level_consistency_abs=round(level_abs, 4),
        level_consistency_rel=round(level_rel, 4),
        missed=missed,
    )


def _align_by_text(ref: Sequence[Block], prod: Sequence[Block]) -> list[tuple[int, int]]:
    """按归一化文本相似度做一对一贪心匹配（阈值过滤），保序优先取最相似。"""
    ref_norm = [normalize(b.text) for b in ref]
    prod_norm = [normalize(b.text) for b in prod]
    used: set[int] = set()
    matches: list[tuple[int, int]] = []
    for r, rn in enumerate(ref_norm):
        best_p, best_s = -1, _MATCH_THRESHOLD
        for p, pn in enumerate(prod_norm):
            if p in used:
                continue
            s = _similar(rn, pn)
            if s >= best_s:
                best_s, best_p = s, p
        if best_p >= 0:
            used.add(best_p)
            matches.append((r, best_p))
    return matches


# ---------------------------------------------------------------------------
# 图片识别 + 上下文位置（§4.5）
# ---------------------------------------------------------------------------


def _image_anchors(blocks: Sequence[Block]) -> list[dict]:
    """每张图片记前驱/后继文本块锚点（归一化），供上下文位置判定。"""
    out: list[dict] = []
    for idx, b in enumerate(blocks):
        if b.kind != "image":
            continue
        prev_text = next(
            (normalize(blocks[j].text) for j in range(idx - 1, -1, -1)
             if blocks[j].kind != "image" and blocks[j].text),
            "",
        )
        next_text = next(
            (normalize(blocks[j].text) for j in range(idx + 1, len(blocks))
             if blocks[j].kind != "image" and blocks[j].text),
            "",
        )
        out.append({"alt": normalize(b.meta.get("alt", "")), "prev": prev_text, "next": next_text})
    return out


def image_scores(ref_blocks: Sequence[Block], prod_blocks: Sequence[Block]) -> CleaningImageScore:
    ref_imgs = _image_anchors(ref_blocks)
    prod_imgs = _image_anchors(prod_blocks)
    if not ref_imgs:
        return CleaningImageScore(1.0, 0.0, 1.0, [])

    # 按出现顺序一对一匹配（图片像素不可比，故按序 + alt 兜底判存在）
    m = min(len(ref_imgs), len(prod_imgs))
    recall = m / len(ref_imgs)
    false_rate = (len(prod_imgs) - m) / len(prod_imgs) if prod_imgs else 0.0

    pos_ok = 0
    misplaced: list[str] = []
    for i in range(m):
        r, p = ref_imgs[i], prod_imgs[i]
        prev_ok = _similar(r["prev"], p["prev"]) >= _ANCHOR_THRESHOLD
        next_ok = _similar(r["next"], p["next"]) >= _ANCHOR_THRESHOLD
        if prev_ok and next_ok:
            pos_ok += 1
        else:
            misplaced.append(r["alt"] or f"image-{i}")
    context_ok = pos_ok / m if m else 0.0
    return CleaningImageScore(
        recall=round(recall, 4),
        false_rate=round(false_rate, 4),
        context_position_ok=round(context_ok, 4),
        misplaced=misplaced,
    )


# ---------------------------------------------------------------------------
# 表格识别：先检测模式，再按模式比对（§4.4）
# ---------------------------------------------------------------------------


def _table_cells(rows: Sequence[Sequence[str]]) -> set[tuple[int, int, str]]:
    """把 md 表格行展开成 (row, col, normalized_value) 三元组集合。"""
    return {
        (ri, ci, normalize(val))
        for ri, row in enumerate(rows)
        for ci, val in enumerate(row)
        if normalize(val)
    }


def _json_to_cells(payload) -> set[tuple[int, int, str]]:
    """把 JSON（list[dict] 或 list[list]）还原成与 md 表同形的三元组集合。"""
    cells: set[tuple[int, int, str]] = set()
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        headers = list(payload[0].keys())
        for ci, h in enumerate(headers):
            cells.add((0, ci, normalize(str(h))))
        for ri, obj in enumerate(payload, start=1):
            for ci, h in enumerate(headers):
                v = normalize(str(obj.get(h, "")))
                if v:
                    cells.add((ri, ci, v))
    elif isinstance(payload, list):
        for ri, row in enumerate(payload):
            if isinstance(row, list):
                for ci, v in enumerate(row):
                    nv = normalize(str(v))
                    if nv:
                        cells.add((ri, ci, nv))
    return cells


def _f1(ref: set, prod: set) -> float:
    if not ref and not prod:
        return 1.0
    if not ref or not prod:
        return 0.0
    inter = len(ref & prod)
    prec = inter / len(prod)
    rec = inter / len(ref)
    return 0.0 if prec + rec == 0 else round(2 * prec * rec / (prec + rec), 4)


def _anchor_of(blocks: Sequence[Block], idx: int) -> str:
    """某 block 的前驱文本锚点（归一化），用于在 produced 中定位对应表格区域。"""
    return next(
        (normalize(blocks[j].text) for j in range(idx - 1, -1, -1)
         if blocks[j].kind in ("paragraph", "heading") and blocks[j].text),
        "",
    )


def table_scores(ref_blocks: Sequence[Block], prod_blocks: Sequence[Block]) -> CleaningTableScore:
    ref_tables = [(i, b) for i, b in enumerate(ref_blocks) if b.kind == "table"]
    if not ref_tables:
        return CleaningTableScore()

    # produced 候选：md 表格 / 图片 / JSON 代码块，各记前驱锚点
    candidates: list[tuple[str, str, Block]] = []  # (mode, anchor, block)
    for i, b in enumerate(prod_blocks):
        if b.kind == "table":
            candidates.append(("md", _anchor_of(prod_blocks, i), b))
        elif b.kind == "image":
            candidates.append(("image", _anchor_of(prod_blocks, i), b))
        elif b.kind == "code" and _looks_json(b):
            candidates.append(("json", _anchor_of(prod_blocks, i), b))

    mode_dist = {"md": 0, "image": 0, "json": 0}
    md_f1s: list[float] = []
    json_f1s: list[float] = []
    image_pos_oks: list[float] = []
    used: set[int] = set()

    for ri, rb in ref_tables:
        r_anchor = _anchor_of(ref_blocks, ri)
        best_c, best_s = -1, -1.0
        for ci, (_mode, anchor, _blk) in enumerate(candidates):
            if ci in used:
                continue
            s = _similar(r_anchor, anchor)
            if s > best_s:
                best_s, best_c = s, ci
        if best_c < 0:
            continue
        used.add(best_c)
        mode, _anchor, blk = candidates[best_c]
        mode_dist[mode] += 1
        ref_cells = _table_cells(rb.meta.get("rows", []))
        if mode == "md":
            md_f1s.append(_f1(ref_cells, _table_cells(blk.meta.get("rows", []))))
        elif mode == "json":
            try:
                payload = json.loads(blk.text)
                json_f1s.append(_f1(ref_cells, _json_to_cells(payload)))
            except (ValueError, TypeError):
                json_f1s.append(0.0)
        elif mode == "image":
            # 模式②：位置正确（锚点匹配）；完整度需 OCR，置 None
            image_pos_oks.append(1.0 if best_s >= _ANCHOR_THRESHOLD else 0.0)

    return CleaningTableScore(
        mode_dist=mode_dist,
        md_cell_f1=round(sum(md_f1s) / len(md_f1s), 4) if md_f1s else None,
        json_corr_f1=round(sum(json_f1s) / len(json_f1s), 4) if json_f1s else None,
        image_position_ok=round(sum(image_pos_oks) / len(image_pos_oks), 4) if image_pos_oks else None,
        image_completeness=None,
    )


def _looks_json(block: Block) -> bool:
    if block.meta.get("lang") in ("json", "json5"):
        return True
    t = block.text.strip()
    return t.startswith("[") or t.startswith("{")


# ---------------------------------------------------------------------------
# 列表保真 / 顺序保真（§4.2）
# ---------------------------------------------------------------------------


def list_fidelity(ref_blocks: Sequence[Block], prod_blocks: Sequence[Block]) -> float:
    def stats(blocks):
        items = [it for b in blocks if b.kind == "list" for it in b.meta.get("items", [])]
        count = len(items)
        depth = max((d for d, _ in items), default=0)
        return count, depth

    r_cnt, r_depth = stats(ref_blocks)
    p_cnt, p_depth = stats(prod_blocks)
    if r_cnt == 0:
        return 1.0
    count_ratio = min(r_cnt, p_cnt) / max(r_cnt, p_cnt)
    depth_ratio = 1.0 if max(r_depth, p_depth) == 0 else min(r_depth, p_depth) / max(r_depth, p_depth)
    return round((count_ratio + depth_ratio) / 2, 4)


def order_fidelity(ref_blocks: Sequence[Block], prod_blocks: Sequence[Block]) -> float:
    """块相对顺序一致性：匹配块对后，1 - 逆序对比例（无逆序=1.0）。"""
    matches = _align_blocks(ref_blocks, prod_blocks)
    if len(matches) < 2:
        return 1.0
    prod_seq = [p for _, p in matches]  # 已按 ref 顺序排列，理想是单调递增
    inv = sum(
        1
        for a in range(len(prod_seq))
        for b in range(a + 1, len(prod_seq))
        if prod_seq[a] > prod_seq[b]
    )
    total = len(prod_seq) * (len(prod_seq) - 1) // 2
    return round(1 - inv / total, 4) if total else 1.0


def _align_blocks(ref_blocks: Sequence[Block], prod_blocks: Sequence[Block]) -> list[tuple[int, int]]:
    """跨块类型按归一化文本相似度一对一匹配（同 kind 优先），用于顺序保真。"""
    prod_norm = [(p, normalize(b.text)) for p, b in enumerate(prod_blocks) if b.text]
    used: set[int] = set()
    matches: list[tuple[int, int]] = []
    for r, rb in enumerate(ref_blocks):
        if not rb.text:
            continue
        rn = normalize(rb.text)
        best_p, best_s = -1, _MATCH_THRESHOLD
        for p, pn in prod_norm:
            if p in used:
                continue
            s = _similar(rn, pn)
            if s >= best_s:
                best_s, best_p = s, p
        if best_p >= 0:
            used.add(best_p)
            matches.append((r, best_p))
    return matches


# ---------------------------------------------------------------------------
# 稳定性（§4.2，非确定后端）
# ---------------------------------------------------------------------------


def stability(produced_runs: Sequence[str]) -> float:
    """同输入多次清洗的一致率：成对完全相同的比例（单次或无运行恒 1.0）。"""
    runs = [r for r in produced_runs if r is not None]
    if len(runs) < 2:
        return 1.0
    pairs = same = 0
    for a in range(len(runs)):
        for b in range(a + 1, len(runs)):
            pairs += 1
            if normalize(runs[a]) == normalize(runs[b]):
                same += 1
    return round(same / pairs, 4) if pairs else 1.0


# ---------------------------------------------------------------------------
# 顶层装配：一对 md → CleaningQcItem（§5.1）
# ---------------------------------------------------------------------------


def score_pair(
    pair: CleaningPair,
    *,
    sample_id: str,
    fmt: str,
    pdf_backend: str | None = None,
    clean_ms: int = 0,
    ok: bool = True,
    stability_runs: Sequence[str] | None = None,
    artifacts: dict | None = None,
) -> CleaningQcItem:
    """把参考 md 与清洗产出 md 比成单文档质检明细（纯函数，进 PR 门禁）。"""
    ref_blocks = parse_blocks(pair.ref)
    prod_blocks = parse_blocks(pair.produced)
    return CleaningQcItem(
        sample_id=sample_id,
        format=fmt,
        pdf_backend=pdf_backend,
        clean_ms=clean_ms,
        ok=ok,
        text=text_scores(ref_blocks, prod_blocks),
        heading=heading_scores(ref_blocks, prod_blocks),
        table=table_scores(ref_blocks, prod_blocks),
        image=image_scores(ref_blocks, prod_blocks),
        list_fidelity=list_fidelity(ref_blocks, prod_blocks),
        order_fidelity=order_fidelity(ref_blocks, prod_blocks),
        stability=stability(stability_runs) if stability_runs else 1.0,
        artifacts=artifacts or {},
    )


# ---------------------------------------------------------------------------
# 跨样本聚合：逐 (format, pdf_backend) 分桶（§5.2）
# ---------------------------------------------------------------------------


def _percentile(values: Sequence[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, int(round((pct / 100) * (len(s) - 1))))
    return s[idx]


def _mean(values: Sequence[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def aggregate(items: Sequence[CleaningQcItem], *, run_id: str, snapshot: dict | None = None) -> CleaningQcReport:
    """把单文档明细按 (format, pdf_backend) 聚合成分桶报告。

    每个 metric 即一条 `eval_metric_result`（layer=cleaning，format/backend 进维度）。
    明细字段（missed/misplaced）不进聚合，只随 per-sample 落对象存储。
    """
    buckets: dict[tuple[str, str | None], list[CleaningQcItem]] = {}
    for it in items:
        buckets.setdefault((it.format, it.pdf_backend), []).append(it)

    out: list[CleaningBucket] = []
    for (fmt, backend), group in buckets.items():
        clean_ms = [g.clean_ms for g in group]
        metrics: dict[str, float] = {}

        def put(name: str, value: float | None) -> None:
            if value is not None:
                metrics[name] = value

        put("clean_ms_p50", _percentile(clean_ms, 50))
        put("clean_ms_p95", _percentile(clean_ms, 95))
        put("text_completeness", _mean([g.text.completeness for g in group]))
        put("text_noise", _mean([g.text.noise for g in group]))
        put("heading_recall", _mean([g.heading.recall for g in group]))
        put("heading_false_rate", _mean([g.heading.false_rate for g in group]))
        put("heading_level_consistency_abs", _mean([g.heading.level_consistency_abs for g in group]))
        put("heading_level_consistency_rel", _mean([g.heading.level_consistency_rel for g in group]))
        put("table_md_cell_f1", _mean([g.table.md_cell_f1 for g in group]))
        put("table_json_corr_f1", _mean([g.table.json_corr_f1 for g in group]))
        put("table_image_position_ok", _mean([g.table.image_position_ok for g in group]))
        total_tables = sum(sum(g.table.mode_dist.values()) for g in group)
        if total_tables:
            img_tables = sum(g.table.mode_dist.get("image", 0) for g in group)
            metrics["table_mode_image_ratio"] = round(img_tables / total_tables, 4)
        put("image_recall", _mean([g.image.recall for g in group]))
        put("image_false_rate", _mean([g.image.false_rate for g in group]))
        put("image_context_position_ok", _mean([g.image.context_position_ok for g in group]))
        put("list_fidelity", _mean([g.list_fidelity for g in group]))
        put("order_fidelity", _mean([g.order_fidelity for g in group]))
        put("stability", _mean([g.stability for g in group]))

        out.append(CleaningBucket(format=fmt, pdf_backend=backend, n=len(group), metrics=metrics))

    out.sort(key=lambda b: (b.format, b.pdf_backend or ""))
    return CleaningQcReport(run_id=run_id, snapshot=snapshot or {}, buckets=out)
