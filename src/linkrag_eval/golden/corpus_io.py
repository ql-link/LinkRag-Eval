"""语料/manifest 读取器(纯文件解析,eval 自持,零生产依赖)。

口径对齐源仓库:
- collection.tsv:逐行 ``pid\\ttext``(pid=首列,text=末列;空行跳过,pid 重复报错)。
- manifest jsonl:逐行 ``{source_id, doc_id, status}``;灌库只取 ``status=="success"``。

灌库时 ``source_id``(pid)↔ ``doc_id`` 的映射来自 manifest,正文来自 collection,二者按 pid 对齐。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


def read_tsv_collection(path: str | Path) -> dict[str, str]:
    """读 ``pid\\ttext`` → ``{pid: text}``。pid 重复报错;空 pid/text 跳过。"""
    passages: dict[str, str] = {}
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                raise ValueError(f"{path}:{lineno} collection 行格式非法(需 pid\\ttext)")
            pid, text = parts[0].strip(), parts[-1].strip()
            if not pid or not text:
                continue
            if pid in passages:
                raise ValueError(f"{path}:{lineno} pid 重复: {pid}")
            passages[pid] = text
    return passages


@dataclass(frozen=True)
class ManifestRecord:
    source_id: str   # 语料单元标识(开源 pid / 合成 doc 名)
    doc_id: int      # chunk.doc_id 即它
    status: str      # success / failed
    ordinal: int = 0 # doc 内 chunk 序号;老 manifest 不提供时默认 0


def load_manifest(path: str | Path) -> list[ManifestRecord]:
    """读 manifest jsonl → ``[ManifestRecord]``(source_id ↔ doc_id + 灌库状态)。"""
    records: list[ManifestRecord] = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                records.append(
                    ManifestRecord(
                        source_id=str(d["source_id"]),
                        doc_id=int(d["doc_id"]),
                        status=str(d.get("status", "success")),
                        ordinal=int(d.get("ordinal", 0)),
                    )
                )
            except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
                raise ValueError(f"{path}:{lineno} manifest 行非法: {exc}") from exc
    return records


def write_manifest(records: list[ManifestRecord], path: str | Path) -> Path:
    """写 manifest jsonl(灌库 source_id↔doc_id↔status 锚点,供 convert/灌库下游消费)。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(
                json.dumps(
                    {
                        "source_id": r.source_id,
                        "doc_id": r.doc_id,
                        "status": r.status,
                        "ordinal": r.ordinal,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    return path
