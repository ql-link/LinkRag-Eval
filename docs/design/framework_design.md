# RAG 评估框架 — 架构设计与模块拆分

> 状态：设计稿（`.specs/rag-quality-eval/`，git-ignored 临时交付物）
> 范围：从零设计一套**评估框架**（engine），承载对 toLink-Rag 全链路的质量评估。
> 约束：本设计**只参考已实现的生产模块**（recall / rerank / generation / llm / chunk repository），不沿用任何历史评估代码。
> 落点：框架代码归于 `src/evaluation/`（顶层独立包，与 `api` / `services` 同级，强调它是离线驱动器、不属生产 `core`）。
> 沉淀：稳定的契约/口径最终回流 `docs/internals/rag_eval.md`。
>
> ⚠️ **存储口径已更新（权威见 [eval_storage_design.md](eval_storage_design.md)）**：评测语料/chunk 进评测自持
> **`eval_corpus_chunk`（EvalBase）+ ES/Qdrant 评测 namespace**，**不入生产 `kb_document_chunk`**；黄金集落
> `eval_query`+`eval_qrel`；灌库经 EvalIngestor（复用 core 组件、**不走 `ParseTaskPipeline`**）；`user_id`
> 为路由常量。多租户隔离负样本检查（B10）仍适用于评测 namespace 内。

---

## 一、结论先行

把"质量检测"建成一套**分层的评估框架**，而不是一堆零散脚本。框架按职责切成两组模块：

- **横切骨架（framework backbone）**：契约、数据模型、数据集、适配器、运行器、报告、产物、观测。这组与"评什么环节"无关，是可复用的地基。
- **纵向环节（per-stage metrics + adapters）**：数据清洗、召回、重排、生成、端到端正确性（共 5 个评测点），每个环节挂自己的指标实现与一个把生产/解析模块包成"可评测对象"的适配器。

三条硬约束贯穿全设计：

1. **依赖单向 `evaluation → core`。** 框架反向调用生产模块来跑评测；生产请求路径（`api` / `mq` / `pipeline` 请求段）**绝不** import `evaluation`。建议 CI 加一条 import-lint 守方向。
2. **适配器是唯一接缝。** 框架对生产代码的所有调用都收敛到 `adapters/`，其余模块只依赖框架自己的抽象（`contracts/`）。生产模块签名变更时，改一处适配器即可。
3. **指标数学纯函数化。** 检索/重排层指标不碰外部依赖，可单测、可进 PR 门禁；需要活栈（MySQL/Qdrant/ES/LLM）的"整轮 run"只手动或定时触发。

---

## 二、被评测的生产接缝（设计依据）

框架的适配器层据下列**已实现**的真实接口编写。这些是设计的事实基础，不可臆测。

| 环节 | 生产入口 | 关键签名 / 返回 |
| --- | --- | --- |
| 召回（分路·dense） | `VectorStorageFacade.search_dense_chunks` | `(*, query, user_id, set_id, doc_id=None, top_k=None, score_threshold=None) -> VectorSearchResult` |
| 召回（分路·sparse） | `VectorStorageFacade.search_sparse_chunks` | 同上签名 → `VectorSearchResult` |
| 召回（分路·bm25） | `Bm25Retriever.recall` | `(query, dataset_ids, doc_ids=None, *, user_id, top_k) -> list[RetrieverHit]` |
| 召回（融合） | `RecallPipeline.execute` / `fuse_with_rrf` | `execute(RecallRequest) -> RecallResponse`；`RecallRequest(query, user_id, dataset_ids, doc_ids=None, top_k=20)`；`RecallResponse(query, hits: list[RecallHit], per_source_counts, failed_sources, elapsed_ms)` |
| 重排 | `PostRecallReranker.rerank` | `rerank(RerankRequest) -> RerankResponse`；`RerankResponse(query, hits: list[RerankedHit], rerank_applied, elapsed_ms)`；内部 `_degrade` 提供 `degrade_to_rrf_order` 顺序 |
| 上下文拼装 | `recall.generation.assemble_context` / `fetch_chunk_contents` | `assemble_context(hits, contents, token_budget, tokenizer=None) -> AssembledContext` |
| 生成 | `application/recall_stream_runtime._generate_answer` → `provider.stream(...)` | **目前只有流式入口**，绑 SSE / 用户模型解析；非流式入口缺失（见 §六风险 R1） |
| LLM 客户端 | `ModelFactory.create_client(...)` / `aresolve_user_model` | 复用项目自身 provider + 加密 + 熔断；判官/生成器走同一工厂 |
| 黄金集语料源 | `ChunkRepository`（`ChunkRecordDB.content`） | 按 `chunk_id` 取真实正文，供合成器反向生成 |

数据契约取项目现成的 `RecallHit` / `RerankedHit`（含 `chunk_id` / `doc_id` / `dataset_id` / `fused_score` / `scores` / `rerank_score` / `rerank_rank`），评估侧不另造重复模型。

---

## 三、框架分层与目录结构

```
src/evaluation/                       # 顶层独立包：评估框架（离线驱动器，单向依赖 core）
├── __init__.py
│
├── contracts/                        # ① 抽象层（端口）：框架内部唯一的依赖目标
│   ├── metric.py                     #   Metric 协议：name / layer / compute(sample, run_output) -> MetricValue
│   ├── evaluable.py                  #   Evaluable 协议：被评测环节的统一调用面（run(sample) -> StageOutput）
│   ├── judge.py                      #   Judge 协议：LLM-as-judge 抽象（score(prompt, ...) -> JudgeResult）
│   ├── dataset.py                    #   Dataset / Sample 协议
│   └── store.py                      #   ResultStore 协议：产物读写（落地实现见 storage/）
│
├── models.py                         # ② 数据模型：EvalRequest / EvalResult / 各层 MetricResult / Snapshot（dataclass）
│
├── golden/                           # ③ 评测集（黄金集）— 详见 phase1.5 / Track B
│   ├── schema.py                     #   GoldenSample dataclass（见 §四）+ jsonl 加载/校验
│   ├── loader.py                     #   读黄金集，做存在性/有效性前置自检
│   ├── cleaning_dataset/             #   数据清洗质检·阶段一：md→渲染各格式存 MinIO + 对应关系表（详见 phase0_5）
│   │   ├── render.py                 #     标准 md → DOCX/PDF/HTML（复用 Track B render）
│   │   ├── store.py                  #     渲染件存 MinIO（tolink-rag-eval/cleaning_corpus/）
│   │   └── registry.py               #     写 eval_cleaning_doc / eval_cleaning_rendered 表
│   ├── opensource/                   #   主力：开源数据集 → GoldenSample（doc 粒度，DuReader/T2Ranking）
│   │   ├── ingest.py                 #     数据集文档经真实 ingestion 入评测租户
│   │   └── convert.py                #     query→相关段落标注 转 GoldenSample（expected_doc_ids）
│   ├── synth/                        #   Track B：LLM 合成真实格式文档 + 埋点回定位（chunk 粒度）
│   └── gen/                          #   辅路：自有 chunk 反向合成
│       ├── sampler.py                #     从 ChunkRepository 采样 chunk（按 dataset/类型分层）
│       ├── generator.py             #     调 ModelFactory：chunk → (query, golden_answer, type)
│       ├── prompts.py               #     各问题类型生成 prompt（中文自研）
│       └── gate.py                  #     自动质量门禁（异模型可答性 + 第三方检索回环 + 答案自洽），无人工
│
├── adapters/                         # ④ 适配器：把生产模块包成 Evaluable（唯一接缝）
│   ├── cleaning_adapter.py           #   数据清洗·阶段二：照表取冻结渲染件 → parser.parse → produced_md
│   ├── recall_adapter.py             #   分路(facade/Bm25Retriever) + 融合(RecallPipeline.execute)
│   ├── rerank_adapter.py             #   PostRecallReranker.rerank（同 run 内并产 degrade_to_rrf_order 对照）
│   └── generation_adapter.py         #   非流式生成入口（依赖 R1 改造）+ assemble_context
│
├── metrics/                          # ⑤ 指标实现：按环节分子模块 + 注册表
│   ├── registry.py                   #   指标注册/发现（按 layer 取用）
│   ├── cleaning.py                   #   数据清洗层（自研·纯函数）：produced_md vs 参考 md（文本/标题/表格/图片/清洗时间）
│   ├── retrieval.py                  #   第1层（自研·纯函数）：recall@k / precision@k / mrr / ndcg / map / 三路重叠率 / 延迟
│   ├── rerank.py                     #   第2层（自研·纯函数）：rerank vs RRF 顺序的 ndcg/mrr 增益
│   └── generation.py                 #   第3层（LLM-as-judge）：RAG Triad + Context Recall + Answer Correctness（judge 抽象，惰性依赖）
│
├── runners/                          # ⑥ 运行器：编排 dataset × evaluable × metrics
│   ├── context.py                    #   一次 run 的上下文：配置快照 / run-id / 资源句柄
│   ├── stage_runner.py               #   单环节驱动：对每个 sample 跑 evaluable → 收集 metrics
│   └── pipeline_runner.py            #   多环节串联（retrieval→rerank→generation）一轮跑完
│
├── snapshot.py                       # ⑦ 配置快照：抓检索层(provider/top_k/threshold/enabled_sources) + 生成层(CHAT/judge/生成器模型名、token 预算、rerank top_n、prompt 版本)；含三模型错配校验
│
├── reporters/                        # ⑧ 报告：结果表 + 基线 diff + 回归判据
│   ├── base.py
│   ├── html_reporter.py              #   HTML 报告（templates/eval_report_template.html）→ reports/<run-id>.html
│   └── json_reporter.py              #   机器可读结果（供后续趋势/门禁）
│
├── storage/                          # ⑨ 产物落地：ResultStore 实现
│   └── filesystem.py                 #   写 .specs/rag-quality-eval/{snapshots,reports}
│
└── hooks/                            # ⑩ 观测：进度 / 日志（不影响指标）
    └── logging_hook.py

tests/unit/evaluation/                # 指标数学单测（确定性强、进 PR 门禁）
scripts/eval/run.py                   # 薄 CLI：仅解析参数 → 调 src/evaluation，无业务逻辑

.specs/rag-quality-eval/              # 产物（git-ignored，数据非代码）
├── framework_design.md               # 本文
├── technical_design.md               # 五层评估点口径与黄金集设计
├── golden/<dataset>.jsonl            # 黄金集
├── snapshots/<run-id>.yaml           # 本轮配置快照
└── reports/<run-id>.html             # HTML 报告：结果表 + 基线 diff + 回归告警
```

---

## 四、模块职责一览

| # | 模块 | 职责 | 依赖 | 是否碰活栈 |
| --- | --- | --- | --- | --- |
| ① | `contracts/` | 定义框架内部所有端口（Metric/Evaluable/Judge/Dataset/Store）。其余模块只依赖它，不互相直连 | 无（纯抽象） | 否 |
| ② | `models.py` | EvalRequest/EvalResult/MetricResult/Snapshot 等贫数据结构 | contracts | 否 |
| ③ | `golden/` | 黄金集 schema、加载校验、自研合成器（反向从 chunk 生成 query+答案） | `ChunkRepository` / `ModelFactory` | 合成器是（取 chunk + LLM） |
| ④ | `adapters/` | 把生产模块封成统一 `Evaluable`；收敛对 core 的全部调用 | recall/rerank/generation/llm | 是 |
| ⑤ | `metrics/` | 各层指标实现 + 注册表；检索/重排层纯函数，生成层经 Judge 抽象 | contracts（+ 生成层惰性判官依赖） | 检索/重排否；生成是 |
| ⑥ | `runners/` | 编排 dataset × evaluable × metrics，产出 EvalResult | contracts/adapters/metrics/golden | 取决于所跑环节 |
| ⑦ | `snapshot.py` | 抓配置快照 + 三模型（生成器/判官/被测）错配校验 | config / models | 否 |
| ⑧ | `reporters/` | 结果表、基线 diff、回归判据渲染 | models/store | 否 |
| ⑨ | `storage/` | ResultStore 落地到 .specs | contracts | 否（本地 IO） |
| ⑩ | `hooks/` | 进度/日志观测 | contracts | 否 |
| C1 | `golden/cleaning_dataset/` | 数据清洗·阶段一：md→各格式渲染存 MinIO + 记对应关系表 | `src/core/parser` 出口 / MinIO | 否（数据工程） |
| C2 | `adapters/cleaning_adapter.py` | 数据清洗·阶段二：照表取渲染件 → `parser.parse` → produced_md（Evaluable, layer=CLEANING） | ParserFactory / MinIO | 是 |
| C3 | `metrics/cleaning.py` | produced_md vs 参考 md 比对（纯函数，逐 格式×PDF后端） | contracts | 否 |

> CLEANING 层（C1–C3）是纵向第 5 个评测点，与 M1 检索层并行交付；详见 [phase0_5_cleaning_quality_design.md](phase0_5_cleaning_quality_design.md)。

设计要点：

- **`contracts` 是依赖汇聚点。** `metrics` 不知道 `adapters` 存在，`adapters` 不知道 `metrics` 存在，二者只认 `contracts` 里的 `Evaluable` / `Metric`。`runners` 是唯一把它们组装起来的地方。这样新增一个环节 = 加一个 adapter + 一组 metric，互不牵动。
- **生成层依赖隔离。** 仅 `metrics/generation.py` 与其 `Judge` 实现引入外部判官依赖（如 RAGAS），装在 `[eval]` extra、惰性 import，生产镜像不含；第 1/2 层零外部依赖、任意环境可跑。
- **不新增 ORM 模型。** 框架只读既有存储，不触发 `src/models/**` 的文档同步与迁移规则。

---

## 五、典型调用流（一轮检索+重排评测）

```
scripts/eval/run.py
  └─ runners.pipeline_runner.run(EvalRequest)
       ├─ golden.loader 载入 samples + 前置自检（chunk 在库且 ACTIVE）
       ├─ snapshot.capture() 抓配置 + 错配校验 → .specs/snapshots/<run-id>.yaml
       ├─ for sample in dataset:
       │     ├─ adapters.recall_adapter.run(sample)   → RecallResponse（按 §六口径走 pipeline）
       │     │     └─ metrics.retrieval.compute(sample, response)   # recall@k / ndcg ...
       │     └─ adapters.rerank_adapter.run(sample, recall_out)     → RerankResponse + degrade 对照
       │           └─ metrics.rerank.compute(...)                   # rerank vs RRF 增益
       └─ reporters.html_reporter 汇总 → 基线 diff → 回归判据 → reports/<run-id>.html
```

生成层（第 3 层）在此基础上多一步 `generation_adapter` + `metrics.generation`（经 Judge），依赖非流式生成入口就绪（R1）。

**数据清洗层（CLEANING，独立并行）** 调用流不同——不走召回栈，照对应关系表跑：

```
scripts/eval/run.py --layers cleaning
  └─ runners.stage_runner.run(rendered_dataset, cleaning_evaluable, cleaning_metrics, ctx)
       ├─ 照 eval_cleaning_rendered 表取冻结渲染件（阶段一已渲染入 MinIO）
       ├─ snapshot.capture() 记 PDF_PARSER_BACKEND / 渲染器版本
       ├─ for rendered in dataset:
       │     └─ adapters.cleaning_adapter.run(rendered)   → produced_md（parser.parse，计清洗时间）
       │           └─ metrics.cleaning.compute(produced_md, 参考 md)  # 文本/标题/表格/图片/清洗时间
       └─ reporters.html_reporter（cleaning_report_template）→ reports/<run-id>.cleaning.html
```

---

## 六、必须遵守的口径与已知风险

口径（来自三层指标设计，框架适配器须照此实现，否则数字不可信）：

1. **bm25 走独立 retriever，不在 facade。** dense/sparse 走 `facade.search_dense/sparse_chunks`，bm25 走 `Bm25Retriever.recall`，固化在 `recall_adapter`。
2. **融合口径以 pipeline 为准。** 融合评测走 `RecallPipeline.execute(top_k=RECALL_RESULT_LIMIT=20)` + `fuse_with_rrf`，报告显式标注 top_k 口径，不拿分路 facade 兜底默认值下结论。
3. **provider 覆盖三态。** `SPARSE_VECTOR_PROVIDER` 的 `bge_m3 / bge_m3_http / remote_bge_m3` 三态都要进快照与对比，`remote_bge_m3`（dense+sparse 同出）最该回归。
4. **rerank 双顺序同 run 落地。** 一次 run 内同时产 rerank 生效顺序与 `degrade_to_rrf_order`，量化精排真实增益。
5. **三模型错配。** 生成器 / 判官 / 被测 CHAT 模型不得同一，`snapshot.py` 显式校验并记快照，防自评偏置。

风险：

- **R1 · 生成入口耦合 SSE（最大改造点）。** 现有生成段（`application/recall_stream_runtime._generate_answer`）为流式 + 用户模型解析上下文而写，`generation_adapter` 无法直接复用。落地前须评估抽出一个**非流式生成入口**（输入 query + 已排序候选 + 已回填正文 → 返回完整答案），供 runner 与生产 SSE 共用。此为第 3 层前置依赖。
- **R2 · 活栈与冻结语料。** 召回及以上环节需 seed 好的 MySQL/Qdrant/ES。须先建**只读冻结评测语料/租户**（固定 user_id + dataset_ids），黄金集 `expected_chunk_ids` 绑其某次 ingestion 快照；语料重灌则需重校验。
- **R3 · 判官非确定性与成本。** 判官 `temperature=0`，关键指标多次采样取均值；单轮 LLM 调用量 = 生成层条数 ×（生成 + 各判官指标），按规模预估成本。

---

## 七、落地里程碑

1. **M0 骨架与地基**：建 `src/evaluation/` 包 + `contracts/` + `models.py` + `tests/unit/evaluation/`；`pyproject.toml` 加 `[eval]` extra；CI 加 import-lint 守 `evaluation → core` 单向；搭冻结评测语料/租户（R2）。
2. **M1 检索层（自研，可独立交付）**：`golden/schema+loader` + `metrics/retrieval.py`（二值 NDCG，标注口径）+ `recall_adapter`（按 §六口径）+ `snapshot.py` + `reporters`（基线 diff + 回归判据）。指标数学进 PR 门禁，整轮 run 手动/定时。
3. **M1.5 黄金集来源（无人工）**：`golden/opensource`（主力 DuReader/T2Ranking）+ `golden/synth`（Track B）+ `golden/gen`（辅，sampler/generator/prompts）+ `gate.py`（自动门禁：异模型可答性 + 第三方检索回环 + 答案自洽）+ 模型错配校验；产出首版 50–100 条。是 M3 前置。
4. **M2 重排层**：`rerank_adapter` + `metrics/rerank.py`；同 run 双顺序对照。
5. **M3 生成 + 正确性层**：前置 = M1.5 的 `golden_answer` + R1 的非流式生成入口；`generation_adapter` + `metrics/generation.py`（Judge 抽象、惰性判官依赖、temperature=0）。
6. **M4 收口**：稳定口径/判据/配置回流 `docs/internals/rag_eval.md`。

---

## 八、实现顺序（按模块单元，从上往下写）

里程碑是粗粒度阶段，本节是可逐个落地的**模块清单**。严格按依赖排序：前一个不依赖后一个，照此从上往下实现即可。每项标注依赖、是否需活栈、能否单测。

### 阶段 0 · 地基（无依赖，最先做）

1. **`contracts/`** — 抽象端口（`Metric`/`Evaluable`/`Judge`/`Dataset`/`Store`）。全框架唯一依赖汇聚点。无外部依赖，可单测。
2. **`models.py`** — `EvalRequest`/`EvalResult`/`MetricResult`/`Snapshot`。依赖 ①。
3. **工程地基**（非代码模块）：`pyproject.toml` 加 `[eval]` extra；CI 加 import-lint 守 `evaluation→core` 单向；建 `tests/unit/evaluation/`；**搭只读冻结评测语料/租户**（R2，召回以上全部依赖它）。

### 阶段 1 · 检索层（自成闭环，第一个可交付的可跑版本）

4. **`golden/schema.py` + `golden/loader.py`** — 黄金集模型 + jsonl 加载 + 前置自检（chunk 在库且 ACTIVE）。依赖 ②。
5. **`metrics/registry.py` + `metrics/retrieval.py`** — recall@k / precision@k / mrr / ndcg / map / 三路重叠率。**纯函数，单测进 PR 门禁**。依赖 ①。
6. **`snapshot.py`** — 配置快照 + 三模型错配校验。依赖 ②。
7. **`storage/filesystem.py`** — 产物落地到 `.specs`。依赖 ①。
8. **`adapters/recall_adapter.py`** — 分路(`facade`/`Bm25Retriever`) + 融合(`RecallPipeline.execute`)，按 §六口径。**需活栈**。依赖 ①②。
9. **`runners/context.py` + `runners/stage_runner.py`** — 单环节编排。依赖 ①④⑤⑧。
10. **`reporters/base.py` + `html_reporter.py` + `json_reporter.py`** — HTML 报告（结果表 + 基线 diff + 回归判据）。依赖 ②⑦。
11. **`scripts/eval/run.py`** — 薄 CLI 入口。依赖以上全部。

➡️ **到此可跑完整检索层评测**（第一个停靠点）。

### CLEANING 层 · 数据清洗质检（与 M1 并行、可独立交付；详见 phase0_5_cleaning_quality_design.md）

- C1. **`golden/cleaning_dataset/{render,store,registry}.py`** — 阶段一：标准 md → 渲染各格式 → 存 MinIO + 写对应关系表（`eval_cleaning_doc`/`eval_cleaning_rendered`）。
- C2. **`adapters/cleaning_adapter.py`** — 阶段二：照表取冻结渲染件 → `parser.parse` → produced_md。需活栈。
- C3. **`metrics/cleaning.py`** — produced_md vs 参考 md 比对（文本完整性 + 标题/表格/图片识别专项 + 顺序/稳定性 + 清洗时间），纯函数进 PR 门禁。

➡️ **到此可跑完整数据清洗质检**（与 M1 同期停靠）。

### 阶段 1.5 · 黄金集来源（阶段 3 前置，全程无人工；详见 phase1.5 / Track B）

12. **`golden/opensource/{ingest,convert}.py`（主力）** — DuReader/T2Ranking 文档入评测租户 + 标注转 GoldenSample（doc 粒度）。
13. **`golden/synth/`（Track B）** — LLM 合成真实格式文档 + 埋点回定位（chunk 粒度，覆盖解析链路）。
14. **`golden/gen/{sampler,prompts,generator}.py`（辅路）** — 自有 chunk 反向合成，调 `ModelFactory`。
15. **`golden/gen/gate.py`** — 自动质量门禁（异模型可答性 + **第三方检索回环** + 答案自洽），无人工。

➡️ 产出**自动门禁过的首版 50–100 条**黄金集。

### 阶段 2 · 重排层

16. **`adapters/rerank_adapter.py`** — `PostRecallReranker.rerank`，同 run 内并产 `degrade_to_rrf_order` 对照。需活栈。
17. **`metrics/rerank.py`** — rerank vs RRF 顺序的 ndcg/mrr 增益。纯函数。

### 阶段 3 · 生成 + 正确性层

- **0' 前置改造**（在 `core`，不在框架内）：抽**非流式生成入口**（R1，最大改造点），否则 adapter 无法复用现有流式生成段。
18. **`contracts/judge.py`** — LLM-as-judge 抽象（阶段 0 留位，此处补实现契约）。
19. **`adapters/generation_adapter.py`** — 非流式生成入口 + `assemble_context`。需活栈。
20. **`metrics/generation.py`** — RAG Triad + Context Recall + Answer Correctness。惰性导入判官依赖、`temperature=0`。
21. **`runners/pipeline_runner.py`** — 串联 retrieval→rerank→generation 一轮跑完。

### 阶段 4 · 收口

22. **`hooks/logging_hook.py`** 观测打磨；稳定口径/判据回流 `docs/internals/rag_eval.md`。

> 一句话：**先抽象（contracts/models）→ 检索层闭环（能跑即交付）→ 补黄金集 → 加重排 → 最后啃生成层（含非流式入口改造）**。

---

## 九、已知边界与缺口（诚实声明，避免误用）

经方法论审查保留的已知局限,落地时须正视:

- **"噪声恒定"是待验证假设(B1)**：相对比较消化噪声的前提,换 provider 时减弱。**M1 第一件事是测噪声地板**(同配置重跑 + 等价配置互比,见 trend §5.0),用它校准回归判据;跨 provider 结论降级为"提示性"。
- **小样本统计审慎(B6)**：50–100 条分桶后每桶 n≈12–25,裸阈值会触发假回归。判据须满足 `n≥30` + 超噪声地板 + 置信区间。
- **数据清洗质量已纳入直接评测（B9 已覆盖）**：新增 CLEANING 评测点(数据清洗=文档经 parser 转成结构化 md),以**标准 md 为参考做 round-trip**(md→渲染各格式→parser 清洗回 md→比对),含标题/表格(三模式)/图片识别专项 + 数据清洗时间,逐 `(format, pdf_backend)` 分桶,直接量化换 PDF backend 的内容保真变化。详见 [phase0_5_cleaning_quality_design.md](phase0_5_cleaning_quality_design.md)。Track B 锚点丢弃率退为辅助信号。**分片(chunk)质量不在评测范围**（如需另列模块）。
- **embedding 维度/collection 布局与多租户隔离未纳入(B10)**：不同 embedding 模型维度不同→可能落不同 collection/分桶,跨 provider 对比时向量库布局本身变了;快照须记录 embedding 维度与 collection 布局。多租户隔离正确性(召回不得越权命中他租户 chunk)对线上是质量+安全双重风险,建议补一条隔离负样本检查(范围外 chunk 命中数必须为 0),当前未纳入。
- **同源 LLM 偏置(B5)**：模型错开只防同名,防不住同源;合成集生成层绝对分偏乐观,仅作相对追踪。
- **判官需校准(B7)**：reference-free 指标可信度=判官可信度,须留人工标注校准集测 judge-human 一致率,换模型/版本重测。

---

## 十、测试数据准备与质检严格分离（跨层统一原则）

**所有评测层一致遵守：测试数据准备是独立的前置阶段，质检只消费"已准备好、已冻结、已入表/入库"的数据，绝不在质检 run 里内联准备。** 准备未完成，质检不开始；这是可复现的根基（数据清洗层的两阶段拆分只是该原则的一个实例）。

| 层 | 阶段一：测试数据准备（前置、冻结） | 阶段二：质检（照表/集消费） | 两阶段锚点 |
| --- | --- | --- | --- |
| 数据清洗（CLEANING） | `golden/cleaning_dataset/`：md→渲染各格式→存 MinIO | `cleaning_adapter` + `metrics/cleaning` 照表取渲染件比对 | `eval_cleaning_doc/rendered` 表 |
| 检索 / 重排 / 生成 / 正确性 | **冻结评测语料**（R2，EvalIngestor 入 `eval_corpus_chunk` + ES/Qdrant 评测 namespace）+ **黄金集**（M1.5：opensource/synth/gen+gate） | phase1/2/3 `*_adapter` + `metrics/*` 照黄金集跑 | `eval_query`+`eval_qrel` 表（+ 冻结语料 ingestion 快照） |

落地保证：

- **就绪门禁**：质检入口先做"数据就绪自检"——检索类用 `loader.precheck`（黄金集 chunk 在库且 ACTIVE）、清洗类用对应关系表存在性校验；不就绪即判本轮无效、不跑指标。
- **冻结与版本**：准备产物冻结并记版本（语料 ingestion 快照 / `md_hash` / `renderer_version` / 黄金集绑定），质检 run 只读；版本变了不与旧数据同口径比。
- **职责切分**：准备是数据工程（渲染/灌库/合成/入表），质检是纯评测（取数据→算指标）；二者代码分模块、分阶段、可各自交付。

---

## 十一、原则

数据可复现 > 指标好看；**测试数据准备与质检严格分离（准备先行、冻结、质检只消费）**；适配器是对生产代码的唯一接缝，签名变更只改一处；依赖单向 `evaluation → core`，生产路径绝不 import 评测；检索/重排/清洗指标纯函数化、进 CI，整轮 run 靠活栈、手动/定时；判官依赖惰性隔离在 `[eval]` extra；生成器/判官/被测模型三者错开。
