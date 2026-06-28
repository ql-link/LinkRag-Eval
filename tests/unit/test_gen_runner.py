"""run_golden_gen 编排单测(fake sampler/generator/gate,不连 LLM/语料):

- 配额分配:单跳类型按 type_mix 切片、CROSS_DOC 走相邻组。
- 生成器返回 None(答不出)被静默丢弃,不进 golden。
- 门禁:passed 入库、hard 落难例桶、dropped 计数;无门禁则 produced 全入库。
"""

from __future__ import annotations

from linkrag_eval.golden.gen.gate import GateDecision, GateReport
from linkrag_eval.golden.gen.generator import GenerationStats
from linkrag_eval.golden.gen.sampler import SampleSpec, SampledChunk
from linkrag_eval.golden.loader import load_golden
from linkrag_eval.models import QuestionType
from linkrag_eval.runners.gen_runner import run_golden_gen


def _chunk(i: int) -> SampledChunk:
    return SampledChunk(
        chunk_id=f"c{i}", content=f"正文片段编号 {i},含足够信息以供出题。",
        user_id=990001, set_id=990101, doc_id=700 + i, chunk_index=i,
    )


def _sample(cid_list, type_: QuestionType, *, sid: str):
    from linkrag_eval.golden.schema import GoldenSample

    return GoldenSample(
        id=sid, query=f"问题 {sid}", user_id=990001, dataset_ids=[990101],
        expected_chunk_ids=list(cid_list), expected_doc_ids=None,
        golden_answer="答", type=type_, note="test",
    )


class _FakeSampler:
    def __init__(self, singles, groups):
        self._singles = singles
        self._groups = groups
        self.single_spec_n = None
        self.group_spec_n = None

    async def sample_single(self, spec: SampleSpec):
        self.single_spec_n = spec.n
        return list(self._singles)

    async def sample_groups(self, spec: SampleSpec):
        self.group_spec_n = spec.n
        return list(self._groups)


class _FakeGenerator:
    """每次 generate_one 产一条;chunk_id 命中 drop_ids 则返回 None(模拟答不出)。"""

    def __init__(self, *, drop_ids=()):
        self.drop_ids = set(drop_ids)
        self.calls: list[tuple[list[str], QuestionType]] = []
        self.stats = GenerationStats()

    async def generate_one(self, chunks, type_):
        cids = [c.chunk_id for c in chunks]
        self.calls.append((cids, type_))
        self.stats.requested += 1
        if any(c in self.drop_ids for c in cids):
            self.stats.dropped_unanswerable += 1
            return None
        self.stats.produced += 1
        return _sample(cids, type_, sid=f"g-{'_'.join(cids)}")


class TestRunGoldenGen:
    async def test_quota_split_and_write(self, tmp_path):
        # n=10,默认 mix keyword .35 paraphrase .30 longtail .20 cross_doc .15
        # → int 折 3/3/2/1,余 1 给占比最大的 keyword → keyword 4 / paraphrase 3
        #   / longtail 2 / cross_doc 1
        singles = [_chunk(i) for i in range(9)]
        groups = [[_chunk(20), _chunk(21)]]
        sampler = _FakeSampler(singles, groups)
        generator = _FakeGenerator()
        spec = SampleSpec(user_id=990001, dataset_ids=[990101], n=10)

        report = await run_golden_gen(
            sampler=sampler, generator=generator, spec=spec,
            out_path=tmp_path / "golden.jsonl",
        )
        # 单跳采样请求数=keyword+paraphrase+longtail=9;组请求=cross_doc=1
        assert sampler.single_spec_n == 9
        assert sampler.group_spec_n == 1
        # 9 单 + 1 组 = 10 次生成,全部成功
        assert report.produced == 10
        assert report.passed == 10
        types = [t for _, t in generator.calls]
        assert types.count(QuestionType.KEYWORD) == 4
        assert types.count(QuestionType.PARAPHRASE) == 3
        assert types.count(QuestionType.LONGTAIL) == 2
        assert types.count(QuestionType.CROSS_DOC) == 1
        # 落盘可被 load_golden 读回
        loaded = load_golden(tmp_path / "golden.jsonl")
        assert len(loaded) == 10

    async def test_unanswerable_dropped(self, tmp_path):
        singles = [_chunk(i) for i in range(8)]
        sampler = _FakeSampler(singles, [])
        # c0 出题答不出 → None
        generator = _FakeGenerator(drop_ids={"c0"})
        spec = SampleSpec(
            user_id=990001, dataset_ids=[990101], n=8,
            type_mix={QuestionType.KEYWORD: 1.0},
        )
        report = await run_golden_gen(
            sampler=sampler, generator=generator, spec=spec,
            out_path=tmp_path / "g.jsonl",
        )
        assert report.produced == 7          # 8 请求 - 1 丢
        assert "答不出=1" in report.gen_summary

    async def test_gate_splits_passed_hard_dropped(self, tmp_path):
        singles = [_chunk(i) for i in range(4)]
        sampler = _FakeSampler(singles, [])
        generator = _FakeGenerator()
        spec = SampleSpec(
            user_id=990001, dataset_ids=[990101], n=4,
            type_mix={QuestionType.KEYWORD: 1.0},
        )

        seen_chunk_texts = {}

        def gate_factory(chunk_texts):
            seen_chunk_texts.update(chunk_texts)

            class _Gate:
                async def screen(self, samples):
                    rep = GateReport(total=len(samples))
                    rep.passed = samples[:2]
                    rep.hard = samples[2:3]
                    rep.dropped = [GateDecision(s.id, "dropped", "consistency")
                                   for s in samples[3:]]
                    return rep

            return _Gate()

        report = await run_golden_gen(
            sampler=sampler, generator=generator, spec=spec,
            out_path=tmp_path / "g.jsonl", hard_path=tmp_path / "hard.jsonl",
            gate_factory=gate_factory,
        )
        assert report.passed == 2
        assert report.hard == 1
        assert report.dropped == 1
        # 门禁拿到了本轮全部 chunk 正文
        assert set(seen_chunk_texts) == {"c0", "c1", "c2", "c3"}
        assert len(load_golden(tmp_path / "golden.jsonl" if False else tmp_path / "g.jsonl")) == 2
        assert len(load_golden(tmp_path / "hard.jsonl")) == 1
