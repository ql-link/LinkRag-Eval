"""自动质量门禁三信号单测（fake 复核模型 + 独立检索器）。"""

from __future__ import annotations

from linkrag_eval.golden.gen.gate import AutoQualityGate
from linkrag_eval.golden.schema import GoldenSample


def make_sample(sid: str = "s1", answer: str | None = "7B") -> GoldenSample:
    return GoldenSample(
        id=sid, query="模型 X 参数量是多少", user_id=990001, dataset_ids=[990101],
        expected_chunk_ids=["c1"], golden_answer=answer,
    )


CHUNK_TEXTS = {"c1": "模型 X 的参数量为 7B。"}


class ScriptedLLM:
    """按调用顺序回放预设输出（信号一 → 信号三）。"""

    def __init__(self, outputs: list[str]):
        self.outputs = list(outputs)
        self.prompts: list[str] = []

    async def generate(self, prompt, system_prompt=None, temperature=0.7,
                       max_tokens=None, **kw):
        self.prompts.append(prompt)

        class R:
            pass

        r = R()
        r.content = self.outputs.pop(0)
        return r


def hit_retriever(query: str) -> list[str]:
    return ["c1", "c2"]


def miss_retriever(query: str) -> list[str]:
    return ["c8", "c9"]


ANSWERABLE = '{"answerable": true, "answer": "参数量是 7B"}'
UNANSWERABLE = '{"answerable": false}'
CONSISTENT = '{"consistent": true}'
INCONSISTENT = '{"consistent": false, "reason": "数值不同"}'


class TestGateSignals:
    async def test_all_pass(self):
        gate = AutoQualityGate(
            ScriptedLLM([ANSWERABLE, CONSISTENT]), "judge-m", hit_retriever, CHUNK_TEXTS
        )
        report = await gate.screen([make_sample()])
        assert report.passed and not report.dropped and not report.hard
        assert report.pass_rate == 1.0

    async def test_signal1_unanswerable_drops(self):
        gate = AutoQualityGate(
            ScriptedLLM([UNANSWERABLE]), "m", hit_retriever, CHUNK_TEXTS
        )
        report = await gate.screen([make_sample()])
        assert report.dropped[0].failed_signal == "answerability"

    async def test_signal3_inconsistent_drops(self):
        gate = AutoQualityGate(
            ScriptedLLM([ANSWERABLE, INCONSISTENT]), "m", hit_retriever, CHUNK_TEXTS
        )
        report = await gate.screen([make_sample()])
        assert report.dropped[0].failed_signal == "consistency"
        assert "数值不同" in report.dropped[0].detail

    async def test_signal2_miss_goes_to_hard_bucket(self):
        # 回环不命中 → 难例桶单列，不丢弃不混入
        gate = AutoQualityGate(
            ScriptedLLM([ANSWERABLE, CONSISTENT]), "m", miss_retriever, CHUNK_TEXTS
        )
        report = await gate.screen([make_sample()])
        assert report.hard and not report.dropped and not report.passed
        assert report.decisions[0].failed_signal == "retrieval_loop"

    async def test_no_golden_answer_skips_consistency(self):
        # 无 golden_answer（如日志种子未补标）只跑信号一与回环
        gate = AutoQualityGate(
            ScriptedLLM([ANSWERABLE]), "m", hit_retriever, CHUNK_TEXTS
        )
        report = await gate.screen([make_sample(answer=None)])
        assert report.passed

    async def test_missing_chunk_text_drops(self):
        gate = AutoQualityGate(ScriptedLLM([]), "m", hit_retriever, chunk_texts={})
        report = await gate.screen([make_sample()])
        assert report.dropped[0].detail == "expected chunk 正文缺失"

    async def test_async_retriever_supported(self):
        async def async_retriever(query: str) -> list[str]:
            return ["c1"]

        gate = AutoQualityGate(
            ScriptedLLM([ANSWERABLE, CONSISTENT]), "m", async_retriever, CHUNK_TEXTS
        )
        report = await gate.screen([make_sample()])
        assert report.passed

    async def test_report_rates_and_summary(self):
        gate = AutoQualityGate(
            ScriptedLLM([ANSWERABLE, CONSISTENT, UNANSWERABLE]),
            "m", hit_retriever, CHUNK_TEXTS,
        )
        report = await gate.screen([make_sample("s1"), make_sample("s2")])
        assert report.total == 2
        assert report.pass_rate == 0.5 and report.drop_rate == 0.5
        assert "通过 1" in report.summary()
