"""依赖边界 grep 守卫(见 AGENTS.md 三)。

强制"rag(``src.*``)的 import 只许出现在 compute/rag_adapter.py 与 retrieval/recall_factory.py
两个文件"——import-linter 的 forbidden 契约不便表达白名单豁免,故用源码扫描兜这条。
.importlinter 负责黑名单(禁 import 的具体生产模块)。
"""

from __future__ import annotations

import re
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent / "linkrag_eval"

# 唯一允许 import toLink-Rag(src.*)的文件(相对 PKG_ROOT)。
ALLOWED_RAG_IMPORTERS = {
    "compute/rag_adapter.py",
    "retrieval/recall_factory.py",
}

_RAG_IMPORT = re.compile(r"^\s*(?:from\s+src[.\s]|import\s+src[.\s])", re.MULTILINE)


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
