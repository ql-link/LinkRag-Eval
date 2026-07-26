"""清洗评测语料对应关系（phase0_5 §3 / eval_storage §3.6）：md ↔ 各渲染件。

阶段一把标准 md 渲染成各格式并**记对应关系**，阶段二照表取渲染件清洗比对。
这里用文件后端（两个 jsonl，对应 eval_cleaning_doc / eval_cleaning_rendered
两张表的 1:N）落地——首版零基建；切 DB 后字段一一对应、可平滑迁移。

对应关系表是阶段一↔阶段二、以及跨 run 复现的锚点：`md_hash` / `renderer_version`
保证"语料 / 渲染没变"才同口径比。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from linkrag_eval.cleaning.adapter import RenderedRef


@dataclass
class CleaningDoc:
    """一篇标准 md（参考真值）= eval_cleaning_doc 行。"""

    sample_id: str
    source: str                  # chinese-markdown / synth / opendataset / curated
    md_path: str                 # 参考 md 本地路径（切 MinIO 后为 object_key）
    md_hash: str                 # 内容指纹，绑定版本


@dataclass
class RenderedDoc:
    """一个渲染件（md × 格式）= eval_cleaning_rendered 行。

    不含 pdf_backend：backend 是清洗（解析）期变量、不是渲染期变量；同一份 PDF
    渲染件在质检时按多个 backend 各跑一次（runner 枚举）。
    """

    sample_id: str               # → CleaningDoc.sample_id（对应关系锚点）
    fmt: str                     # pdf / docx / html / md
    rendered_path: str           # 渲染件本地路径（切 MinIO 后为 object_key）
    file_hash: str
    renderer: str                # weasyprint / pandoc / python-docx ...
    renderer_version: str        # 进表并冻结：换版本=换输入，不混比


@dataclass
class CleaningRegistry:
    """对应关系表的文件后端：docs.jsonl + rendered.jsonl。"""

    docs: list[CleaningDoc] = field(default_factory=list)
    rendered: list[RenderedDoc] = field(default_factory=list)

    def md_path_of(self, sample_id: str) -> str:
        for d in self.docs:
            if d.sample_id == sample_id:
                return d.md_path
        raise KeyError(f"未登记的参考 md: {sample_id}")

    def iter_rendered_refs(self, *, pdf_backends: list[str] | None = None):
        """展开成 RenderedRef 序列：PDF 件按 pdf_backends 各产一条，其余各一条。"""
        backends = pdf_backends or ["auto"]
        for r in self.rendered:
            md_ref = self.md_path_of(r.sample_id)
            if r.fmt == "pdf":
                for backend in backends:
                    yield RenderedRef(
                        sample_id=r.sample_id, fmt="pdf",
                        rendered_path=r.rendered_path, md_ref_path=md_ref,
                        pdf_backend=backend,
                    )
            else:
                yield RenderedRef(
                    sample_id=r.sample_id, fmt=r.fmt,
                    rendered_path=r.rendered_path, md_ref_path=md_ref,
                    pdf_backend=None,
                )

    def save(self, manifest_dir: str | Path) -> Path:
        d = Path(manifest_dir)
        d.mkdir(parents=True, exist_ok=True)
        _write_jsonl(d / "docs.jsonl", [asdict(x) for x in self.docs])
        _write_jsonl(d / "rendered.jsonl", [asdict(x) for x in self.rendered])
        return d

    @classmethod
    def load(cls, manifest_dir: str | Path) -> "CleaningRegistry":
        d = Path(manifest_dir)
        docs = [CleaningDoc(**row) for row in _read_jsonl(d / "docs.jsonl")]
        rendered = [RenderedDoc(**row) for row in _read_jsonl(d / "rendered.jsonl")]
        return cls(docs=docs, rendered=rendered)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
