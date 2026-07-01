"""依赖边界源码扫描守卫(见 AGENTS.md 三)。

import-linter 2.x 不支持把外部包的子模块(如 ``src.config``)作为 forbidden module;
而本项目又必须允许少数 adapter import ``src.*`` 白名单模块。因此这里用源码扫描同时强制:

- rag(``src.*``) import 只许出现在 adapter 白名单文件。
- 黑名单生产模块全仓零直接 import。
"""

from __future__ import annotations

import re
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent / "src" / "linkrag_eval"

# 允许 import toLink-Rag(src.*)的 adapter 文件(相对 PKG_ROOT),按关注点:
#   compute/rag_adapter      —— 纯计算(chunk 切分 + bm25 分词)
#   store/vector_store       —— Qdrant 原语(QdrantIndexStore/BucketRouter/point 模型)
#   retrieval/recall_factory —— 召回装配(被测对象 RecallPipeline,指向 eval 前缀)
#   retrieval/recall_adapter —— RecallRequest/Response marshalling(被测对象类型)
#   cleaning/adapter         —— ParserFactory(CLEANING 层被测对象:清洗/解析那一步)
ALLOWED_RAG_IMPORTERS = {
    "compute/rag_adapter.py",
    "store/vector_store.py",
    "retrieval/recall_factory.py",
    "retrieval/recall_adapter.py",
    "cleaning/adapter.py",
}

_RAG_IMPORT = re.compile(r"^\s*(?:from\s+src[.\s]|import\s+src[.\s])", re.MULTILINE)
_IMPORT_LINE = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import\b|import\s+([\w.]+))", re.MULTILINE)

FORBIDDEN_RAG_PREFIXES = (
    "src.core.storage.es",
    "src.core.storage.vector.sparse_indexing",
    "src.core.storage.vector.pipeline",
    "src.models",
    "src.config",
    "src.core.pipeline.parse_task",
    "src.services.storage",
    "src.core.storage.chunks.repository",
)


def _rel(p: Path) -> str:
    return p.relative_to(PKG_ROOT).as_posix()


def test_rag_imports_confined_to_two_files() -> None:
    offenders: list[str] = []
    for py in PKG_ROOT.rglob("*.py"):
        rel = _rel(py)
        if rel in ALLOWED_RAG_IMPORTERS:
            continue
        if _RAG_IMPORT.search(py.read_text(encoding="utf-8")):
            offenders.append(rel)
    assert not offenders, (
        "以下文件违规 import 了 toLink-Rag(src.*),只允许在 "
        f"{sorted(ALLOWED_RAG_IMPORTERS)} 中出现:\n  " + "\n  ".join(offenders)
    )


def test_forbidden_rag_modules_are_not_imported() -> None:
    offenders: list[str] = []
    for py in PKG_ROOT.rglob("*.py"):
        rel = _rel(py)
        text = py.read_text(encoding="utf-8")
        for match in _IMPORT_LINE.finditer(text):
            module = match.group(1) or match.group(2) or ""
            if any(module == p or module.startswith(f"{p}.") for p in FORBIDDEN_RAG_PREFIXES):
                offenders.append(f"{rel}: {module}")
    assert not offenders, (
        "以下文件违规 import 了生产黑名单模块:\n  " + "\n  ".join(offenders)
    )
