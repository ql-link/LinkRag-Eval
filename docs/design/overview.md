# RAG 评估框架 — 设计文档总览

> 状态：设计稿集合（`.specs/rag-quality-eval/`，git-ignored 临时交付物）
> 目的：把一套对 toLink-Rag 全 RAG 链路的质量评估框架，从总架构拆到可逐个落地的模块设计。
> 一句话定位：**评估引擎（代码）进 `src/evaluation/`，可复用 / 可测 / 进 CI；评测产物（黄金集 / 快照 / 报告 / 台账）留 `.specs/` 或 MinIO，git-ignored。依赖单向 `evaluation → core`。**

---

## 一、按角色的阅读路线

| 我是… | 先读 | 再读 |
| --- | --- | --- |
| 第一次了解全局 | [framework_design.md](framework_design.md)（总架构 + 实现顺序） | [technical_design.md](technical_design.md)（五层评估点口径） |
| 要动手实现 | [framework_design.md §八](framework_design.md)（按模块单元的实现顺序） | 对应阶段文档（见下表） |
| 关心某一环节口径 | [technical_design.md](technical_design.md) | 该层阶段文档 |
| 关心产物 / 看板 / 存储 | [trend_dashboard_design.md](trend_dashboard_design.md) | [minio_eval_bucket_design.md](minio_eval_bucket_design.md) |

---

## 二、文档清单与职责

| 文档 | 职责 | 对应模块 / 里程碑 | 状态 |
| --- | --- | --- | --- |
| [technical_design.md](technical_design.md) | 五层评估点定义与口径（CLEANING/RETRIEVAL/RERANK/GENERATION/CORRECTNESS）、黄金集 schema、黄金集来源、运行时与可复现判据 | 全局口径 | 设计稿 |
| [framework_design.md](framework_design.md) | 总架构：横切骨架 + 5 个纵向评测点、依赖方向、目录结构、按单元实现顺序 | 全局 / M0–M4 | 设计稿 |
| [phase0_design.md](phase0_design.md) | 地基：`contracts/` 抽象端口 + `models.py` 数据模型 + 工程地基 | 模块 1–3 / M0 | 设计稿 |
| [phase1_design.md](phase1_design.md) | 检索层闭环：golden/metrics/snapshot/storage/recall_adapter/runners/reporters/CLI | 模块 4–11 / M1 | 设计稿 |
| [phase0_5_cleaning_quality_design.md](phase0_5_cleaning_quality_design.md) | 数据清洗质量（文档→md，仅清洗、不含分片）：参考真值首选真实 md 数据集 `rojasdiego/chinese-markdown`，以标准 md 为参考 round-trip，标题/表格三模式/图片识别 + 清洗时间 + 两阶段(数据集准备/质检)，逐 (格式×PDF后端)，零人工 | CLEANING 层 / M1 并行 | 设计稿 |
| [phase1_5_golden_gen_design.md](phase1_5_golden_gen_design.md) | 黄金集来源：开源数据集（主力）+ 自有 chunk 反向合成（辅）+ 自动门禁，无人工 | 模块 12–15 / M1.5 | 设计稿 |
| [phase1_5_trackB_llm_corpus_design.md](phase1_5_trackB_llm_corpus_design.md) | Track B：LLM 合成真实格式文档 + 埋点回定位，覆盖解析/分块全链路 | M1.5 辅路 | 设计稿 |
| [phase2_rerank_design.md](phase2_rerank_design.md) | 重排层：同 run 双序对比、对 RRF 增量 Δ、rerank_applied 率 | 模块 16–17 / M2 | 设计稿 |
| [phase3_generation_design.md](phase3_generation_design.md) | 生成 + 正确性层：R1 契约、Judge 抽象、RAG Triad + 正确性、pipeline_runner | 模块 18–21 / M3 | 设计稿 |
| [trend_dashboard_design.md](trend_dashboard_design.md) | 多轮趋势/回归看板：指标台账（→ `eval_metric_result` 表）+ 同口径分组 + trend.html | M4 旁路 | 设计稿 |
| [eval_storage_design.md](eval_storage_design.md) | **存储权威稿**：数据持久化 + 存储隔离 + 解耦灌库（评测自持 `EvalBase`/`eval_corpus_chunk`、不走 ParseTaskPipeline、足迹隔离、user_id 路由常量）。已合并 eval_ingest_decoupled / eval_data_schema / eval_storage_isolation 三份 | 横切（存储） | 设计稿 |
| [minio_eval_bucket_design.md](minio_eval_bucket_design.md) | 评测产物 MinIO 桶：桶/键布局/清单对象/双后端 | 横切（存储） | 设计稿 |
| [templates/eval_report_template.html](templates/eval_report_template.html) | HTML 报告模版（检索/重排/生成，简洁美观、自包含、涨绿跌红、口径脚注） | M1 产物 | 模版 |
| [templates/cleaning_report_template.html](templates/cleaning_report_template.html) | 数据清洗质检 HTML 报告模版（标题/表格/图片/清洗时间，逐 格式×PDF后端） | CLEANING 产物 | 模版 |

---

## 三、实现顺序速查（来自 framework_design §八）

```
阶段0 地基        ① contracts/  ② models.py  ③ 工程地基([eval]extra/import-lint/冻结语料)
   ↓
阶段1 检索层      ④ golden  ⑤ metrics/retrieval  ⑥ snapshot  ⑦ storage
（第一个可跑闭环） ⑧ recall_adapter  ⑨ runners  ⑩ reporters  ⑪ CLI   ← 停靠点：可跑检索评测
   │
   ├─ 并行 ─ CLEANING 层(数据清洗质检)  C1 cleaning_dataset(render/store/registry)
   │         C2 cleaning_adapter  C3 metrics/cleaning   ← 与 M1 并行,独立可交付
   ↓
阶段1.5 黄金集     ⑫ opensource(主力) ⑬ synth/TrackB ⑭ gen(辅) ⑮ gate(自动门禁)  ← 停靠点：自动门禁过的首版 50–100 条
   ↓
阶段2 重排层      ⑯ rerank_adapter  ⑰ metrics/rerank
   ↓
阶段3 生成层      0' R1非流式入口(core,前置) → ⑱ judge ⑲ generation_adapter ⑳ metrics/generation ㉑ pipeline_runner
   ↓
阶段4 收口        ㉒ 口径回流 docs/internals/rag_eval.md + 趋势看板 + MinIO 产物
```

一句话：**先抽象 → 检索层闭环（能跑即交付）→ 补黄金集 → 加重排 → 最后啃生成层（含 R1 改造）**。

---

## 四、跨文档关键决策（速查）

| 决策 | 出处 | 要点 |
| --- | --- | --- |
| 引擎 vs 产物边界 | framework §五 / 九 | 引擎进 `src/evaluation/`；产物留 `.specs/` 或 MinIO |
| 依赖方向单向 | framework §五 | `evaluation → core`；生产路径绝不 import 评测；import-lint 守 |
| `StageOutput` 统一三层产出 | phase0 §3.3 | 指标只认归一化 `ranked`/`answer`/`contexts`，不依赖 `raw` |
| `RankedHit.sources` 为集合 | phase0 §3.2（审查修订） | 融合项可多源；三路重叠率读它、不读 raw |
| `Metric.compute` 统一 async | phase0 §4.3（审查修订） | 生成层需 await judge；检索层 async 内部纯函数 |
| top_k 单一真相源 | phase0 §3.7（审查修订） | 一律取 `RECALL_RESULT_LIMIT`，三处不各立默认 |
| 召回口径对齐生产 | phase1 §5.3 | 复用 `get_recall_pipeline()`；取舍：`evaluation→api` 白名单放行 |
| 三路重叠率免调分路 | phase1 §5.2 | 由 `RecallHit.scores` 非 None 推导 |
| lru_cache 跨配置陷阱 | phase1 §5.5（审查修订） | 换 provider 对比须每态独立进程或绕缓存直建 |
| 重排同 run 双序可比 | phase2 §4.2 | rerank 序 vs degrade_to_rrf_order，共享同一 content-present 集 |
| 重排适配器 core-only | phase2 §4.3 | `PostRecallReranker()` 直构，不依赖 api |
| 必报 rerank_applied 率 | phase2 §5.3 | 降级样本 Δ=0，避免稀释出假"无增益" |
| R1 非流式入口 | phase3 §三 | `provider.generate()` 已存在，R1=抽编排不是造功能 |
| 判官先集成后内化 | phase3 §六 | 首版 RAGAS（惰性、[eval] extra），后接 ModelFactory |
| 三模型错配防偏置 | phase3 §八 | 生成器/判官/被测 CHAT 不得同一，snapshot 校验 |
| 黄金集来源（无人工） | phase1.5 §一/§九 | 开源数据集（DuReader/T2Ranking）为**主力**（doc 粒度）+ 自有 chunk 反向合成/Track B（辅，chunk 粒度）+ 自动门禁；C-MTEB 仅模型选型 |
| 标尺定位 | phase1.5 §一 / trend §5.0 / framework §九 | 稳定比较尺 > 绝对权威尺；噪声靠相对比较消化，**前提"噪声恒定"须经噪声地板验证** |
| 数据可复现 > 指标好看 | technical §九 | 冻结评测语料/租户；黄金集绑 ingestion 快照 |
| 测试数据准备与质检严格分离 | framework §十 | **跨层统一**：准备(冻结语料/黄金集/清洗渲染件)是独立前置阶段，质检只消费已就绪数据，绝不内联准备；就绪门禁(precheck/对应表)把关 |

---

## 五、两个需要你拍板/前置的事项

1. **R1 非流式生成入口**（phase3 §三）：你已确认提前完成。落 `core`、与 SSE 共享拼装段，契约见 phase3 §三。
2. **冻结评测语料/号段**（technical §七.2 / phase0 §六.4 / **构建策略见 phase1.5 §二** / **存储见 [eval_storage_design.md](eval_storage_design.md)**）：召回及以上全部依赖，需最先建。要点——`EVAL_USER_ID`（路由常量）+ `dataset_ids`、只读冻结、gen/rerank 预置 CHAT/RERANK 模型；**语料主动灌而非复用生产现状**：用 EvalIngestor（复用 core 组件、不走 `ParseTaskPipeline`）灌进**评测自持 `eval_corpus_chunk` + ES/Qdrant 评测 namespace**，覆盖文档类型/结构/领域的代表性文档。

---

## 六、产物落点一览

```
评估引擎（代码，进 CI）        src/evaluation/（含 store/ 独立 EvalBase）+ tests/unit/evaluation/ + scripts/eval/run.py
被评测数据                     语料 → eval_corpus_chunk（EvalBase，自持，非生产 chunk 表）+ ES/Qdrant 评测 namespace
                              黄金集 → eval_query + eval_qrel 表
评测输出（结构化）             指标 → eval_metric_result 表；运行+快照 → eval_run 表（独立 EvalBase）
评测输出（渲染件 blob）        HTML 报告 reports/<run-id>.html、trend.html → MinIO tolink-rag-eval 桶 / .specs
不可变快照                     黄金集冻结 jsonl 导出 → MinIO / .specs
长期契约/口径回流（M4）        docs/internals/rag_eval.md（含 eval schema 说明）
无 DB 环境回退                 ResultStore 文件后端：结果 json + HTML 报告落 .specs
```

---

## 七、当前状态

设计稿体系（12 份 .md + 2 份 HTML 模版）已成型，覆盖总架构 + **五个纵向评测点**（数据清洗/检索/重排/生成/正确性）+ 实现阶段 M0–M4（含与 M1 并行的 CLEANING 层）+ 黄金集双 track + 趋势看板 + 数据持久化/库表 + 产物存储 + HTML 报告模版，并经两轮交叉审查修订（一致性 / 代码接缝 / 方法论）。下一步二选一：

- **落代码**：从阶段 0 `contracts/` + `models.py` + 单测起，按实现顺序推进。
- **M4 收口**：稳定口径/判据回流 `docs/internals/rag_eval.md`（建议在 M1 跑出首轮真实数字、判据校准后再做）。
