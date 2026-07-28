# 阶段 3 · 生成 + 正确性层 — 设计文档

> **归档文档：仅供追溯，不是当前权威依据。** 替代关系见 [归档说明](../README.md)。

> 状态：设计稿（`.specs/rag-quality-eval/`，git-ignored）
> 上游：[framework_design.md](framework_design.md)（总架构）、[phase0_design.md](phase0_design.md)（抽象/模型，含 `Judge`）、[phase2_rerank_design.md](phase2_rerank_design.md)（本层上游产出）、[phase1_5_golden_gen_design.md](phase1_5_golden_gen_design.md)（`golden_answer` 来源）、[technical_design.md](technical_design.md) §第2/3层
> 范围：评估链路最后一层——生成答案的质量（RAG Triad）与端到端正确性（需标准答案），模块 18–21。
> 前置：① **R1 非流式生成入口**（由你提前完成，`core` 侧，契约见 §三）；② 阶段 1.5 产出的含 `golden_answer` 黄金集；③ 冻结租户配置可用 CHAT 模型。

---

## 一、结论先行

本层回答两类问题：答案**忠实、相关**与否（RAG Triad，不需标准答案），以及答案**正确**与否（需 `golden_answer`）。三条决策：

1. **判官能力经 `Judge` 抽象隔离，先集成 RAGAS、后可内化。** 第 2/3 层共用一套 LLM 判官。首版用 RAGAS 拿其已校准的 LLM-as-judge prompt 快速见数；`Judge` 协议（phase0 §4.4）让后续把高频指标内化为自研、接回项目自身 `ModelFactory`，对上层零改动。
2. **RAGAS 惰性导入、隔离在 `[eval]` extra。** 仅 `metrics/generation.py` 与 RAGAS 判官实现 import 它，生产镜像不含；第 1/2 层零外部依赖不受影响。
3. **三模型错配是硬纪律。** 判官 / 被测 CHAT / 黄金集生成器三者不得同一，否则系统性高估 faithfulness/correctness。`snapshot.validate_model_distinctness` 同名即告警/拒绝（phase0 已留）。

依赖：生成适配器对接 R1 非流式入口（`core`），core-only；判官依赖经 extra 隔离。

---

## 二、被依赖的生产接缝

| 用途 | 入口 | 说明 |
| --- | --- | --- |
| 非流式生成（R1，你自建） | `core` 侧新入口，契约见 §三 | 复用 `assemble_context` / `build_rag_user_prompt` / `RAG_GENERATION_SYSTEM_PROMPT` / `provider.generate` |
| LLM 非流式原语 | `ITextGenerator.generate(prompt, system_prompt=None, temperature=0.7, max_tokens=None)` → `GenerateResult` | **已存在**，无需新实现 |
| CHAT 模型解析 | `aresolve_user_model(*, user_id, capability="CHAT", ...)`（参数 keyword-only） | 解析被测租户 CHAT 模型 |
| 上下文拼装 | `assemble_context(hits, contents, token_budget)` → `AssembledContext(blocks, context_text, skipped_no_content, truncated)` | 已有 |
| 正文回填 | `fetch_chunk_contents(chunk_ids, user_id)` | 已有 |

> **R1 的真相**：`provider.generate()` 早已存在，R1 **不是实现非流式推理**，而是把现有 `_generate_answer`（`src/application/recall_stream_runtime.py`）里"拼上下文 → 建 prompt → 调模型"这段编排抽成一个**非流式、无 SSE 上下文**的函数，供生产 SSE 与评测 runner 共用。改造量集中在解耦，不在新功能。

---

## 三、R1 非流式生成入口契约（前置，你自建）

建议落 `core`（如 `src/core/pipeline/recall/generation_runtime.py`），SSE 与评测共用：

```python
@dataclass
class GenerationOutput:
    answer: str
    blocks: list[ContextBlock]      # 实际纳入上下文的片段（含 chunk_id + content）
    context_text: str               # 注入 prompt 的编号上下文
    skipped_no_content: int
    truncated: int

async def generate_answer(
    *,
    query: str,
    hits: list[RerankedHit],        # rerank 后最终候选（降级时为 RRF 顺序）
    contents: dict[str, str],       # 已回填正文（与 rerank 共用，不重复查库）
    resolved,                       # 已解析的用户 CHAT 模型
    token_budget: int = settings.RECALL_GENERATION_CONTEXT_TOKEN_BUDGET,
) -> GenerationOutput:
    # 1. assembled = assemble_context(hits, contents, token_budget)
    # 2. 空 blocks → 返回 answer="" + 空 blocks（评测侧据此标"无上下文/弃答"）
    # 3. user_prompt = build_rag_user_prompt(query, assembled.context_text)
    # 4. result = await resolved.provider.generate(prompt=user_prompt,
    #             system_prompt=RAG_GENERATION_SYSTEM_PROMPT)
    # 5. 返回 GenerationOutput(answer=result.text, blocks=assembled.blocks, ...)
```

要点（供你实现时对齐）：

- **与生产同 prompt / 同预算 / 同 system prompt**，保证评测出的生成质量等同线上。
- SSE 侧 `_generate_answer` 理想上重构为：调本函数的"拼装段"，流式部分（`provider.stream` + `answer_delta`）保留在 SSE 专属路径——非流式入口与流式入口共享 `assemble_context` + prompt 构建，仅生成调用不同（`generate` vs `stream`）。
- 空命中 / 全缺正文返回空答案而非抛错，让评测把"弃答"作为一种可度量结果（呼应"绝不返回没答案的成功"这一现有设计）。

---

## 四、模块结构

```
src/evaluation/
├── contracts/judge.py           # ⑱ Judge 协议落实现侧契约（phase0 已定协议）
├── adapters/
│   └── generation_adapter.py    # ⑲ 对接 R1：query+候选+正文 → 答案+上下文 → StageOutput
├── metrics/
│   └── generation.py            # ⑳ RAG Triad + Context Recall + Answer Correctness（RAGAS 惰性）
├── judges/                      # 判官实现（惰性依赖隔离处）
│   ├── ragas_judge.py           #    RAGAS 适配（首版）
│   └── native_judge.py          #    自研判官（后续内化，接 ModelFactory）
└── runners/
    └── pipeline_runner.py       # ㉑ 串联 retrieval→rerank→generation 一轮跑完
```

---

## 五、生成适配器（⑲ `generation_adapter.py`）

实现 `Evaluable(layer=Layer.GENERATION)`：

```python
class GenerationEvaluable:
    layer = Layer.GENERATION
    def __init__(self, token_budget: int): ...
    async def run(self, sample: Sample, *, upstream: StageOutput) -> StageOutput:
        rerank_hits = upstream.raw.hits                       # list[RerankedHit]
        contents = await fetch_chunk_contents(
            [h.chunk_id for h in rerank_hits], sample.user_id) # 可由 run 上下文复用，免重查
        resolved = await aresolve_user_model(
            user_id=sample.user_id, capability="CHAT", allow_system_fallback=False)
        out = await generate_answer(                          # R1 入口
            query=sample.query, hits=rerank_hits,
            contents=contents, resolved=resolved, token_budget=self.token_budget)
        return StageOutput(
            layer=Layer.GENERATION, query=sample.query,
            ranked=upstream.ranked,                           # 沿用 rerank 序（供需要时归因）
            answer=out.answer,
            contexts=[b.content for b in out.blocks],         # 判官据此评 faithfulness/context
            elapsed_ms=upstream.elapsed_ms, raw=out,
        )
```

要点：

- **正文回填可由 run 上下文复用**：rerank 层已回填过同批 chunk 正文，`pipeline_runner` 把 `contents` 按 sample 缓存传下，生成层免重复查库。
- `contexts` 用**实际纳入上下文的 blocks**（经预算截断后），而非全部召回——这才是判官该评的"真正喂给模型的上下文"。
- 空答案（弃答）照常返回，metrics 侧据此度量（弃答率、忠实度对弃答的处理）。

---

## 六、判官（⑱ `contracts/judge.py` + `judges/`）

### 6.1 协议（phase0 §4.4 回顾）

```python
class Judge(Protocol):
    model_name: str
    async def score(self, criterion, *, query, answer, contexts, golden_answer=None) -> JudgeResult
# JudgeResult(score: float, reasoning: str, n_samples: int)
```

### 6.2 首版：`ragas_judge.py`（集成）

- 惰性 import RAGAS（`[eval]` extra），把本项目的 `(query, answer, contexts, golden_answer)` 适配成 RAGAS 入参，调其对应指标的 LLM-as-judge。
- RAGAS 判官 LLM 可配置为独立模型；**须与被测 CHAT、生成器错开**（§八纪律），并记入快照。
- `temperature=0`；关键指标多次采样取均值/多数，`JudgeResult.n_samples` 记采样次数。

### 6.3 后续：`native_judge.py`（内化）

按业务信号把高频指标（如 faithfulness）内化为自研 prompt，接 `ModelFactory` + 项目加密/熔断，去掉 RAGAS 依赖。`Judge` 协议不变，上层零改动——这是先集成后内化路线的落点。

---

## 七、生成与正确性指标（⑳ `metrics/generation.py`）

全部 `async def compute`（phase0 §4.3 统一），经注入的 `Judge` 打分。RAGAS 仅在本文件惰性 import。

### 7.1 第 2 层 · 生成质量（RAG Triad，不需 `golden_answer`）

| 指标 | 衡量 | requires_golden_answer |
| --- | --- | --- |
| **Faithfulness / Groundedness** | 答案每个论断能否被 `contexts` 支持（直接抓幻觉，最高信号） | 否 |
| **Answer Relevancy** | 答案与原始 `query` 的语义贴合度 | 否 |
| **Context Relevance / Precision** | `contexts` 中真正服务于回答的比例 | 否 |

`requires_judge=True`。Faithfulness 是对"绝不返回没答案的成功"现有设计的关键补充——抓"答了但没依据"。

### 7.2 第 3 层 · 端到端正确性（需 `golden_answer`）

| 指标 | 衡量 |
| --- | --- |
| **Context Recall** | 回答所需信息有多少出现在 `contexts`（RAGAS 视其为"检索是否根本正确"的判据） |
| **Answer Correctness / Accuracy** | 答案与 `golden_answer` 的事实一致性 |

`requires_judge=True`、`requires_golden_answer=True`。runner 对缺 `golden_answer` 的样本跳过本层并计数（不报假分）。

### 7.3 聚合与口径

- 复用阶段 1 聚合：逐 type 桶均值 + 桶样本量；判官多采样时记 `n_samples`。
- 报告标注判官模型名、采样次数、RAGAS 版本——判官口径变了数字不可比。

---

## 八、判官的非确定性、成本、校准与防偏置

- **判官校准集（B7，生成层数字可信的前提）**：reference-free 指标的可信度 = 判官的可信度。`temperature=0 + 多采样`只压**采样方差**,压不住**系统性偏差**——RAGAS prompt 的"已校准"是对英文公开集而言,**对中文 + 本场景的校准度未知**。故须留一份**几十条人工标注的判官校准集**,定期测 judge-human 一致率(如 Cohen's κ);**判官换模型 / 换 RAGAS 版本必须重测**(快照已记版本,此处补重测闭环)。一致率过低则该判官的生成层数字不可用。
- **非确定性**：判官 `temperature=0`；多采样降方差。注意 t=0 时多采样几乎退化为单次(采样间无差异),若要真正暴露方差,改用 few-shot 扰动 / prompt 变体,否则 `n_samples>1` 是假精度。
- **成本**：单轮 LLM 调用量 = 生成层样本数 ×（1 次生成 + 各判官指标 × 采样次数）。按黄金集规模预估，避免无意识刷量。
- **防自评偏置（硬纪律）**：生成器 / 判官 / 被测 CHAT 不得同一,判官最好强于被测;`snapshot.validate_model_distinctness` 同名告警。但**只防同名,防不住同源 LLM 偏置**(见 phase1.5 §6.4 B5)——合成集上 Faithfulness 等绝对分偏乐观,仅作相对追踪。

---

## 九、流水线 runner（㉑ `runners/pipeline_runner.py`）

串联三层，一轮跑完，逐层产指标：

```python
async def run_pipeline(dataset, ctx, *, layers: list[Layer]) -> EvalResult:
    for sample in dataset:
        out_recall = await recall_evaluable.run(sample)
        if Layer.RERANK in layers or Layer.GENERATION in layers:
            out_rerank = await rerank_evaluable.run(sample, upstream=out_recall)
        if Layer.GENERATION in layers or Layer.CORRECTNESS in layers:
            out_gen = await generation_evaluable.run(sample, upstream=out_rerank)
        # 各层 metrics: for m in metrics_for(layer): await m.compute(sample, out_*, judge=judge)
    # 聚合 → EvalResult（含各层 MetricResult）
```

要点：

- **一次召回/重排喂多层**：检索、重排、生成共享同一次上游执行，避免重复跑链路、口径漂移。
- **contents 复用**：rerank 回填的正文经 ctx 传给生成层，免重查（§五）。
- **层选择**：`--layers retrieval,rerank,gen,correctness` 控制跑哪些；correctness 自动要求 `golden_answer`。
- 判官实例由 ctx 注入；生成/正确性层 metric 经 `judge=` 形参拿到。

---

## 十、运行前置（生成层专属）

- **R1 非流式入口就绪**（你提前完成）——本层全部依赖它。
- **冻结租户 CHAT 模型可用**：`aresolve_user_model(capability="CHAT", allow_system_fallback=False)`，未配置抛错。
- **黄金集含 `golden_answer`**（阶段 1.5 产出）——正确性层依赖。
- **判官可用 + 三模型错开**；RAGAS 装在 `[eval]` extra。
- 活栈 + 多次 LLM 调用，属 acceptance 级，手动/定时跑，绝不挂 PR 门禁。

---

## 十一、报告增量

- RAG Triad + Context Recall + Answer Correctness 的逐桶均值（标 n、判官采样次数）。
- 弃答率（空答案样本占比）单列。
- 回归判据扩展：`Faithfulness` 跌幅 > 0.05 判回归（technical_design 示例，入配置可调）。
- 基线对比按 config 同口径分组，config 维度新增 chat/judge/generator 模型名（已在 Snapshot / 台账 schema 预留）。

---

## 十二、完成判据（Definition of Done）

1. 对接 R1 非流式入口，`generation_adapter` 产出 `answer` + 实际 `contexts` 的 `StageOutput`。
2. `Judge` 协议下 `ragas_judge` 可跑通 RAG Triad + Context Recall + Answer Correctness；RAGAS 惰性导入、仅在 `[eval]` extra。
3. 缺 `golden_answer` 样本在正确性层被跳过并计数，不报假分。
4. 三模型错配校验生效并记快照；判官 `temperature=0` + 多采样记 `n_samples`。
5. `pipeline_runner` 一次上游执行喂多层，contents 复用、口径不漂移。
6. 报告含弃答率、判官口径标注；回归判据按 config 同口径分组。

---

## 十三、本阶段不做（划清边界）

- 不在评测里实现非流式生成本身（R1 属 `core`，你自建）。
- 首版不强求内化判官（`native_judge` 后续按业务信号再做）；先 RAGAS 见数。
- 开源数据集是检索/重排主力；生成正确性可选用 CMRC2018（抽取式短答案，仅弱信号），但**不把开源 answer-correctness 当权威**——生成层最高信号 Faithfulness 为 reference-free，优先靠它 + Track B 埋点真值。
- 不挂 PR 门禁（依赖活栈 + 判官 + 多次 LLM 调用）。
