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
from collections.abc import Iterable, Iterator
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


@dataclass(frozen=True)
class QrelObservation:
    line_number: int
    grade: int


@dataclass(frozen=True)
class ParsedQrels:
    """一个来源文件的四级判断；冲突键不出现在可用 grades 中。"""

    grades: dict[tuple[str, str], int]
    conflicts: dict[tuple[str, str], tuple[QrelObservation, ...]]
    source: str
    row_count: int
    duplicate_rows: int


def _source_id(value: str, *, source: str, lineno: int, field_name: str) -> str:
    if not value or any(c.isspace() for c in value):
        raise ValueError(f"{source}:{lineno} {field_name} 必须是非空、无空白的字符串 ID")
    return value


def _text_rows(
    lines: Iterable[str], *, id_name: str, source: str
) -> Iterator[tuple[int, str, str]]:
    first = True
    for lineno, line in enumerate(lines, start=1):
        line = line.rstrip("\r\n")
        if not line:
            continue
        if first and line == f"{id_name}\ttext":
            first = False
            continue
        first = False
        if "\t" not in line:
            raise ValueError(f"{source}:{lineno} 格式非法（需 {id_name}\\ttext）")
        source_id, text = line.split("\t", 1)
        yield lineno, _source_id(
            source_id, source=source, lineno=lineno, field_name=id_name
        ), text


def parse_t2_queries(lines: Iterable[str], *, source: str = "<memory>") -> dict[str, str]:
    """独立读取完整查询；只移除行结束符，保留正文和来源顺序。

    识别官方表头，也接受现有调用方使用的无表头 TSV。查询不经过 qrels 筛选。
    """
    queries: dict[str, str] = {}
    for lineno, qid, text in _text_rows(lines, id_name="qid", source=source):
        if not text.strip():
            raise ValueError(f"{source}:{lineno} query 正文为空")
        if qid in queries and queries[qid] != text:
            raise ValueError(f"{source}:{lineno} qid 重复且 query 不一致")
        queries[qid] = text
    return queries


def read_t2_queries(path: str | Path) -> dict[str, str]:
    with open(path, encoding="utf-8") as fh:
        return parse_t2_queries(fh, source=str(path))


def parse_t2_collection(
    lines: Iterable[str], *, source: str = "<memory>"
) -> Iterator[tuple[str, str]]:
    """逐段读取原始正文；空正文仍产出供输入侧报告，不在这里静默删除。"""
    seen: set[str] = set()
    for lineno, pid, text in _text_rows(lines, id_name="pid", source=source):
        if pid in seen:
            raise ValueError(f"{source}:{lineno} pid 重复")
        seen.add(pid)
        yield pid, text


def iter_t2_collection(path: str | Path) -> Iterator[tuple[str, str]]:
    with open(path, encoding="utf-8") as fh:
        yield from parse_t2_collection(fh, source=str(path))


def parse_t2_qrels(lines: Iterable[str], *, source: str = "<memory>") -> ParsedQrels:
    """保留四级判断；相同等级去重，冲突保留各等级首次出现的行号。

    两列 retrieval qrels 不能用于此入口。没有记录的 qid/pid 不补零。
    """
    grades: dict[tuple[str, str], int] = {}
    first_lines: dict[tuple[str, str], int] = {}
    conflicts: dict[tuple[str, str], tuple[QrelObservation, ...]] = {}
    row_count = duplicate_rows = 0
    first = True
    for lineno, line in enumerate(lines, start=1):
        line = line.rstrip("\r\n")
        if not line:
            continue
        if first and line == "qid\t-\tpid\trel":
            first = False
            continue
        first = False
        parts = line.split("\t")
        if len(parts) != 4:
            raise ValueError(f"{source}:{lineno} qrels 格式非法（需四列 qid - pid rel）")
        qid = _source_id(parts[0], source=source, lineno=lineno, field_name="qid")
        pid = _source_id(parts[2], source=source, lineno=lineno, field_name="pid")
        if parts[1] not in {"-", "0"} or parts[3] not in {"0", "1", "2", "3"}:
            raise ValueError(f"{source}:{lineno} qrels 格式或等级非法（等级必须是 0、1、2、3）")
        grade = int(parts[3])
        key = (qid, pid)
        row_count += 1
        if key in conflicts:
            if any(item.grade == grade for item in conflicts[key]):
                duplicate_rows += 1
            else:
                conflicts[key] += (QrelObservation(lineno, grade),)
        elif key in grades:
            if grades[key] == grade:
                duplicate_rows += 1
            else:
                conflicts[key] = (
                    QrelObservation(first_lines.pop(key), grades.pop(key)),
                    QrelObservation(lineno, grade),
                )
        else:
            grades[key] = grade
            first_lines[key] = lineno
    return ParsedQrels(grades, conflicts, source, row_count, duplicate_rows)


def read_t2_qrels(path: str | Path) -> ParsedQrels:
    with open(path, encoding="utf-8") as fh:
        return parse_t2_qrels(fh, source=str(path))


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
    """完整读取 T2；旧 QueryJudgment 无法表达冲突时明确拒绝。

    探索输入分别调用 read_t2_queries/read_t2_qrels，不需要加载整个 collection。
    """
    queries = read_t2_queries(queries_path)
    qrels = read_t2_qrels(qrels_path)
    if qrels.conflicts:
        raise ValueError("T2 qrels 存在冲突；请用 read_t2_qrels 保留并处理冲突记录")
    unknown_qids = {qid for qid, _ in qrels.grades if qid not in queries}
    if unknown_qids:
        raise ValueError(f"T2 qrels 含 {len(unknown_qids)} 个不在 queries 中的 qid")
    judged_by_query: dict[str, dict[str, int]] = {}
    for (qid, pid), grade in qrels.grades.items():
        judged_by_query.setdefault(qid, {})[pid] = grade
    corpus = PassageCorpus(dict(iter_t2_collection(collection_path)))
    judgments = [
        QueryJudgment(qid=qid, query=text, judged=judged_by_query.get(qid, {}))
        for qid, text in queries.items()
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
