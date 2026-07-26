"""GoldenGenerator:chunk(s) → LLM → GoldenSample。

搬迁自源仓库 ``gen/generator.py``。``TextClient`` 是生成调用面,由
:class:`linkrag_eval.judge.EvalChatClient` 满足(其 ``generate`` 返回带 ``.content`` 的结果)。
temperature 适度(生成多样性,区别于判官的 0);answerable=false / 解析失败静默丢弃并计数,
不污染产出。生成器模型须与门禁复核/判官/被测错开(快照校验)。

解耦要点:源版把 chunk 标注成生产 ``ChunkRecordDB`` 类型,但代码全程鸭子类型只用
``chunk_id/content/user_id/set_id/doc_id``;这里改用结构化 :class:`GenChunk` Protocol,
零 rag——eval 侧采样器(读 eval 语料)产出满足该形状的对象即可。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol, Sequence, runtime_checkable

from linkrag_eval.golden.gen.prompts import (
    build_generation_prompt,
    build_seed_annotation_prompt,
    parse_llm_json,
)
from linkrag_eval.golden.schema import GoldenSample
from linkrag_eval.models import QuestionType


@runtime_checkable
class TextClient(Protocol):
    """生成调用面(与 judge ``EvalChatClient.generate`` 兼容)。"""

    async def generate(self, prompt: str, system_prompt: str | None = None,
                       temperature: float = 0.7, max_tokens: int | None = None,
                       **kwargs) -> object: ...


@runtime_checkable
class GenChunk(Protocol):
    """生成器消费的 chunk 结构(eval 语料行 / 采样产物只需满足这几个字段)。"""

    chunk_id: str
    content: str
    user_id: int
    set_id: int
    doc_id: int


@dataclass
class GenerationStats:
    requested: int = 0
    produced: int = 0
    dropped_unanswerable: int = 0
    dropped_parse_error: int = 0
    dropped_invalid: int = 0
    errors: list[str] = field(default_factory=list)


class GoldenGenerator:
    def __init__(
        self,
        client: TextClient,
        generator_model: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ):
        self.client = client
        self.generator_model = generator_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.stats = GenerationStats()

    async def generate_one(
        self, chunks: Sequence[GenChunk], type_: QuestionType
    ) -> GoldenSample | None:
        self.stats.requested += 1
        system, user = build_generation_prompt(
            type_, [(c.chunk_id, c.content) for c in chunks]
        )
        return await self._call_and_build(system, user, chunks, type_, note_prefix="synth")

    async def annotate_seed(
        self, seed_query: str, chunks: Sequence[GenChunk]
    ) -> GoldenSample | None:
        """真实 query 日志种子冷启动:补标命中 chunk 与 golden_answer。"""
        self.stats.requested += 1
        system, user = build_seed_annotation_prompt(
            seed_query, [(c.chunk_id, c.content) for c in chunks]
        )
        return await self._call_and_build(
            system, user, chunks, QuestionType.KEYWORD, note_prefix="log-seed",
        )

    async def _call_and_build(
        self,
        system: str,
        user: str,
        chunks: Sequence[GenChunk],
        type_: QuestionType,
        *,
        note_prefix: str,
    ) -> GoldenSample | None:
        result = await self.client.generate(
            prompt=user,
            system_prompt=system,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        data = parse_llm_json(getattr(result, "content", "") or "")
        if data is None:
            self.stats.dropped_parse_error += 1
            return None
        if not data.get("answerable"):
            self.stats.dropped_unanswerable += 1
            return None
        query = (data.get("query") or "").strip()
        answer = (data.get("golden_answer") or "").strip()
        if not query or not answer:
            self.stats.dropped_invalid += 1
            return None

        chunk_by_id = {c.chunk_id: c for c in chunks}
        used = [c for c in (data.get("used_chunk_ids") or []) if c in chunk_by_id]
        expected = used or list(chunk_by_id)
        records = [chunk_by_id[c] for c in expected]
        self.stats.produced += 1
        return GoldenSample(
            id=f"{note_prefix}-{uuid.uuid4().hex[:12]}",
            query=query,
            user_id=records[0].user_id,
            dataset_ids=sorted({r.set_id for r in records}),
            expected_chunk_ids=expected,
            expected_doc_ids=sorted({r.doc_id for r in records}),
            golden_answer=answer,
            type=type_,
            note=f"{note_prefix}; generator={self.generator_model}; "
            f"reason={(data.get('reason') or '').strip()}",
        )
