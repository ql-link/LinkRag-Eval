"""阶段一·数据集准备（phase0_5 §3.1）：标准 md → 各格式渲染件 + 写对应关系表。

复用 Track B 的 render 链路（golden/synth/render.py），在清洗步之前把参考 md 钉成
冻结的各格式输入。渲染是重活、质检是高频活——解耦后换 PDF backend / 改 parser
回归直接复用已冻结渲染件，差异纯来自清洗器。

首版文件后端：渲染件落本地 corpus 目录、对应关系写 registry jsonl；切 MinIO 后
把写文件换成 put_object、路径换 object_key 即可。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from linkrag_eval.golden.cleaning_dataset.prepare import normalize_reference_md
from linkrag_eval.golden.cleaning_dataset.registry import (
    CleaningDoc,
    CleaningRegistry,
    RenderedDoc,
)
from linkrag_eval.golden.synth.render import render

DEFAULT_FORMATS = ["pdf", "docx", "html"]   # md 直输入作基准线，单列、无需渲染

_RENDERER_OF = {"pdf": "weasyprint", "docx": "python-docx", "html": "builtin", "md": "identity"}


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def _renderer_version() -> str:
    """渲染器版本指纹（进表冻结：换版本=换输入，不混比）。缺失则记 'unknown'。"""
    parts = []
    for mod in ("weasyprint", "docx"):
        try:
            m = __import__(mod)
            parts.append(f"{mod}={getattr(m, '__version__', '?')}")
        except ImportError:
            parts.append(f"{mod}=absent")
    return ";".join(parts)


def build_corpus(
    md_sources: dict[str, str],
    out_dir: str | Path,
    *,
    source: str = "chinese-markdown",
    formats: list[str] | None = None,
    normalize: bool = True,
    include_md_baseline: bool = True,
) -> CleaningRegistry:
    """把 {sample_id: raw_md} 渲染成各格式，写 corpus 目录并返回填好的 registry。

    normalize=True 时对原始 md 走 prepare.normalize_reference_md（首选真实数据集场景）；
    已是干净标准 md（如 Track B 合成）传 normalize=False。
    """
    out = Path(out_dir)
    (out / "md").mkdir(parents=True, exist_ok=True)
    (out / "rendered").mkdir(parents=True, exist_ok=True)
    fmts = formats or DEFAULT_FORMATS
    reg = CleaningRegistry()
    rv = _renderer_version()

    for sample_id, raw in md_sources.items():
        md = normalize_reference_md(raw) if normalize else raw
        if md is None:
            continue
        md_bytes = md.encode("utf-8")
        md_path = out / "md" / f"{sample_id}.md"
        md_path.write_text(md, encoding="utf-8")
        reg.docs.append(
            CleaningDoc(sample_id=sample_id, source=source, md_path=str(md_path), md_hash=_hash(md_bytes))
        )

        targets = list(fmts) + (["md"] if include_md_baseline else [])
        for fmt in targets:
            try:
                data, ext = render(fmt, md, title=sample_id)
            except RuntimeError:  # 渲染依赖缺失（如未装 weasyprint）→ 跳过该格式
                continue
            rpath = out / "rendered" / f"{sample_id}{ext}"
            rpath.write_bytes(data)
            reg.rendered.append(
                RenderedDoc(
                    sample_id=sample_id, fmt=fmt, rendered_path=str(rpath),
                    file_hash=_hash(data), renderer=_RENDERER_OF.get(fmt, "?"),
                    renderer_version=rv,
                )
            )

    reg.save(out / "manifest")
    return reg
