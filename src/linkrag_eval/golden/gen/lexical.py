"""独立词法检索器（gate 信号二用）：纯 Python BM25，与被测系统完全无关。

为什么不用被测召回（B2 防循环论证）：用待评测的召回链路去筛黄金集，会把
"现有配置召不回但其实是好题"的样本踢掉，使黄金集偏向当前 baseline。
此实现零外部依赖（中文按字符 unigram + 段内 bigram + 英文/数字 token 切分），
只为门禁回环信号，不追求检索质量。
"""

from __future__ import annotations

import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")
_CJK_RUN_RE = re.compile(r"[一-鿿]+")
_K1 = 1.5
_B = 0.75


def tokenize(text: str) -> list[str]:
    """英文/数字按词；中文按字符 unigram + **段内** bigram（无外部分词依赖）。

    bigram 只在连续中文片段内组合，不跨标点/空白/非中文边界——否则
    "向量。检索" 会误造出 "量检" 这种跨句噪声词，干扰回环命中判断。
    """
    text = text.lower()
    tokens = _TOKEN_RE.findall(text)
    for run in _CJK_RUN_RE.findall(text):
        tokens.extend(run)                                      # unigram
        tokens.extend(run[i : i + 2] for i in range(len(run) - 1))  # 段内 bigram
    return tokens


class SimpleBM25Retriever:
    """对 {chunk_id: content} 语料建内存 BM25 索引，search 返回 top-N chunk_id。"""

    def __init__(self, corpus: dict[str, str]):
        self.doc_tokens = {cid: tokenize(text) for cid, text in corpus.items()}
        self.doc_len = {cid: len(toks) for cid, toks in self.doc_tokens.items()}
        self.avg_len = (
            sum(self.doc_len.values()) / len(self.doc_len) if self.doc_len else 0.0
        )
        self.tf: dict[str, Counter] = {
            cid: Counter(toks) for cid, toks in self.doc_tokens.items()
        }
        df: Counter = Counter()
        for toks in self.doc_tokens.values():
            df.update(set(toks))
        n = len(self.doc_tokens)
        self.idf = {
            term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()
        }

    def search(self, query: str, top_n: int = 10) -> list[str]:
        q_tokens = tokenize(query)
        scores: dict[str, float] = {}
        for cid, tf in self.tf.items():
            dl = self.doc_len[cid]
            score = 0.0
            for term in q_tokens:
                if term not in tf:
                    continue
                idf = self.idf.get(term, 0.0)
                freq = tf[term]
                denom = freq + _K1 * (1 - _B + _B * dl / (self.avg_len or 1))
                score += idf * freq * (_K1 + 1) / denom
            if score > 0:
                scores[cid] = score
        return [cid for cid, _ in sorted(scores.items(), key=lambda kv: -kv[1])[:top_n]]
