# 阶段 1.5 · 黄金集合成器 — 设计文档

> **归档文档：仅供追溯，不是当前权威依据。** 替代关系见 [归档说明](../README.md)。

> 状态：设计稿（`.specs/rag-quality-eval/`，git-ignored）
> 上游：[framework_design.md](framework_design.md)（总架构）、[phase1_design.md](phase1_design.md)（黄金集 schema/loader）、[technical_design.md](technical_design.md) §四（黄金集来源与三条纪律）
> 范围：黄金集来源设计——**以开源中文数据集为主、自有 chunk 反向合成为辅**，全程**无人工抽检**，产出符合阶段 1 `GoldenSample` schema 的评测条目。
> 定位：阶段 3（生成/正确性层）的 `golden_answer` 来源；与阶段 1 检索层并行即可起步。
>
> ⚠️ **存储口径已更新（权威见 [eval_storage_design.md](eval_storage_design.md)）**：本文凡"灌进评测租户 /
> 走真实 ingestion pipeline / 从 `kb_document_chunk` 采样 / 反向合成读 `ChunkRepository`"，一律改为：
> 经 **EvalIngestor（复用 core 组件、不走 `ParseTaskPipeline`）灌进评测自持 `eval_corpus_chunk`**，
> 采样/回定位目标为 **`eval_corpus_chunk`**；黄金集落 `eval_query` + `eval_qrel`（非 `eval_golden_sample`）；
> `user_id` 为路由常量 `EVAL_USER_ID`、非租户。分块/索引仍用与生产同一组件（口径不变）。

---

## 一、结论先行

人工抽检成本过高、不可持续。本设计改为**无人工**方案，靠三件事保住数据可信：**开源标注数据集作主力、自动质量门禁替代人工审核、以"相对比较"而非"绝对权威"定位评测**。四条决策：

1. **降低标尺要求：稳定的比较尺 > 完美的绝对尺。** 本模块头号用例是"换 provider / 调 top_k 后有没有退化"——这是相对比较。只要测试集噪声在不同配置间**恒定**，即使有噪声也能正确判断退化方向。这一步去掉了"必须人工校准绝对分数"的前提。
2. **主力用开源中文数据集，doc 粒度评测（零人工）。** 把开源检索数据集的文档灌进评测租户（走真实 pipeline），用其自带 `query→相关文档` 标注，落到 schema 的 `expected_doc_ids`（doc 粒度兜底）。选型见 §九。
3. **辅以自有 chunk 反向合成 + 自动质量门禁（零人工）。** 仍保留反向合成以拿 chunk 粒度的自有语料评测，但把"人工抽检"换成**自动多信号过滤**（异模型可答性 + 召回回环一致性 + 答案自洽）。
4. **生成层最高信号本就无需标注。** Faithfulness / Answer Relevancy / Context Relevance 是 reference-free 的，零标注成本；仅 Answer Correctness / Context Recall 需 `golden_answer`，用合成的（带噪）做相对追踪或降优先级。

依赖方向：合成器只读 chunk 仓储 `src/core/storage/chunks`（`ChunkRepository` → 表 `kb_document_chunk`，只读查询、不新增 ORM）、调 `src.core.llm`；开源数据集经真实 ingestion 灌入评测租户；产出写 `.specs`/MinIO。属 `evaluation → core` 正常依赖。

---

## 二、评测语料构建（前置地基，先于合成）

**核心认知：评测语料是主动构建的，不是被动复用生产现状。** `kb_document_chunk` 当前数据稀疏不足以覆盖测试——这不是阻塞，而是说明评测租户需要**专门灌一批有代表性的文档**。冻结评测语料/租户（R2）是受控隔离环境，数据少就走真实 ingestion pipeline 灌进去：文档经与生产**完全一致**的 解析→分块→索引 路径，产出的 chunk 即库内真实 chunk，`chunk_id` 真实可命中，既解决覆盖又不破坏"黄金集长在自有语料"原则。

### 2.1 灌库策略

- **同一条 pipeline**：经生产 ingestion 入库（同 parser provider、同分块策略），保证 chunk 形态与线上一致。
- **绑定 ingestion 快照**：语料一次性灌定后冻结、只读；黄金集与该次 ingestion 绑定，语料重灌/换分块策略则 `expected_chunk_ids` 需重校验（阶段 1 `loader.precheck`）。
- **预置模型配置**：评测租户须配可用 EMBEDDING / CHAT / RERANK 模型（阶段 1/2/3 分别需要）。

### 2.2 覆盖维度清单（灌什么）

按"评测要回答的问题"反推要覆盖的维度，宁可窄而全，不要宽而稀：

| 维度 | 覆盖项 | 为什么 |
| --- | --- | --- |
| 文档类型 | PDF / Word / HTML / Markdown | parser 多 provider，不同类型数据清洗质量不同 |
| 文档结构 | 长文 / 短文 / 表格密集 / 图文混排 / 多级标题 | 压测分块边界与正文回填 |
| 领域 | 你的产品文档 + 目标业务领域文档 | 贴近真实召回分布 |
| 来源 | 自有文档 + 公开领域文档（中文维基子集、行业 PDF） | 补量且可控 |

> 区分：开源数据集的**文档**可灌进来当语料（会变成库内真实 chunk）；其**问答对**不可直接当黄金集（标准 chunk 不在本库）。

### 2.3 规模与分层

- **中等规模即够**：几百篇文档 → 数千 chunk，足以支撑丰富黄金集；不必追求海量。
- **覆盖靠分层不靠堆量**：采样按 `dataset` / `chunk_type` / 文档长度分层（见 §6.1 sampler），保证每种条件都有样本。
- 与黄金集量级匹配：首版黄金集 50–100 条，对应语料只需覆盖到这些条目能分层抽到各类型即可，可滚动扩。

### 2.4 语料来源（LinkRag 是通用多领域 RAG，无固定垂直领域）

项目定位是通用 RAG 系统、无固定客户语料，故评测语料按"零人工 + 通用"组织，两条来源互补：

- **来源一·开源通用文档（主力，见 §九）**：DuReader_retrieval / T2Ranking 的段落灌入评测租户，doc 粒度评检索/重排。通用 RAG 的预期分布即通用语料，**不存在领域错配**，故**不取 Multi-CPR / C-MTEB 领域子集**。
- **来源二·LLM 合成文档（补全链路）**：用 LLM 生成**真实格式**文档（带表格/多级标题/图文的 PDF/Word/HTML/Markdown），走真实 ingestion，**覆盖开源纯文本绕过的 parser + chunker**。对通用 RAG，合成内容的事实性不影响检索评测（只看 chunk 是否命中）。

> 合成文档的纪律：语料模型 / 问题生成模型 / 门禁复核模型 / 判官两两错开（防双重合成偏置）；数字按"相对比较"用，不作绝对权威。

### 2.5 两步走

1. **现在**：建评测租户 → 灌开源通用文档（Track A）+ 一批 LLM 合成真实格式文档（Track B）→ 反向合成 + 自动门禁出首版黄金集，全程无人工。
2. **以后**：若未来有真实生产文档可用（脱敏），再作为最高保真来源补入；线上 query 日志作种子滚动扩。

---

## 三、被依赖的生产接缝

| 用途 | 入口 | 说明 |
| --- | --- | --- |
| 按 id 取 chunk 正文 | `ChunkRepository.get_by_chunk_ids(db, chunk_ids)` → `list[ChunkRecordDB]` | 已有 |
| 采样 ACTIVE chunk | 只读查询 `ChunkRecordDB`（表 `kb_document_chunk`） | 按 `user_id`/`set_id`/`lifecycle_status=ACTIVE` 过滤；有 `idx_user_set` 索引。**只读、不新增模型**，可在 `src/core/storage/chunks` 加只读查询或合成器内直接 select |
| LLM 生成 | `ModelFactory.create_client(...)` → `ITextGenerator.generate(...)` → `GenerateResult` | 复用加密/熔断；生成器模型与判官/被测模型须错开 |

`ChunkRecordDB` 关键字段：`chunk_id` / `doc_id` / `set_id` / `user_id` / `content` / `content_hash` / `lifecycle_status` / `chunk_type` / `start_line` / `end_line` / `chunk_index`。

---

## 四、模块结构

```
src/evaluation/golden/
├── opensource/                 # 主力：开源数据集 → GoldenSample（doc 粒度）
│   ├── ingest.py               #   把数据集文档经真实 pipeline 灌入评测租户
│   └── convert.py              #   query→相关段落标注 转 GoldenSample（expected_doc_ids）
└── gen/                        # 辅路：自有 chunk 反向合成
    ├── __init__.py
    ├── sampler.py              #   从 kb_document_chunk 采样 chunk（按 dataset/类型分层）
    ├── prompts.py              #   各问题类型的生成 prompt（中文自研）
    ├── generator.py            #   调 ModelFactory：chunk(s) → (query, golden_answer, type)
    └── gate.py                 #   自动质量门禁（异模型可答性 + 召回回环 + 答案自洽），无人工
```

产出：`.specs/rag-quality-eval/golden/<dataset>.jsonl`（或经 §八 落 MinIO），每行一个 `GoldenSample`（schema 见 phase1 §3.1）。

---

## 五、核心循环

```
sampler 取一个（或几个相关）chunk
    → generator 据 chunk 内容调 LLM 生成「该 chunk 可回答的问题」+ 标准答案
    → 源 chunk_id 即 expected_chunk_ids、生成答案即 golden_answer
    → 标注问题类型（keyword / paraphrase / longtail / cross_doc）
    → gate 自动门禁（异模型可答性 + 召回回环一致性 + 答案自洽）→ 通过/丢弃/难例桶
    → 写入 <dataset>.jsonl（全程无人工）
```

> 注：开源数据集路径（§九，主力）不走"合成"循环，而是 ingest 文档 + 转换其 `query→相关段落`标注为 `GoldenSample`（`expected_doc_ids`），直接入库。本循环是辅路（自有 chunk 反向合成）。

多跳/跨文档（`cross_doc`）问题由 sampler 自行组织候选 chunk 组合，借问题类型 taxonomy 与 prompt 思路，但**不引入知识图谱与 node→chunk_id 映射的对齐麻烦**（与 technical_design §四 一致）。

---

## 六、各模块设计

### 5.1 `sampler.py` — 采样

```python
@dataclass
class SampleSpec:
    user_id: int                 # 冻结评测语料/租户（R2）
    dataset_ids: list[int]
    n: int                       # 目标条数
    type_mix: dict[QuestionType, float]   # 各类型配比
    multi_chunk_size: int = 2    # cross_doc 时一组取几个

class ChunkSampler:
    async def sample_single(self, spec) -> list[ChunkRecordDB]: ...     # 单 chunk → 单跳问题
    async def sample_groups(self, spec) -> list[list[ChunkRecordDB]]: ...# 相关 chunk 组 → 多跳/跨文档
```

要点：

- **只在冻结语料范围采样**（固定 `user_id` + `dataset_ids`），`lifecycle_status=ACTIVE`，与生产数据隔离（R2）。
- **分层**：按 `dataset` / `chunk_type` / 文档分层抽样，避免集中在少数长文档，保证覆盖面。
- **相关组的组织**（cross_doc）：同 `doc_id` 相邻 `chunk_index`，或同 `set_id` 下经一次召回取 top 近邻作"相关候选"，再让 LLM 判定是否真能合成一个跨片段问题（不强造）。
- 过滤过短/模板化/无信息量 chunk（按 `content` 长度与启发式），降低"答不出"噪声。

### 5.2 `prompts.py` — 生成 prompt

按问题类型分 prompt，中文自研，taxonomy 参考 RAGAS/DeepEval 但 prompt 自写：

| type | 含义 | prompt 要旨 |
| --- | --- | --- |
| `keyword` | 关键词直问 | 据 chunk 事实出一个用词贴近原文的问题 |
| `paraphrase` | 改写 | 同一事实换一种问法，措辞与原文拉开 |
| `longtail` | 长尾/细节 | 针对 chunk 中具体数字/条件/边界的细问 |
| `cross_doc` | 跨片段/多跳 | 需综合给定多个 chunk 才能回答，禁止单 chunk 可答 |

每个 prompt 强约束输出结构（JSON：`query` / `golden_answer` / `answerable` / `used_chunk_ids` / `reason`），并要求模型**自报是否真能由给定 chunk 回答**（`answerable=false` 直接丢弃），从源头压低噪声。

### 5.3 `generator.py` — 调 LLM 产条目

```python
class GoldenGenerator:
    def __init__(self, client: ITextGenerator, generator_model: str): ...
    async def generate_one(self, chunks: list[ChunkRecordDB], type_: QuestionType) -> GoldenSample | None:
        # 1. 取 chunks 正文 + 选 prompts[type] 构造请求
        # 2. client.generate(...) → 解析 JSON
        # 3. answerable=false 或解析失败 → 返回 None（计入丢弃）
        # 4. expected_chunk_ids = [c.chunk_id for c in chunks]；golden_answer = 输出
        # 5. 组装 GoldenSample（user_id/dataset_ids 取自 chunks，type/note 标注）
```

要点：复用 `ModelFactory.create_client` 拿 `ITextGenerator`，走项目加密/熔断；`temperature` 适度（生成多样性，区别于判官的 0）；失败/不可答静默丢弃并计数，不污染产出。

### 5.4 `gate.py` — 自动质量门禁（替代人工抽检）

合成数据必有噪声（问题答不出、标错 chunk、答案幻觉）。**人工抽检成本过高，改为全自动多信号门禁**——三个信号都是机器可跑、无需人介入：

```python
class AutoQualityGate:
    async def screen(self, samples: list[GoldenSample]) -> GateReport:
        # 对每条跑三信号 → 通过/丢弃/标"难例桶"，返回统计
```

- **信号一·异模型可答性**：用一个**与生成器不同、最好更强**的模型，只喂 `expected_chunk_ids` 正文，让它答这个问题。答不出 → 自动丢（catches "chunk 其实答不出的问题"）。
- **信号二·第三方检索回环（B2 防循环论证）**：把生成的 `query` 走**一个与被测系统无关的独立检索器**（如纯 BM25 / 一个固定的开源 embedding，**不是阶段 1 的 `recall_adapter`**），看 `expected_chunk_ids` 是否落 top-N。
  - **为什么不用被测召回**：用待评测的召回链路去筛黄金集是**循环论证**——会把"现有配置召不回但其实是好题"的样本踢掉，使黄金集偏向当前 baseline，后续换 provider 评测时对新 provider 不公平。
  - 命不中 → 进**难例桶**,且必须有去向:跨配置对比时**显式排除难例桶或单列**,不静默混入。
- **信号三·答案自洽**：比较"生成器的答案"与"信号一里异模型据 chunk 给的答案"，语义分歧大 → 自动丢（catches 幻觉/不准）。

通过全部硬信号的条目直接入库，无人工环节。门禁可调严格度，通过率/丢弃率/难例占比写入 `GateReport`。

> **残留噪声与"相对比较"的诚实边界（B1）**：相对比较能消化噪声的前提是"噪声在各配置间恒定"——此假设在换 provider 时**减弱**(脏样本命中依赖召回模型本身)。故:(1) 该假设须在 M1 经**噪声地板验证**(见 trend_dashboard §5.0)后才作数;(2) 自动门禁是**降低**噪声而非消除;(3) 跨 provider 结论降级为"提示性"。
>
> **同源偏置(B5)**：合成语料 + 合成问题 + 合成判官,即便模型两两错开(只防同名),都是 LLM 仍有**同源偏置**,会系统性高估生成层指标。声明:模型错开降低但不消除;生成层绝对分偏乐观、仅作相对追踪;正确性优先用 Track B 埋点真值而非判官;真实 query 日志冷启动是对抗合成分布偏移的主要手段。

---

## 七、三条不可省的纪律（贯穿流程，已无人工化）

来自 technical_design §四，落到本设计的具体位置（纪律一已从"人工"改为"自动"）：

1. **质量门禁（自动，替代人工评审）** → `gate.py` 的三信号过滤（§6.4）。残留噪声靠相对比较消化；通过率/难例占比作为黄金集可信度凭据。
2. **真实查询冷启动** → sampler 支持以 **recall stream 线上 query 日志**挑真实用户问题作 query 种子（比纯合成更贴业务分布），再用 LLM 补 `golden_answer` 并标注命中 chunk。设计上 sampler 增一条"种子来源 = 日志"的输入路径，与"纯合成"并行。
3. **模型错配（防自评偏置）** → **生成器 / 门禁复核 / 判官 / 被测 CHAT 模型尽量两两错开**，同模型自产自评/自筛会系统性高估。约束：门禁复核模型与判官应不同于、最好强于被测；生成器也尽量错开。`snapshot.py` 显式校验（同名即告警/拒绝）并记入快照（呼应 phase0 `Snapshot.validate_model_distinctness`）。

---

## 八、产出与存储

- 格式：`GoldenSample` jsonl，逐行一对象，字段含 `note`（构造说明 / 为何这样判命中），便于人工复核与归因。
- 落点：开发期 `.specs/rag-quality-eval/golden/<dataset>.jsonl`；正式留存可入 MinIO eval 桶 `runs/`同级的 `golden/<dataset>.jsonl`（参 minio_eval_bucket_design）。
- 与冻结语料绑定：黄金集与该 corpus 某次 ingestion 快照绑定；语料重灌/换分块策略后需重校验 `expected_chunk_ids`（阶段 1 `loader.precheck` 负责）。

---

## 九、开源数据集选型（主力来源，零人工）

> 用法转变：开源数据集**从旁路升为主力**。把其文档灌进评测租户走真实 pipeline，用其 `query→相关文档/段落` 标注落到 `expected_doc_ids`，在 **doc 粒度**评测——损失 chunk 级精度，换零人工 + 大覆盖 + 真实 query 分布。

### 9.1 候选评估与选定（授权已核实，2026-06）

| 数据集 | 规模 / 特点 | 授权 | 适配评测层 | 选定 |
| --- | --- | --- | --- | --- |
| **DuReader_retrieval** | ~9.7 万真实百度搜索 query / 8.9M 段落；人工标注 dev/test；二值相关 | **Apache-2.0**（宽松） | 检索层 recall（真实 query 分布最贴业务） | ✅ 检索主力 |
| **T2Ranking** | ~30 万 Sogou query / 2M 段落；**4 级分级相关** | **Apache-2.0**（宽松） | 重排层 ordering（分级相关→**分级 NDCG**，补足二值口径短板）；模型选型 | ✅ 重排主力 |
| **C-MTEB**（检索/重排任务族） | 聚合 35 个数据集（含 T2Retrieval/DuRetrieval/MMarco 等） | **逐数据集不一**（需逐个核） | embedding/rerank 模型横评（对齐公开 leaderboard） | ⚠️ 仅模型选型，按需 |
| **CMRC2018** | ~1.9 万问题；维基段落；抽取式 (question, answer, passage) | **CC BY-SA 4.0**（署名 + 相同方式共享） | 生成正确性（带 `golden_answer`） | ◯ 可选·生成正确性 |

### 9.2 选型结论

- **检索层 → DuReader_retrieval**：真实搜索 query 分布最接近业务，Apache-2.0 可放心用；二值相关对应阶段 1 的二值 NDCG 口径。
- **重排层 → T2Ranking（有重要限制，见 §9.3 粒度）**：4 级分级相关可跑**分级 NDCG**。但开源是 **doc 粒度**标注,经 chunker 切分后**抹平 chunk 级排序**,而重排的全部价值在 chunk 级 ordering——故 T2Ranking 对重排只给**近似/doc 粒度**结论;**重排 NDCG 的可信来源是 Track B(chunk 级埋点真值)**,T2Ranking 作辅证与模型选型。Apache-2.0。
- **模型选型 → C-MTEB**：回答"换 bge embedding/rerank 模型值不值",对齐公开榜单。**注意逐数据集授权**，落地前核每个子集 license。
- **生成正确性（可选）→ CMRC2018**：自带 (问题, 答案, 段落),省去合成 `golden_answer`。**授权 CC BY-SA 4.0**：内部评测使用无碍，但**派生黄金集若对外分发须署名 + 相同方式共享**,需合规留意;抽取式短答案对生成式 RAG 的 answer-correctness 仅作弱信号。
- **不取领域子集（Multi-CPR / C-MTEB Ecom·Medical·Video 等）**：LinkRag 为通用多领域 RAG、无固定垂直，通用集已贴合；领域子集仅在未来明确某垂直时再按需引入。

### 9.3 落地注意

- **粒度对齐（B8）**：开源标注是 query→段落。**以段落为 ingestion 单元**(段落→一个 doc_id),经 chunker 切分后用 `expected_doc_ids` 在 **doc 粒度**评测。明确分工:**doc 粒度集只用于检索层(召回是否漏),不用于重排 ordering 的精细结论**;重排 chunk 级 ordering 看 Track B。段落→doc_id 映射须校验一一对应(去重/合并/超长跨 doc 会破坏映射)。
- **两套口径分开汇报**：开源数据集评的是"模型/pipeline 在通用语料上的能力";自有语料(反向合成)评的是"本 pipeline 在本数据上的表现"。分开存放、分开汇报，不互相替代(technical_design §四)。
- **授权合规**：Apache-2.0(DuReader/T2Ranking)宽松;CC BY-SA 4.0(CMRC2018)有署名+相同方式共享义务;C-MTEB 逐子集核。仅内部评测用途风险低,对外分发派生数据须按各自 license 处理。

---

## 十、完成判据（Definition of Done）

1. **主力路（开源）**：`golden/opensource/` 能 ingest DuReader_retrieval（检索）与 T2Ranking（重排）文档入评测租户，并把其标注转成 `GoldenSample`（doc 粒度 `expected_doc_ids`），零人工。
2. **辅路（合成）**：`golden/gen/` 能采样 → 生成 → **自动门禁** → 写 `<dataset>.jsonl`，全程无人工。
3. **自动门禁生效**：三信号（异模型可答性 / 召回回环一致性 / 答案自洽）可跑，`GateReport` 输出通过率/丢弃率/难例占比。
4. 模型错配校验生效（生成器/门禁复核/判官/被测 同名即告警），记入快照。
5. T2Ranking 分级相关可落 **分级 NDCG**（重排层），开源与自有两套口径分开汇报。
6. 授权合规已核（Apache-2.0 / CC BY-SA 4.0 / C-MTEB 逐子集），对外分发按 license 处理。
7. 支持真实 query 日志作种子的冷启动路径。

---

## 十一、本阶段不做（划清边界）

- 不引入知识图谱 / node→chunk_id 对齐（cross_doc 用 chunk 组合近似）。
- 不做生成/正确性指标计算（judge/RAGAS）——阶段 3。
- **不做人工抽检**——改自动门禁 + 相对比较消化残留噪声。
- 不追求一次性大批量；先开源 doc 粒度跑通，再补合成 chunk 粒度。
