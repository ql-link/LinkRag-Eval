"""辅路 · 自有 chunk 反向合成:采样 → LLM 生成 → 自动质量门禁,全程无人工。

采样器 ``ChunkSampler`` 读 **eval 自有语料**(EvalCorpusRepo,非生产 ChunkRecordDB)。
"""

from linkrag_eval.golden.gen.gate import AutoQualityGate, GateReport
from linkrag_eval.golden.gen.generator import (
    GenChunk,
    GenerationStats,
    GoldenGenerator,
    TextClient,
)
from linkrag_eval.golden.gen.lexical import SimpleBM25Retriever
from linkrag_eval.golden.gen.prompts import (
    build_generation_prompt,
    build_seed_annotation_prompt,
    parse_llm_json,
)
from linkrag_eval.golden.gen.sampler import (
    ChunkSampler,
    SampledChunk,
    SampleSpec,
    group_adjacent,
    stratified_pick,
)

__all__ = [
    "AutoQualityGate",
    "ChunkSampler",
    "GateReport",
    "GenChunk",
    "GenerationStats",
    "GoldenGenerator",
    "SampleSpec",
    "SampledChunk",
    "SimpleBM25Retriever",
    "TextClient",
    "build_generation_prompt",
    "build_seed_annotation_prompt",
    "group_adjacent",
    "parse_llm_json",
    "stratified_pick",
]
