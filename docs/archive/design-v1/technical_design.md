# RAG 质量评估模块 — 技术设计（指标口径权威源）

> **归档文档：仅供追溯，不是当前权威依据。** 替代关系见 [归档说明](../README.md)。

> 状态：设计稿（`.specs/rag-quality-eval/`，git-ignored 临时交付物）
> 范围：对 toLink-Rag(LinkRag) 完整 RAG 链路（检索 → 重排 → 生成 → 含标准答案的正确性）提供可量化、可复跑的质量评估。
> 定位：本文是**指标定义与口径的权威源**；架构落地见 [framework_design.md](framework_design.md)，分阶段见 phase0–3，黄金集来源见 phase1.5 / Track B，存储见 eval_storage / minio，看板见 trend_dashboard。
> 沉淀：稳定口径最终回流 `docs/internals/rag_eval.md`。
>
> ⚠️ **存储口径已更新（权威见 [eval_storage_design.md](eval_storage_design.md)）**：本文凡涉及黄金集主源
> `eval_golden_sample` / 反向合成从 `kb_document_chunk` 取片段 / 语料走真实 ingestion，一律改为：黄金集
> 落 **`eval_query` + `eval_qrel`**，语料/采样在评测自持 **`eval_corpus_chunk`**（经 EvalIngestor、不走
> `ParseTaskPipeline`），`user_id` 为路由常量 `EVAL_USER_ID`。指标定义本身不受影响。

---

## 一、结论先行

本模块对 LinkRag 的 RAG 链路（解析→分块→三路索引→RRF 融合召回→rerank 精排→LLM 生成）做质量评估，回答两类问题：换 provider / 调 top_k·threshold / 改 enabled_sources 后**有没有退化**，以及生成答案**忠实、相关、正确与否**。基本决策：

1. **结构上：评估引擎作顶层独立包 `src/evaluation/`**（与 `api`/`application`/`services` 同级，强调它是**离线驱动器、不属生产 `core`**）。指标计算、调用链 adapter/runner、黄金集模型与来源都是可复用、可被 `tests/unit/evaluation` 覆盖的库代码。结构化评测数据落**独立 eval schema 表**（见 eval_storage），渲染件/不可变快照落对象存储；依赖单向 `evaluation → core`。
2. **方法上：分层混合。** 检索/重排层指标自研（reference-based，纯数学、确定性强、可进 CI）；生成/正确性层先集成 RAGAS 作离线判官，后按业务信号内化为自研、接回项目 LLM provider 层。
3. **数据上：零人工。** 黄金集**以开源中文数据集为主力**（doc 粒度）+ 自有 chunk 反向合成/Track B（辅，chunk 粒度），用**自动质量门禁**替代人工抽检；评测定位为**稳定的相对比较尺**而非绝对权威尺（前提"噪声恒定"须经噪声地板验证，见 §七.8）。

---

## 二、可评估环节与五个评估点（对齐 `Layer` 枚举）

链路上有五个评估点，与 phase0 `Layer` 枚举一致（数据清洗为最上游，详见 [phase0_5_cleaning_quality_design.md](phase0_5_cleaning_quality_design.md)；**分片质量不在评测范围**）：

| Layer | 评估点 | 产出 | 方法 |
| --- | --- | --- | --- |
| CLEANING | 各格式经 parser 清洗 → md（`IFileParser.parse`） | 文本完整性 + 标题/表格/图片识别专项 + 顺序/稳定性 + **数据清洗时间**（逐 格式×PDF后端） | 自研，**以标准 md 为参考 round-trip**，无需 LLM/人工 |
| RETRIEVAL（第1层） | `RecallResponse`（RRF 融合后候选） | recall/precision/ndcg/mrr/map/三路重叠率/延迟 | 自研，reference-based，无需 LLM |
| RERANK（第2层） | `RerankResponse` / `RerankedHit`（精排后候选） | 对 RRF 的增量 ΔNDCG/ΔMRR + applied 率 | 自研 |
| GENERATION（第3层） | `answer`（生成答案） | RAG Triad（Faithfulness/Answer Relevancy/Context Relevance） | LLM-as-judge，先集成 RAGAS |
| CORRECTNESS（第3层） | `answer` + 标准答案 | Context Recall / Answer Correctness | LLM-as-judge，需 `golden_answer` |

### 第 1 层 · 检索/召回质量（reference-based，自研，无需 LLM）

依据黄金集 `expected_chunk_ids`（或 doc 粒度 `expected_doc_ids`）即可计算，成本低、确定性强、可 CI 化。

| 指标 | 衡量 | 排序敏感 | 主要用于 |
| --- | --- | --- | --- |
| Recall@k / Hit@k | 期望命中是否落在前 k | 否 | 召回层：广召回是否漏 |
| Precision@k | 前 k 中相关比例 | 否 | 召回层：噪声比 |
| MRR | 首个相关结果排名 | 是 | rerank 层：首位质量 |
| NDCG@k | 相关性 + 位置加权 | 是 | rerank 层：精排是否把对的排前 |
| MAP | 多 query 平均精度 | 是 | 综合排序质量 |
| 命中重叠率 | dense/sparse/bm25 各自独有/共有命中 | — | 三路互补性（读 `RecallHit.scores` 非 None 推导） |
| 各路延迟 | 单 query 各路耗时 | — | 换 provider 回归 |

口径约定：**召回层主看 Recall@k**，**rerank 层主看 NDCG@k 与 MRR 的增量**。

> **相关性标签口径**：自有/DuReader 黄金集仅命中/不命中二值，故为**二值相关性 NDCG**；T2Ranking 自带 4 级分级相关，可跑**分级 NDCG**。两者数值不可比——台账以 `relevance_scale`（binary/graded）区分、指标名分用 `ndcg_binary`/`ndcg_graded`，看板不同 scale 不连线（见 trend §三）。

### 第 2 层 · 重排质量

rerank 当前为 best-effort 降级设计，必须在一次 run 内同时落"rerank 生效 vs `degrade_to_rrf_order`"两种顺序、建立在**同一份已过滤正文的候选集**上，量化精排相对纯 RRF 的真实增益（ΔNDCG/ΔMRR），并**如实报告 `rerank_applied` 率**（降级样本 Δ=0，避免稀释出假"无增益"）。详见 [phase2_rerank_design.md](phase2_rerank_design.md)。

### 第 3 层 · 生成质量（LLM-as-judge，先集成 RAGAS）

针对 `answer`，采用 TruLens 提出、RAGAS/DeepEval 通行的 "RAG Triad"：

- **Faithfulness / Groundedness（忠实度）**：答案每个论断能否被召回上下文支持。最高信号、直接抓幻觉，且 **reference-free（无需标准答案/人工标注）**。
- **Answer Relevancy（答案相关性）**：答案与原始 query 的语义贴合度（reference-free）。
- **Context Relevance / Precision（上下文相关性）**：召回上下文里真正服务于回答的比例（reference-free）。

### 第 3 层 · 端到端正确性（需标准答案）

- **Context Recall**：回答所需信息有多少出现在召回上下文。
- **Answer Correctness / Accuracy**：答案与标准答案的事实一致性。

生成/正确性层共用一套 LLM 判官，先由 RAGAS 提供，后续按需内化（phase3 §六）。**判官需校准**：reference-free 指标可信度=判官可信度，须留人工标注校准集测 judge-human 一致率，换模型/版本重测（phase3 §八）。

---

## 三、黄金集 Schema

工作态主源为 `eval_query` + `eval_qrel` 两表（eval_storage §4.3，取代旧 `eval_golden_sample` 单表）；冻结导出为 jsonl（绑 ingestion 快照）。逻辑结构：

```jsonc
{
  "id": "q-001",
  "query": "用户原始问题文本",
  "user_id": 123,                       // 冻结评测租户，保证可复现与权限隔离
  "dataset_ids": [45],                  // 召回范围；空列表=全库
  "expected_chunk_ids": ["c-1","c-9"],  // chunk 粒度 reference（合成/Track B）
  "expected_doc_ids": [7],              // doc 粒度（开源数据集主力 / chunk 失效兜底）
  "golden_answer": "标准答案文本",       // 第3层 LLM-as-judge / Track B 埋点真值
  "type": "keyword|paraphrase|longtail|cross_doc",
  "label_granularity": "chunk|doc",     // 标注粒度
  "gate_status": "passed|hard_case",    // 自动门禁结果
  "note": "构造说明"
}
```

约定：固定 `user_id`/`dataset_ids`、绑冻结评测语料；`golden_answer` 仅第 3 层用，第 1 层即便缺它也能独立跑。完整列以 eval_storage §3.2 为准。

---

## 四、黄金集来源（无人工；开源主力 + 合成辅）

核心前提：**端到端评测集必须长在自有语料上**——`expected_chunk_ids` 必须指向自家 chunk 库的真实 id。但 LinkRag 为通用多领域 RAG，开源通用集本就贴合，故采"开源主力 + 合成辅"两条 track，全程零人工。详见 [phase1_5_golden_gen_design.md](phase1_5_golden_gen_design.md) 与 [phase1_5_trackB_llm_corpus_design.md](phase1_5_trackB_llm_corpus_design.md)。

### 主力 · 开源中文数据集（doc 粒度，零人工）

把开源检索数据集的**文档灌入评测租户**（走真实 ingestion），用其 `query→相关段落`标注落到 `expected_doc_ids`，doc 粒度评检索。选定（授权已核 2026-06）：

- **DuReader_retrieval**（Apache-2.0）：~9.7 万真实搜索 query，**检索层主力**。
- **T2Ranking**（Apache-2.0）：4 级分级相关→分级 NDCG，**模型选型 + 重排辅证**（doc 粒度对重排只给近似，chunk 级 ordering 看 Track B）。
- **C-MTEB**（逐子集授权）：仅 embedding/rerank 模型横评。
- **CMRC2018**（CC BY-SA 4.0）：可选生成正确性（抽取式短答案，弱信号）。
- **不取领域子集**（Multi-CPR / C-MTEB Ecom·Medical·Video）：通用 RAG、无固定垂直。

### 辅路 · 自有 chunk 反向合成 + Track B 合成语料（chunk 粒度，零人工）

- **反向合成**：从 `src/core/storage/chunks`（`ChunkRepository` → `kb_document_chunk`）取片段喂 LLM，反向生成"该 chunk 可回答的问题 + 标准答案"，源 `chunk_id` 即 `expected_chunk_ids`。位置 `src/evaluation/golden/gen/`。
- **Track B**：LLM 生成真实格式文档（PDF/DOCX/HTML/MD）+ distinctive 锚点埋点，走真实 ingestion 后按锚点（归一化）回定位 chunk_id——**唯一覆盖 parser/chunker 全链路**的来源。位置 `src/evaluation/golden/synth/`。

三条不可省的纪律（已无人工化）：

- **自动质量门禁**（替代人工评审，`golden/gen/gate.py`）：异模型可答性 + **第三方独立检索器回环**（不用被测召回，防循环论证）+ 答案自洽。
- **真实查询冷启动**：用 recall stream 线上 query 日志作种子，贴近业务分布。
- **模型错配（防自评偏置）**：生成器 / 门禁复核 / 判官 / 被测 CHAT 两两错开；`snapshot.validate_model_distinctness` 同名告警。注意只防同名、防不住同源 LLM 偏置（合成集生成层绝对分偏乐观，仅作相对追踪）。

---

## 五、整体结构（引擎 src/evaluation + 结构化数据进 DB + 渲染件进对象存储）

```
src/evaluation/                    # 顶层独立包：评估引擎（可复用 / 可测 / 进 CI）
├── contracts/                     # 抽象端口（Metric/Evaluable/Judge/Dataset/Store）
├── models.py                      # EvalRequest / EvalResult / 各层指标结果 dataclass
├── golden/
│   ├── cleaning_dataset/{render,store,registry}.py  # 数据清洗·阶段一：md→渲染存 MinIO + 对应关系表
│   ├── opensource/{ingest,convert}.py  # 主力：开源数据集 → GoldenSample（doc 粒度）
│   ├── synth/                     # Track B：合成真实格式文档 + 埋点回定位（chunk 粒度）
│   ├── gen/{sampler,prompts,generator,gate}.py  # 辅：自有 chunk 反向合成 + 自动门禁
│   ├── schema.py                  # GoldenSample + 加载/校验
│   └── loader.py                  # 前置自检（chunk 在库且 ACTIVE）
├── metrics/
│   ├── cleaning.py                # 数据清洗层（自研）：produced_md vs 参考 md（文本/标题/表格/图片/清洗时间）
│   ├── retrieval.py               # 第1层（自研）：recall@k/precision@k/mrr/ndcg/map/重叠率
│   ├── rerank.py                  # 第2层（自研）：对 RRF 增量 Δ
│   └── generation.py              # 第3层：RAGAS 适配，惰性导入（[eval] extra）
├── adapters/                      # 对生产代码的唯一接缝（实现 Evaluable）
│   ├── cleaning_adapter.py        # 数据清洗·阶段二：照表取渲染件 → parser.parse → produced_md
│   ├── recall_adapter.py          # 复用 application.recall_pipeline_provider.get_recall_pipeline()
│   ├── rerank_adapter.py          # PostRecallReranker（core-only 直构）
│   └── generation_adapter.py      # 对接 R1 非流式生成入口
├── runners/{context,stage_runner,pipeline_runner}.py
├── snapshot.py                    # 配置快照 + 模型错配校验
├── reporters/{base,html_reporter,json_reporter,trend_report}.py  # HTML 报告 + 趋势看板
└── store/                         # 独立 EvalBase + EvalStore（eval schema 表，不在 src/models）

tests/unit/evaluation/             # 引擎单测（指标数学进 PR 门禁）
scripts/eval/run.py                # 薄 CLI 入口

评测数据（git-ignored）：
- 结构化（黄金集/run/快照/指标）→ 独立 eval schema 表（eval_storage_design.md）
- 渲染件（HTML 报告 reports/<run-id>.html、trend.html）→ MinIO tolink-rag-eval 桶 / .specs
- 不可变快照（黄金集冻结 jsonl）→ MinIO / .specs
- 无 DB 环境 → ResultStore 文件后端回退（结果 json + HTML 报告落 .specs）
```

**职责边界与依赖方向**

- 引擎承载"哪条路调哪个函数、top_k 取哪个值、指标怎么算"，可 import、被 `tests/unit/evaluation/` 覆盖、进 CI。
- **依赖方向单向（硬约束）**：`evaluation → core` 为主；`recall_adapter` 复用 `application.recall_pipeline_provider`、`store` 复用 `services.storage`，属有意识取舍，import-lint 白名单显式放行；生产请求路径绝不 import `evaluation`。
- **RAGAS 可选惰性导入**：仅 `metrics/generation.py` 用到时 import，装 `[eval]` extra，生产镜像不含。
- **eval schema 表在 `src/evaluation/store`（独立 EvalBase、不并入生产 alembic）**，不触发 CLAUDE.md §四（仅 `src/models/**` 触发）。引擎不改 `src/models`。

---

## 六、评测调用链的正确口径（必须与生产一致）

runner 调用链有几处必须按生产实际写，否则数字不可信：

1. **bm25 走独立 retriever，不在 facade。** dense/sparse 走 `VectorStorageFacade.search_dense_chunks/search_sparse_chunks`（`src/core/storage/vector/facade.py`），bm25 走 `Bm25Retriever.recall`（`src/core/storage/es/bm25_retriever.py`）。固化在 `adapters/recall_adapter.py`。
2. **融合口径以 pipeline 为准。** 融合评测必须走 `RecallPipeline.execute(RecallRequest(..., top_k=RECALL_RESULT_LIMIT=20))` + `fuse_with_rrf`，报告显式标注 top_k 口径。复用 `application.recall_pipeline_provider.get_recall_pipeline()` 装配，保证与线上一致（注意其 `@lru_cache` 单例，跨配置对比须每态独立进程，见 phase1 §5.5）。
3. **provider 覆盖三态。** `SPARSE_VECTOR_PROVIDER` 的 `bge_m3 / bge_m3_http / remote_bge_m3` 三态都进快照与对比，`remote_bge_m3`（dense+sparse 同出）最该回归。
4. **生成入口（R1）。** 现有 `application/recall_stream_runtime._generate_answer` 为流式 SSE 而写；`provider.generate()` 非流式原语已存在，R1 = 把"拼上下文→建 prompt→调模型"抽成非流式入口供 runner 与 SSE 共用（phase3 §三）。

---

## 七、运行时与可复现（执行模型 / 冻结语料 / 判据 / 噪声地板）

### 1. 运行环境依赖：评测不是纯函数

- **纯指标计算（`metrics/retrieval.py`、`metrics/rerank.py`）**：纯函数、无外部依赖，**可单测、挂 PR 门禁**。
- **端到端评测 run（adapter 驱动真实链路）**：需活的 MySQL + Qdrant + ES + 可用模型，属 integration/acceptance 级，**只手动/定时触发，不挂 PR 门禁**。

### 2. 冻结评测语料（可复现的地基）

设一份**只读、冻结、专供评测**的 corpus/租户（固定 `user_id` + `dataset_ids`），与生产隔离。**语料主动灌而非复用生产现状**：开源数据集文档 + LLM 合成文档经真实 ingestion 灌入（phase1.5 §二）。黄金集绑该 corpus 某次 ingestion 快照；语料重灌/换分块后 `expected_chunk_ids` 需重校验（`loader.precheck`），Track B 可经锚点**自动重定位**重建（Track B §3.5）。

### 3. 执行模型与产物标识

- **入口**：`scripts/eval/run.py --golden <id> --layers retrieval,rerank,gen,correctness --run-id <id>`（薄壳）。
- **run-id**：`<yyyymmdd-hhmm>-<gitsha>-<标签>`，与 `eval_run`/`eval_metric_result`/`reports/<run-id>.html` 一一对应。
- **快照**：见 §五 `snapshot.py`，含错配校验后的模型名、provider 三态、embedding 维度/collection 布局。

### 4. 基线与回归判据

- **基线**：选定 run-id 作 baseline（每 config 组各留各的，指针 `baselines/<config-key>.txt`）。
- **比对**：同口径 diff 当前 run vs baseline，逐指标、逐 type 桶。
- **判据**：`Recall@k 跌>2pp / NDCG 跌>0.02 / Faithfulness 跌>0.05` 仅为**初始占位**，M1 经噪声地板校准后用 `σ_metric` 替换；须满足**最小样本量 n≥30** 且超置信区间才判回归。判据入配置可调。
- **门禁边界**：用于"换 provider/调参"的人工/定时回归决策，**不作 PR 自动门禁**。

### 5. 判官的非确定性与成本

judge `temperature=0`；多采样降方差（注意 t=0 多采样近似单次，真要暴露方差用 prompt 变体）；judge 需人工校准集测一致率。单轮 LLM 调用量按黄金集规模预估。

### 6. 样本量与统计审慎

首版黄金集 50–100 条，分桶后每桶 n 很小。报告须标注每桶样本量；**小样本桶（n<30）不触发回归、只作定性参考**。

### 7. 生成层与 SSE runtime 的解耦（R1）

`generation_adapter` 复用 R1 非流式生成入口（`core` 侧，与 SSE 共享拼装段）。本前置由实现方提前完成（phase3 §三）。

### 8. 噪声地板（"相对比较"成立的前提，必做）

零人工方案靠"相对比较消化噪声"，前提是"噪声在各配置间恒定"——换 provider 时减弱。**M1 第一件事**：同配置重跑 + 等价配置互比，得每指标经验噪声阈值 `σ_metric`，据此设回归判据；跨 provider 结论降级为"提示性"（详见 trend §5.0）。

---

## 八、落地步骤（建议里程碑）

1. **M0 骨架与地基**：建 `src/evaluation/` + `contracts/`+`models.py` + `tests/unit/evaluation/`；`pyproject.toml` 加 `[eval]` extra；import-lint 守依赖方向；搭冻结评测语料/租户（§七.2）+ 独立 eval schema。
2. **M1 检索层（可独立交付）**：`golden/` + `metrics/retrieval.py` + `recall_adapter`（§六口径）+ `snapshot` + `reporters/html_reporter`（基线 diff + 回归判据）。指标数学进 PR 门禁；**整轮跑出首轮数据后立即测噪声地板（§七.8）校准判据**。
3. **M1.5 黄金集来源（无人工）**：`golden/opensource`（主力，DuReader/T2Ranking）+ `golden/synth`（Track B）+ `golden/gen`（辅）+ `gate.py`（自动门禁）；产出首版 50–100 条。
4. **M2 rerank 层**：`rerank_adapter` + `metrics/rerank.py`；同 run 双序对照。
5. **M3 生成 + 正确性层**：前置 = R1 非流式入口 + golden_answer + 判官校准集；`generation_adapter` + `metrics/generation.py`（RAGAS 惰性、judge t=0）。
6. **M4 收口**：稳定口径/判据回流 `docs/internals/rag_eval.md`（含 eval schema 说明）；趋势看板 + 模型选型旁路按需。

---

## 九、原则

数据可复现 > 指标好看；评测是**稳定的相对比较尺**，噪声地板未校准前不下绝对结论；单一变量对比（一次只改一个配置）；换 BGE provider（含 `remote_bge_m3`）必须同口径回归；引擎进 `src/evaluation/`（可复用/可测/进 CI），结构化数据进独立 eval schema、渲染件进对象存储；依赖单向 `evaluation → core`（provider/storage 复用经白名单），生产路径绝不 import 评测；RAGAS 等判官依赖惰性隔离在 `[eval]` extra；生成器/门禁/判官/被测模型两两错开（只防同名、不防同源）；黄金集零人工（开源主力 + 合成辅 + 自动门禁）。
