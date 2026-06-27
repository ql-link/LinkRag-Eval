"""反向合成生成器单测:prompt JSON 解析、GoldenGenerator、独立 BM25。

搬迁自源仓库 test_gen.py 的生成部分;采样分层(SampleSpec/stratified_pick/group_adjacent)
随 Stage 5 sampler 解耦重写后补测。
"""

from __future__ import annotations

from dataclasses import dataclass

from linkrag_eval.golden.gen.generator import GoldenGenerator
from linkrag_eval.golden.gen.lexical import SimpleBM25Retriever, tokenize
from linkrag_eval.golden.gen.prompts import build_generation_prompt, parse_llm_json
from linkrag_eval.models import QuestionType


@dataclass
class FakeChunk:
    chunk_id: str
    doc_id: int
    set_id: int
    user_id: int = 990001
    content: str = "x" * 100
    chunk_type: str = "text"
    chunk_index: int | None = None


class TestParseLlmJson:
    def test_plain(self):
        assert parse_llm_json('{"a": 1}') == {"a": 1}

    def test_code_fence(self):
        assert parse_llm_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_trailing_text(self):
        assert parse_llm_json('{"a": {"b": "}"}} 其他话') == {"a": {"b": "}"}}

    def test_leading_text(self):
        assert parse_llm_json('好的,结果如下:{"a": 1}') == {"a": 1}

    def test_garbage(self):
        assert parse_llm_json("完全不是 JSON") is None
        assert parse_llm_json('{"broken": ') is None

    def test_non_dict(self):
        assert parse_llm_json("[1,2]") is None


class FakeLLM:
    def __init__(self, content: str):
        self.content = content
        self.calls: list[dict] = []

    async def generate(self, prompt, system_prompt=None, temperature=0.7,
                       max_tokens=None, **kw):
        self.calls.append({"prompt": prompt, "temperature": temperature})

        class R:
            pass

        r = R()
        r.content = self.content
        return r


class TestGoldenGenerator:
    def chunks(self):
        return [
            FakeChunk("c1", doc_id=11, set_id=990101, content="深度学习模型 X 的参数量为 7B。"),
            FakeChunk("c2", doc_id=11, set_id=990101, content="模型 X 发布于 2025 年。"),
        ]

    async def test_produces_sample(self):
        llm = FakeLLM(
            '{"answerable": true, "query": "模型 X 参数量是多少", '
            '"golden_answer": "7B", "used_chunk_ids": ["c1"], "reason": "直接事实"}'
        )
        gen = GoldenGenerator(llm, "gen-model")
        sample = await gen.generate_one(self.chunks(), QuestionType.KEYWORD)
        assert sample is not None
        assert sample.expected_chunk_ids == ["c1"]
        assert sample.expected_doc_ids == [11]
        assert sample.dataset_ids == [990101]
        assert sample.golden_answer == "7B"
        assert gen.stats.produced == 1

    async def test_unanswerable_dropped(self):
        gen = GoldenGenerator(FakeLLM('{"answerable": false}'), "m")
        assert await gen.generate_one(self.chunks(), QuestionType.KEYWORD) is None
        assert gen.stats.dropped_unanswerable == 1

    async def test_parse_error_dropped(self):
        gen = GoldenGenerator(FakeLLM("不是 JSON"), "m")
        assert await gen.generate_one(self.chunks(), QuestionType.KEYWORD) is None
        assert gen.stats.dropped_parse_error == 1

    async def test_unknown_used_ids_fall_back_to_all(self):
        llm = FakeLLM(
            '{"answerable": true, "query": "q", "golden_answer": "a", '
            '"used_chunk_ids": ["nonexistent"]}'
        )
        sample = await GoldenGenerator(llm, "m").generate_one(
            self.chunks(), QuestionType.CROSS_DOC
        )
        assert sample.expected_chunk_ids == ["c1", "c2"]

    def test_prompt_contains_chunks_and_schema(self):
        system, user = build_generation_prompt(
            QuestionType.CROSS_DOC, [("c1", "正文一"), ("c2", "正文二")]
        )
        assert "JSON" in system
        assert "[片段 c1]" in user and "正文二" in user
        assert "answerable" in user
        assert "禁止任何单一片段" in user


class TestSimpleBM25:
    def test_chinese_retrieval(self):
        corpus = {
            "c1": "向量检索基于稠密向量的近邻搜索实现语义匹配。",
            "c2": "BM25 是基于词频的经典词法检索算法。",
            "c3": "今天天气很好,适合出门散步。",
        }
        r = SimpleBM25Retriever(corpus)
        assert r.search("什么是向量检索", top_n=2)[0] == "c1"
        assert r.search("BM25 算法", top_n=2)[0] == "c2"

    def test_no_match(self):
        r = SimpleBM25Retriever({"c1": "abc"})
        assert r.search("零零零", top_n=5) == []

    def test_tokenize_mixed(self):
        toks = tokenize("BM25 检索")
        assert "bm25" in toks
        assert "检" in toks and "检索" in toks

    def test_bigram_does_not_cross_punctuation(self):
        toks = tokenize("向量。检索")
        assert "向量" in toks and "检索" in toks
        assert "量检" not in toks

    def test_bigram_does_not_cross_latin(self):
        toks = tokenize("中文ABC检索")
        assert "文检" not in toks
        assert "abc" in toks
