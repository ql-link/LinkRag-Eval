# 冻结评测语料 / 租户（R2）— id 与范围决议

> **归档文档：仅供追溯，不是当前权威依据。** 替代关系见 [归档说明](../README.md)。

> 状态：已决议（阶段 0 DoD#5 交付物）
> 上游：[phase0_design.md §六.4](phase0_design.md)、[technical_design.md §七.2](technical_design.md)、构建策略 [phase1_5_golden_gen_design.md §二](phase1_5_golden_gen_design.md)
> 性质：非代码交付物。本文档定准号段与语料范围；实际灌数与阶段 1 并行执行。
>
> ⚠️ **存储口径已更新（权威见 [eval_storage_design.md](eval_storage_design.md)）**：评测语料**不再复用生产
> `kb_document_chunk`、不靠 `user_id` 做租户隔离**，而是评测自持 `eval_corpus_chunk`（`EvalBase`）+
> ES/Qdrant 评测 namespace。`user_id=990001` 降级为**召回边界路由常量 `EVAL_USER_ID`**（ES term
> 过滤 + Qdrant `crc32(user_id)` 桶路由所需），**非租户、非鉴权身份**。下列号段分配仍有效。

---

## 一、标识号段（保留号段）

`user_id` / `dataset_id` 是 Java 业务侧分配的 BigInt 标识；评测侧固定保留号段、与生产 id 空间隔离。
评测语料不入生产表，下列 id 仅作**召回边界取值**（user_id=路由常量、dataset_id=set_id）：

| 项 | 值 | 说明 |
| --- | --- | --- |
| `EVAL_USER_ID` | **990001** | 召回路由/分区常量（非租户、非登录身份）；99xxxx 段生产不得占用 |
| Track A `dataset_id` | **990101** | 开源通用文档（DuReader_retrieval / T2Ranking 段落） |
| Track B `dataset_id` | **990102 – 990105** | LLM 合成真实格式文档：990102=PDF、990103=Word、990104=HTML、990105=Markdown |
| 开源垂域批 `dataset_id` | **990201 – 990206** | Covid/T2Retrieval/MLDR-zh/Cmedqa/Medical/Ecom（见权威稿 §九） |
| 预留扩展 | 990106 – 990199 / 990207 – 990299 | 未来语料扩充 |

阶段 1 的 `EvalRequest` / 黄金集样本中的 `user_id` 取 `EVAL_USER_ID`、`dataset_ids` 取上表值；
适配器以该 user_id 调 `get_recall_pipeline()`。

## 二、语料范围（灌什么）

按 phase1.5 §2.2 覆盖维度执行，中等规模（几百篇文档 → 数千 chunk）：

- **来源一（主力，→ 990101）**：DuReader_retrieval / T2Ranking 段落，doc 粒度支撑检索/重排评测。
- **来源二（补全链路，→ 990102–990105）**：LLM 合成带表格/多级标题/图文的真实格式文档，覆盖 parser + chunker 全链路（Track B，见 [phase1_5_trackB_llm_corpus_design.md](phase1_5_trackB_llm_corpus_design.md)）。

结构覆盖：长文 / 短文 / 表格密集 / 图文混排 / 多级标题，每类至少有可分层抽样的样本量。

## 三、冻结与隔离纪律

1. **只读冻结**：语料经 EvalIngestor（复用生产同一 parser/chunker 组件、同分块策略，但不走
   `ParseTaskPipeline`）一次性灌定后冻结；任何重灌 / 换分块策略都使既有 qrel 的 `chunk_id` reference
   失效，须走阶段 1 `loader.precheck`（`eval_qrel JOIN eval_corpus_chunk`）重校验。
2. **绑定 ingestion 快照**：灌数完成后记录灌库时间、git sha、parser/chunker 配置（落 `eval_run` /
   `eval_dataset.ingestion_ref`），黄金集与该快照绑定。
3. **与生产隔离**：评测语料进**评测自持 `eval_corpus_chunk`（EvalBase）+ ES/Qdrant 评测 namespace +
   MinIO 评测桶**，完全不进生产 `kb_document_chunk` / 生产索引 / 生产桶；`EVAL_USER_ID=990001` 仅作
   召回路由常量。生产侧无需为评测排除号段（数据物理不在生产库）。
4. **预置模型配置**：gen/rerank 评测须配可用 CHAT / RERANK 模型（`llm_user_config`，阶段 2/3 依赖）；
   检索层 query 编码走系统配置、不依赖 user 配置；三模型错配纪律见 phase3 §八。

## 四、执行状态

- [x] 租户 id 与号段决议（本文档，阶段 0）
- [ ] 评测租户模型配置预置（阶段 1 前置）
- [ ] Track A 开源文档灌库（与阶段 1 并行）
- [ ] Track B 合成文档灌库（与阶段 1.5 并行）
- [ ] ingestion 快照记录（灌数完成后回填 §五）

## 五、ingestion 快照记录（灌数后回填）

| 灌库批次 | 日期 | git sha | parser provider | 分块策略 | 文档数 / chunk 数 |
| --- | --- | --- | --- | --- | --- |
| （待灌数后回填） | | | | | |
