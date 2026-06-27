"""灌库编排(``EvalVectorIndexer``)——取代源仓库 ``live_indexer.py``,是解耦承重墙本体。

把 passage 经 ``ProductComputer`` 算出产物(dense / sparse / [bm25])→ ``EvalVectorStore`` 写
eval 前缀 Qdrant → ``EvalCorpusRepo`` 落 Postgres。**不 import 任何生产写 pipeline / ORM**,
全部经 compute/store 抽象;rag 仅在 rag_adapter / vector_store 两个 adapter 内被触碰。

passage 语义:一个 passage 即一个 chunk(``ordinal`` 为 doc 内序号);需切分的 corpus 走另一条
路径(compute_chunks,后续接)。bm25 路按 mode 可插拔:P1 ``stub`` 只跑 dense+sparse 两路。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from linkrag_eval.compute.protocol import ProductComputer
from linkrag_eval.store.corpus_repo import CorpusChunkRow, EvalCorpusRepo
from linkrag_eval.store.ids import content_hash, eval_chunk_id
from linkrag_eval.store.vector_store import EvalPoint, EvalVectorStore


@dataclass(frozen=True)
class EvalPassage:
    """评测语料单元:一个 passage = 一个 chunk(doc_id 为合成 doc)。"""

    source_passage_id: str
    content: str
    doc_id: int
    ordinal: int = 0


class EvalVectorIndexer:
    """编排产物计算 → 向量库 + 语料库。dense 必算;sparse 视 ``with_sparse``;bm25 视 ``bm25_mode``。"""

    def __init__(
        self,
        *,
        computer: ProductComputer,
        vector_store: EvalVectorStore,
        corpus_repo: EvalCorpusRepo,
        with_sparse: bool = True,
        bm25_mode: str = "stub",
        run_id: str | None = None,
    ) -> None:
        self._computer = computer
        self._vstore = vector_store
        self._repo = corpus_repo
        self._with_sparse = with_sparse
        self._bm25_mode = bm25_mode
        self._run_id = run_id

    async def index_passages(self, dataset_id: int, passages: Sequence[EvalPassage]) -> int:
        """算产物 → 写 Qdrant → 落 Postgres。返回写入 chunk 数。

        失败上抛、不落库——避免"库里标已索引、实则没进 Qdrant"的静默假成功。
        """
        items = list(passages)
        if not items:
            return 0

        contents = [p.content for p in items]
        dense = await self._computer.compute_dense(contents)
        if len(dense) != len(items):
            raise ValueError(f"dense 数量不符:{len(dense)} != {len(items)}")

        sparse = None
        if self._with_sparse:
            sparse = await self._computer.compute_sparse(contents)
            if len(sparse) != len(items):
                raise ValueError(f"sparse 数量不符:{len(sparse)} != {len(items)}")

        bm25_on = self._bm25_mode != "stub"  # P1 stub:不写 bm25 路

        points: list[EvalPoint] = []
        rows: list[CorpusChunkRow] = []
        for i, p in enumerate(items):
            cid = eval_chunk_id(dataset_id, p.doc_id, p.ordinal)
            points.append(
                EvalPoint(
                    chunk_id=cid,
                    doc_id=p.doc_id,
                    dense=dense[i].values,
                    sparse=(sparse[i] if sparse is not None else None),
                )
            )
            rows.append(
                CorpusChunkRow(
                    chunk_id=cid,
                    dataset_id=dataset_id,
                    doc_id=p.doc_id,
                    content=p.content,
                    content_hash=content_hash(p.content),
                    source_passage_id=p.source_passage_id,
                    ordinal=p.ordinal,
                    char_len=len(p.content),
                    dense_indexed=True,
                    sparse_indexed=sparse is not None,
                    bm25_indexed=bm25_on,
                    ingest_run_id=self._run_id,
                )
            )

        await self._vstore.upsert(dataset_id=dataset_id, points=points)
        await self._repo.upsert_chunks(rows)
        return len(items)
