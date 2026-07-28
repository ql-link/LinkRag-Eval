"""开源检索数据集读取：DuReader_retrieval / T2Ranking 的本地文件解析。

数据文件由使用者按各自仓库说明下载到本地（Apache-2.0），此处只做格式解析，
统一产出 PassageCorpus（pid→正文）与 QueryJudgment 列表（query→pid 标注）。

格式约定：
- T2Ranking：collection.tsv（pid\\ttext）、queries.tsv（qid\\tquery）、
  qrels tsv（qid\\t0\\tpid\\trel，rel 0-3 分级，TREC 格式）。
- DuReader_retrieval：passage collection tsv（pid\\ttext，部分发行版多一列段内
  id，取首尾两列）、dev/qrels json（{qid: [pid,...]}）或 TREC tsv，二值相关。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PassageCorpus:
    """pid → 段落正文。一个段落 = 一个 ingestion 单元 = 库内一个 doc_id。"""

    passages: dict[str, str] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.passages)


@dataclass(frozen=True)
class QueryJudgment:
    qid: str
    query: str
    # pid → 相关级别。二值数据集恒为 1；T2Ranking 为 0-3（0 视为不相关，转换时过滤）
    judged: dict[str, int] = field(default_factory=dict)

    @property
    def positive_pids(self) -> list[str]:
        return [pid for pid, rel in self.judged.items() if rel > 0]


def _read_tsv_collection(path: str | Path) -> PassageCorpus:
    corpus = PassageCorpus()
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                raise ValueError(f"{path}:{lineno} collection 行格式非法（需 pid\\ttext）")
            pid, text = parts[0].strip(), parts[-1].strip()
            if not pid or not text:
                continue
            if pid in corpus.passages:
                raise ValueError(f"{path}:{lineno} pid 重复: {pid}")
            corpus.passages[pid] = text
    return corpus


def _read_tsv_queries(path: str | Path) -> dict[str, str]:
    queries: dict[str, str] = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2 and parts[0].strip():
                queries[parts[0].strip()] = parts[1].strip()
    return queries


def _read_trec_qrels(path: str | Path) -> dict[str, dict[str, int]]:
    """TREC qrels：qid <ignored> pid rel（tab 或空白分隔）。"""
    qrels: dict[str, dict[str, int]] = {}
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t") if "\t" in line else line.split()
            if len(parts) < 4:
                raise ValueError(f"{path}:{lineno} qrels 行格式非法（需 qid 0 pid rel）")
            qid, pid, rel = parts[0], parts[2], int(parts[3])
            qrels.setdefault(qid, {})[pid] = rel
    return qrels


def load_t2ranking(
    collection_path: str | Path,
    queries_path: str | Path,
    qrels_path: str | Path,
) -> tuple[PassageCorpus, list[QueryJudgment]]:
    """T2Ranking：4 级分级相关（保留 grade，供分级 NDCG）。"""
    corpus = _read_tsv_collection(collection_path)
    queries = _read_tsv_queries(queries_path)
    qrels = _read_trec_qrels(qrels_path)
    judgments = [
        QueryJudgment(qid=qid, query=queries[qid], judged=dict(judged))
        for qid, judged in sorted(qrels.items())
        if qid in queries
    ]
    return corpus, judgments


def load_dureader_retrieval(
    collection_path: str | Path,
    queries_path: str | Path,
    qrels_path: str | Path,
) -> tuple[PassageCorpus, list[QueryJudgment]]:
    """DuReader_retrieval：二值相关。qrels 支持 TREC tsv 或 {qid: [pid,...]} json。"""
    corpus = _read_tsv_collection(collection_path)
    queries = _read_tsv_queries(queries_path)

    qrels_path = Path(qrels_path)
    if qrels_path.suffix == ".json":
        raw = json.loads(qrels_path.read_text(encoding="utf-8"))
        qrels = {qid: {pid: 1 for pid in pids} for qid, pids in raw.items()}
    else:
        qrels = _read_trec_qrels(qrels_path)

    judgments = [
        QueryJudgment(
            qid=qid,
            query=queries[qid],
            judged={pid: (1 if rel > 0 else 0) for pid, rel in judged.items()},
        )
        for qid, judged in sorted(qrels.items())
        if qid in queries
    ]
    return corpus, judgments
