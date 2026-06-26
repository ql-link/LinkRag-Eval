# 评测数据持久化、存储隔离与解耦灌库（权威合并稿）

> 状态：设计稿（`.specs/rag-quality-eval/`，git-ignored）。**本文是评测存储的唯一权威文档**，
> 合并并取代以下三份（均已转 supersede 桩）：
> [eval_ingest_decoupled_design.md](eval_ingest_decoupled_design.md)（解耦灌库）、
> [eval_data_schema.md](eval_data_schema.md)（关系模型）、
> [eval_storage_isolation_design.md](eval_storage_isolation_design.md)（旧镜像方案/方案甲）。
> 上游：[phase0_design.md](phase0_design.md)、[phase1_design.md](phase1_design.md)、
> [trend_dashboard_design.md](trend_dashboard_design.md)、[minio_eval_bucket_design.md](minio_eval_bucket_design.md)。
>
> **一句话**：评测的全部数据足迹（解析产物 + chunk + 召回标识 + 跑分产物）与生产物理隔离；
> 隔离的总杠杆是**评测不运行生产 `ParseTaskPipeline`，只调 core 组件**，数据落**评测自持
> `EvalBase`（默认 SQLite）+ ES/Qdrant 评测 namespace + MinIO 评测桶**。

---

## 一、核心问题与隔离总杠杆

要解决的不是"换一张 chunk 表"，而是：**评测的全部数据足迹不能与生产混放。** 唯一杠杆：

> **评测绝不运行生产 `ParseTaskPipeline`，只调解析/清洗/分块/索引/召回的 core 组件。**
> 正是这条完整管线在写生产的解析簿记表、MinIO、`kb_document_chunk`；跳过它，co-location 整体消失。

各层用组件、数据落评测自持；`user_id/set_id` 不是生产表行，而是召回边界上的**取值**（§七）。

### 1.1 完整数据足迹与隔离落点

| 生产数据足迹 | 生产落点 | 评测要否 | 评测隔离落点 | 隔离机制 |
| --- | --- | --- | --- | --- |
| 源文件 | MinIO 生产桶/上传 | 自带语料 | MinIO 评测桶 / 本地 | 不走上传 |
| **解析簿记**(task/file 状态) | `document_parse_file` 等 MySQL | **否** | — | **跳过 ParseTaskPipeline** |
| 渲染件 / 中间 md | MinIO | 仅清洗层，eval 自渲染 | `eval_cleaning_rendered` + MinIO 评测桶 | 组件 `parse()` 内存产出 |
| ParseResult(md+坐标) | 内存/MinIO | 内存即用 | 不落生产 | `ChunkingEngine` 内存消费 |
| **chunk 真值** | `kb_document_chunk` | 要内容 | `eval_corpus_chunk`（EvalBase） | 组件不入生产库 |
| dense/sparse 向量 | Qdrant `kb_bucket_*` | 要 | Qdrant `eval_kb_bucket_*` | env namespace |
| ES 文本 | `tolink_rag_index` | 要 | ES `tolink_rag_eval_index` | env namespace |
| **召回标识** user_id/set_id/doc_id | 请求值 + payload | 要(边界) | `EVAL_USER_ID` 常量 / dataset_id=set_id / 合成 doc_id | eval 取值，非生产行 |
| llm_user_config(按 user 配模型) | MySQL | 仅 gen/rerank | 系统配置或 eval 配 | Phase1 不触发 |
| run / 指标 / 黄金集 | 文件 | eval 自有 | EvalBase 表 | 本就 eval 侧 |
| 报告 HTML / 冻结 jsonl | 文件/MinIO | eval 自有 | MinIO 评测桶 / `.specs` | blob，不入库 |

两条已验证关键事实：
- **清洗层(Layer 0)已天然解耦**：`cleaning_adapter` 直接 `ParserFactory.get_parser(fmt).parse(Path)->str`
  组件，docstring 明写"不进活栈"，读 eval 自有渲染件、产出 md 仅在内存。
- **`set_id == dataset_id`**（`services.py:296` `set_id = coerce_optional_int(payload.dataset_id)`）。
  评测 dataset_id 本身充当 set_id，非额外要隔离的概念。

**真正共用的只有无状态计算**（BGE-M3 编码服务、召回代码），算力非数据，不构成 co-location。

---

## 二、存储后端：评测自持 `EvalBase`，不进生产 alembic

> **决议**：默认 **SQLite**。理由——① MySQL-同实例的唯一结构优势"跨 schema JOIN 生产 `kb_document_chunk`
> 做 precheck"已随语料移入 `eval_corpus_chunk` 消失；② 评测串行/单人/批处理，用不上 MySQL 的并发多写；
> ③ 本项目 runner 在本地、活栈 DB 在远端生产服务器，"MySQL 单独 schema"现实会落回生产实例、重新沾上
> 共用运维与爆炸半径，违背"不碰生产"原则；④ 冻结语料 + 可复现 run 与"整库一个文件"天然契合。
> MySQL 仅在"团队共享常驻看板/并发/被他服务查询"成为硬需求时启用，且因后端抽象在 `EvalStore` 之后，
> 切换是改配置不改模型；更稳的中间态是 SQLite 夹具 + `eval_metric_result` 导出至共享 MySQL 喂看板。

| 决策 | 取值 | 理由 |
| --- | --- | --- |
| ORM | 独立 `EvalBase`，置 `src/evaluation/store/models.py` | 不在 `src/models/` → 不触发 mysql.md 文档同步、不进生产 alembic、不与生产 metadata 混 |
| 默认后端 | **SQLite 单文件** `.specs/rag-quality-eval/eval.db` | 最大解耦、零基建、可移植、可重建、不碰共享 MySQL |
| 可选后端 | **独立 MySQL schema `linkrag_eval`**（同实例另一 schema） | 团队级趋势看板/CI 共享时启用；仍独立 Base、不进生产 alembic |
| 建表 | `EvalBase.metadata.create_all(engine)`（或独立 eval alembic 链） | 测试库是派生物，可重建，无需迁移仪式 |
| 访问层 | `src/evaluation/store/` 的 `EvalStore`（落地 phase0 `ResultStore` 协议 + 扩展语料/黄金集/指标读写） | 后端可插拔（SQLite/MySQL/文件回退），生产路径零依赖（import-lint 守） |

> **precheck 不再跨生产 schema**：早期设计为 precheck 而主张"MySQL 同实例跨 schema join
> `kb_document_chunk`"。语料移入 `eval_corpus_chunk` 后，precheck 改为在评测库内 JOIN
> `eval_corpus_chunk`，跨生产 schema 的理由消失——这正是 SQLite 默认可行的关键。
> **台账可导出**：需要共享看板时把 `eval_metric_result` 整表导出 MySQL/CSV，夹具与看板解耦。

---

## 三、数据落点结论（存在哪里）

| 数据 | 性质 | 落点 | 理由 |
| --- | --- | --- | --- |
| **评测语料 chunk** | 测试夹具，需正文回填 | **`eval_corpus_chunk`（EvalBase）** | 不入生产 `kb_document_chunk`；组件灌库自持 |
| **黄金集 query** | 结构化 | **`eval_query`** | 取代 golden jsonl 的 query 部分；jsonl 降为冻结导出 |
| **相关性判定 qrel** | 结构化，支持分级 | **`eval_qrel`** | 标准 qrel 行，分级 NDCG 天然支持，precheck JOIN |
| **run / 快照** | 结构化小数据 | **`eval_run`** | 与结果关联、口径可追溯 |
| **指标台账** | 长表、跨轮 | **`eval_metric_result`** | 趋势/回归直接 SQL；替代 DuckDB 台账 |
| **Track B 埋点回定位** | 结构化、可追溯 | **`eval_synth_fact`** | 解析丢失留痕、可复算 |
| **清洗对应关系** | 结构化 | **`eval_cleaning_doc` / `eval_cleaning_rendered`** | 阶段一↔二、跨 run 复现锚点 |
| **报告 HTML / trend.html** | blob | **MinIO 评测桶 / `.specs`** | 渲染件，不可查询 |
| **黄金集冻结 jsonl** | 不可变快照 | **MinIO 评测桶 / `.specs`** | 可复现、可 diff、绑 ingestion 版本 |

---

## 四、表设计（`src/evaluation/store/models.py`，`EvalBase`）

DDL 以 SQLite 语义给出；切 MySQL 独立 schema 时类型平移（BIGINT/JSON/ENUM→VARCHAR+CHECK）。

### 4.1 `eval_dataset` — 语料编目

| 列 | 说明 |
| --- | --- |
| dataset_id INT PK | set_id，号段见 §九 |
| name / source_type | dureader / covid / t2 …；opensource·synth·selfdoc |
| domain / genre / relevance_type | 政策·医疗·电商·通用 / 公文·问答·短文本·长文 / binary·graded |
| batch / ingestion_ref / note / created_at | 引入批次 / 绑 ingestion 快照 / … |

**无 user_id 列**——见 §七。

### 4.2 `eval_corpus_chunk` — 评测语料 chunk（取代复用生产 `kb_document_chunk`）

| 列 | 说明 | vs 生产 |
| --- | --- | --- |
| chunk_id TEXT PK | `uuid5(eval-{dataset}-{doc}-{ordinal})`，与 ES/Qdrant 同一 id 空间 | 生产是 `uuid4`（随机） |
| dataset_id INT | | 替 set_id |
| doc_id INT | passage 数据集=合成 doc | 同 |
| source_passage_id TEXT | 原数据集 pid，可追溯 | **新增** |
| ordinal INT | doc 内序号；passage 恒 0 | ≈ chunk_index |
| content TEXT / content_hash | 正文真值（供回填）/ 指纹 | 同 |
| char_len / token_len INT | 语料画像 | **新增** |
| dense_indexed / sparse_indexed / es_indexed BOOL | 是否已索引 | **简化**：生产是多态状态机 |
| ingest_run_id TEXT / created_at | 复现溯源 | **新增** |

**去掉的生产列**：`lifecycle_status` 状态机、`dense/sparse_vector_model`（配置由 run 快照统一记）、
`bucket_id`（索引时按 `EVAL_USER_ID` 路由 `crc32%bucket_count` 现算）、各 `*_status` 流转字段、
`user_id`。评测不重试、不做生命周期。

> **chunk_id 为何用 uuid5（活栈联调结论，§十二）**：Qdrant `upsert` 用 chunk_id 当 point id、
> 召回又 `chunk_id=str(point.id)` 读回，point id 必须是合法 uint/UUID——生产 `uuid4` 天然合法，
> 评测要确定性（冻结可复现、re-ingest 不变 → qrels 不失效）故用 `uuid5`。人类可读形态
> （`eval-{dataset}-{doc}-{ordinal}`）保留在 `source_passage_id` / `eval_chunk_key()`。

### 4.3 `eval_query` + `eval_qrel` — 黄金集（拆分，取代单表 `eval_golden_sample`）

```
eval_query(
  query_id TEXT PK, primary_dataset_id INT, dataset_ids_json TEXT,
  text TEXT, type ENUM(keyword|paraphrase|longtail|cross_doc),
  golden_answer TEXT NULL, gate_status ENUM(passed|hard_case), note TEXT, created_at )
  -- 无 user_id 列；召回统一用 EVAL_USER_ID（§七）

eval_qrel(
  id PK, query_id TEXT FK, reference_id TEXT, reference_kind ENUM(chunk|doc),
  grade INT,                       -- 二值=1；分级=0–3
  UNIQUE(query_id, reference_id, reference_kind) )
```

把原 `eval_golden_sample` 压平在一行的 `expected_chunk_ids`/`expected_doc_ids`/`relevance_grades`
拆成标准 qrel 行。**好处**：分级 NDCG(ndcg_graded) 天然支持，无需 json 特判；precheck =
`eval_qrel JOIN eval_corpus_chunk` 校验 reference 在库，替代旧"逐 id 查生产 `ChunkRepository`"。
jsonl（GoldenSample schema）保留为**可导入的冻结交换格式**，import 进两表，表为运行时真相。

### 4.4 `eval_run` — 一轮运行 + 配置快照

`run_id TEXT PK, git_sha, dataset_ids_json, layers_json, baseline_run_id NULL, status,
snapshot_json`（完整 `Snapshot` 冻结契约整块存）+ 打平**可索引维度**列（sparse_provider/top_k/
enabled_sources/rrf_k/rerank_top_n/chat·judge·generator_model）供台账过滤，与 snapshot_json 同源。

### 4.5 `eval_metric_result` — 指标长表（替代 DuckDB 台账）

```
eval_metric_result(
  id PK, run_id TEXT FK, layer, metric, k INT NULL,
  relevance_scale ENUM(binary|graded),    -- B4：二值/分级 NDCG 不可比，进主键
  type_bucket,                            -- __all__ / keyword / ...
  value DOUBLE, n INT, n_samples INT DEFAULT 1,
  UNIQUE(run_id, layer, metric, k, relevance_scale, type_bucket) )
```

**联合主键与现有 `filesystem.ledger_rows()` 完全一致——现有 tidy 长表直接落库，零返工。** 配置维度
从 `eval_run` JOIN，不重复打平。趋势/回归直接查本表（同 config 分组），收敛 trend_dashboard 的
DuckDB 台账。可选 `eval_sample_result`（逐样本明细，归因/回归 diff），体量大，Phase 1 后置。

### 4.6 `eval_synth_fact` — Track B 埋点回定位留痕（可选）

`dataset_id, fact_id, statement, anchor, answer, doc_id NULL, located_chunk_ids_json, located BOOL`。
Track B 锚点回定位命中的 chunk 落此，未中=解析丢失计入保真度。**回定位目标从 `kb_document_chunk`
改为 `eval_corpus_chunk`**（§六 reconcile）。

### 4.7 `eval_cleaning_doc` + `eval_cleaning_rendered` — 清洗对应关系（phase0_5 §3）

1:N。`eval_cleaning_doc`（一篇标准 md：dataset/sample_id/source/md_object_key/md_hash）；
`eval_cleaning_rendered`（一个渲染件：doc_fk/format/object_key/file_hash/renderer/renderer_version/
bytes）。阶段二遍历 rendered → 下载 → parser 清洗 → 比对参考 md → 写 `eval_metric_result(layer=cleaning)`。
`md_hash`/`renderer_version` 保证同口径比。渲染件落 MinIO 评测桶（非生产桶）。

---

## 五、解耦灌库 EvalIngestor（复用组件，不走 ParseTaskPipeline）

```
EvalIngestor.ingest_passages(dataset_id, passages, indexer=LiveEvalChunkIndexer()):
  1. assert_namespace()                          # 护栏：ES/Qdrant 名必须含 "eval"
  2. build_indexable(...)                         # Chunk → detached ChunkRecordDB (§5.1)
  3. indexer.index(EVAL_USER_ID, dataset_id, chunks)   # 按 doc 分组，逐 doc：
        dense  : _DecoupledDenseIndexer（系统配置 embedder + eval QdrantIndexStore，§5.3）
        ES     : EsIndexingPipeline(index_name=tolink_rag_eval_index, repo=NoOp).write_es_index
        sparse : SparseIndexingPipeline(repo=NoOp, store=eval).run（BGE-M3 37997）
  4. 落 eval_corpus_chunk (chunk_id, content, …)  # 供 precheck + Phase2/3 正文回填
```

**代码依据**（读穿生产 + 活栈联调确认）：

| 事实 | 出处 / 修正 |
| --- | --- |
| 分块纯函数、不碰 DB | `splitter/chunking_engine.py`：`ChunkingEngine.aprocess(text)->list[Chunk]`，无 `db/session` |
| ⚠️ 索引组件**不是**纯"吃 chunk 对象"——三条路都写 MySQL `chunk_record` 状态 | dense `pipeline.py:206` 按 user 翻 `dense_status`；ES/sparse 经 `ChunkRepository.mark_*`。**评测注入 `NoOpChunkRepository`（mark_* 空操作、返回 `len`）切断这层写**（§5.3） |
| ⚠️ dense 写入按 `user_id` 查 `llm_user_config`、**无系统兜底/注入缝** | `pipeline.py:206` `aresolve_user_chunk_embedding_pipeline(user_id)`。评测改走解耦 dense（§5.3），不依赖共享库模型配置 |
| 召回只打 ES+Qdrant、返回 chunk_id（= point id） | `recall/pipeline.py` 无 `ChunkRecordDB`/`select`；`qdrant_store.py:338` `chunk_id=str(point.id)` |
| 正文回填硬编码读 MySQL、仅 rerank/生成调 | `pipeline/chunk_content.fetch_chunk_contents`（`select(ChunkRecordDB)`） |
| 索引组件可独立实例化（namespace/store/repo 均可注入） | `compose_vector_storage_facade(repository=,bucket_router=)` / `EsIndexingPipeline(index_name=,chunk_repository=)` / `SparseIndexingPipeline(chunk_repository=,qdrant_store=)` |

Phase 1 检索只需索引部分，正文存 `eval_corpus_chunk` 备 Phase 2/3。**活栈 smoke 已验证全链路隔离（§十二）。**

### 5.1 `Chunk → 可索引对象` 适配（唯一真实工作量）

splitter 输出 `Chunk`，索引组件期望带 `chunk_id/content/dense_vector_status/...` 属性的对象
（只读属性、不要求持久化实例）。**推荐路 1**：构造 detached `ChunkRecordDB` 实例（填属性，
**不** add、**不** commit）喂索引组件——复用生产 draft 字段口径、形态贴生产、不落 MySQL。
（路 2：复用 `ChunkDraftFactory` 直接产 draft。）chunk_id/bucket/dataset_id 赋值须走生产
`ChunkDraftFactory` 口径（§八 lockstep）。

### 5.2 正文回填缝 `ChunkContentResolver`（Phase 2/3）

把 `fetch_chunk_contents` 抽象为协议：生产实现=`select(ChunkRecordDB)`（不变）；评测实现=读
`eval_corpus_chunk.content`。注入口在 `RecallPipeline`/rerank 装配处，默认生产实现。**一处注入
替代整张镜像表。** Phase 1 不引入（检索不回填正文）。

### 5.3 `LiveEvalChunkIndexer`：活栈索引适配器（三条路的生产耦合如何拆）

`store/live_indexer.py`。每条生产索引路 = **写索引引擎（ES/Qdrant）** + **翻 MySQL `chunk_record`
状态**。评测要前者、不要后者：

| 副作用 | 隔离手段 |
| --- | --- |
| 写 ES index / Qdrant collection | namespace 配置（`.env.eval`：`tolink_rag_eval_index` / `eval_kb_bucket` / 桶数 16）；dense 与 sparse **都**注入 eval 前缀的 `QdrantIndexStore`（sparse 默认 store 读 `settings` 前缀，不注入会写串生产） |
| 翻 `chunk_record.{dense,sparse,es}_status` | 注入 `NoOpChunkRepository`：`mark_*` 全空操作、返回 `len(chunk_ids)`（满足 dense `rowcount==len` 成功记账）。评测索引状态记在 `eval_corpus_chunk` |
| **dense embedder 按 user 查 `llm_user_config`** | `_DecoupledDenseIndexer`：用**系统配置 embedder**（`create_chunk_embedding_pipeline` → `SYSTEM_LLM_*`）+ eval store，复刻 `embed→indexed_point_from_record→ensure+upsert` 口径，不走生产 `index_chunks` 的 per-user 解析 |
| ES/sparse 直接调 `db.commit()/rollback()` | 喂 `_NullSession`（commit/rollback 空操作），配 NoOp 仓储，既不开真 DB 又不碰生产 MySQL |

逐 doc 顺序 `dense → ES → sparse`；dense 后在内存把 chunk 标 `INDEXED` 以满足 sparse「dense=SUCCESS」
硬前置。ES plan **不走 `Preprocessor`**（它反查生产库），用同一份 `RagFlowTokenizer` 现场构
`FilePostIndexPlan`。ES 写入校验 `EsIndexingResult.is_success`，防 `_ensure_index` 把 400 吞成静默失败。

---

## 六、`user_id` / `set_id`：召回边界上的路由常量，不入表

`user_id` 不是评测对"主链路/鉴权"的依赖，而是**召回组件硬契约 + Qdrant 物理路由键**：

| 位置 | 用法 |
| --- | --- |
| `RecallPipeline._validate` | `user_id > 0` 否则 `RecallValidationError` |
| ES 检索 | `{"term": {"user_id": ...}}` 硬过滤——payload 不带匹配 user_id 即 0 命中 |
| dense/sparse retriever | `user_id <= 0` 校验 + 透传 facade |
| **Qdrant `bucket_router.route_user`** | `crc32(user_id) % bucket_count` 决定 chunk 落/查哪个 collection |

灌库与召回必须用**同一** user_id，否则 ES 过滤空、Qdrant 路由错桶 → 0 命中。彻底去掉需 fork ES
查询 + Qdrant 路由 + retriever 校验 = 放弃口径对齐生产，不可取。**正确姿势——降级为全局常量**：

- 一处定义 `EVAL_USER_ID = 990001`（评测 const / `.env.eval`），注释：**分区/路由 tag，非租户、
  非登录身份、非鉴权、不连 Java 主链路、不读用户业务数据**。
- 评测表（`eval_corpus_chunk`/`eval_query`/`eval_dataset`）**均无 user_id 列**。
- 只出现在两个边界：① 灌库 `Chunk→可索引对象` 填进 ES/Qdrant payload；② 召回
  `RecallRequest(user_id=EVAL_USER_ID)`。
- `set_id == dataset_id`，直接用语料 dataset_id，无第二概念。
- `llm_user_config`（按 user_id+capability 配模型）：**dense 写入侧原本会按 user 解析它**
  （`pipeline.py:206`，无系统兜底）——这是评测对共享库/主链路的隐藏耦合。评测用 `_DecoupledDenseIndexer`
  改走系统配置 embedder（§5.3），dense 不再依赖 990001 的 `llm_user_config`；gen/rerank（Phase 3）
  调模型时另议。检索层 query 编码走系统配置。

---

## 七、护栏

**召回保真 lockstep**（解耦的保真核心，三条硬约束）：
1. **编码器同源**：dense 用系统配置 embedder（qwen `text-embedding-v4`，灌库与召回同源）、sparse 用
   BGE-M3（37997，只产稀疏向量）；`.env.eval` 只改 index/collection 名与桶数，不改编码配置。
2. **索引参数同源**：ES mapping/analyzer、Qdrant 距离度量/维度由同一组件决定，评测只换名字（仅
   `index_name` / collection 前缀），**禁止**手搓 mapping 或 collection 参数。
3. **id 口径同源**：chunk_id（uuid5）/bucket/dataset_id 由 `build_indexable` 统一赋值，dense/sparse/ES
   三路与 qrels 共用同一 chunk_id，否则召回锚点对不上 qrel。

**namespace 安全护栏**：`EvalIngestor` 与 `LiveEvalChunkIndexer` 启动均断言 `ES_INDEX_NAME` 与
`CHUNK_INDEX_COLLECTION_PREFIX` 含 `eval`，否则 `RuntimeError` 拒跑——防止评测语料灌进生产 ES/Qdrant。

**静默失败护栏**：ES `write_es_index` 把建索引 400 / bulk 失败吞成结果对象而非抛异常；
`LiveEvalChunkIndexer` 显式校验 `EsIndexingResult.is_success`，不让"ingest 报成功、实则没进 ES"溜过。

**Qdrant 桶数冻结**：`CHUNK_INDEX_BUCKET_COUNT` 决定路由，灌库与召回同值，一旦灌库不可中途改。

---

## 八、与既有设计 reconcile + 撤回方案甲残留

| 文档 | 原方案 | 本文调整 |
| --- | --- | --- |
| trend_dashboard §三/四 | DuckDB/Parquet 台账 | `eval_metric_result` 表；DuckDB 降为无 DB 备选 |
| phase1 §八 / phase0 ResultStore | snapshot/report → 文件 | snapshot/指标/语料/黄金集 → EvalBase；report/trend(html) → MinIO |
| phase1.5 黄金集 | jsonl 主源 | EvalBase 为工作态主源；jsonl 降冻结导出 |
| **phase1.5 §golden gen / Track B** | **从 `kb_document_chunk` 采样/回定位** | **改从 `eval_corpus_chunk`**（评测语料已自持） |
| **frozen_corpus_tenant** | **语料进 `kb_document_chunk` 靠 user_id=990001 租户隔离** | **语料进 `eval_corpus_chunk`；user_id 是路由常量非租户隔离** |
| minio_eval_bucket | 已是独立 `tolink-rag-eval` 桶 | 不变（与生产桶物理隔离，本就一致） |

**撤回方案甲已落码残留**（P0）：`src/models/eval_chunk_record.py`、`migrations/versions/0020_*`、
`tests/unit/models/test_eval_chunk_parity.py`、`docs/api/schemas/mysql.md` 的 `eval_kb_document_chunk`
章节（表数回 17）、`env.py` 的 `eval_chunk_record` import。`services._reload_chunks_from_db` 的
`model_cls` 化改动可保留待用或随 0020 回退（实现时按 EvalIngestor 是否触达该路径定）。

---

## 九、号段分配（user_id / dataset_id）

| 项 | 值 | 说明 |
| --- | --- | --- |
| `EVAL_USER_ID` | **990001** | 路由常量，非租户 |
| dataset_id Track A（开源通用） | 990101 | DuReader/T2 段落（旧） |
| dataset_id Track B（LLM 合成） | 990102–990105 | PDF/Word/HTML/MD |
| dataset_id 开源垂域批 | 990201–990206 | Covid/T2Retrieval/MLDR-zh/Cmedqa/Medical/Ecom |
| 预留 | 990106–990199 / 990207–990299 | 扩充 |

---

## 十、分期落地

| 期 | 范围 |
| --- | --- |
| **P0 ✅** | 回退方案甲镜像表残留（§八撤回项） |
| **P1 ✅** | `EvalBase` + 检索层表(corpus/query/qrel/run/metric，sample_result 暂缓) + `create_all`；EvalIngestor 写 `eval_corpus_chunk` + `LiveEvalChunkIndexer` 索引 ES/Qdrant（**活栈 smoke 已验证 §十二**）；query/qrel loader；`EvalDbResultStore` 落 run+metric |
| **P1.5** | 6 开源数据集导入；检索评测出报告；Track B 回定位改 `eval_corpus_chunk`。~~前置：召回侧验证~~ **✅ 召回侧已验（§十二.1，bm25+sparse 在 eval namespace 命中）** |
| **P2** | `ChunkContentResolver` 读 `eval_corpus_chunk`；rerank 评测；按需开 `eval_sample_result` |
| **P3** | 生成/judge；清洗层 2 表落库 |
| **可选** | `eval_metric_result` 导出 MySQL/CSV → 团队趋势看板；或整体切独立 MySQL schema `linkrag_eval` |

---

## 十一、完成判据（DoD）

1. `src/evaluation/store/models.py` 定义独立 `EvalBase` 与全部 `eval_*` 表，**不在 `src/models`**、不入生产 alembic。
2. 后端 `create_all` 可起（默认 SQLite，可切独立 MySQL schema）；与生产库表隔离。
3. `EvalStore` 落 `ResultStore` 协议 + 语料/黄金集/指标读写；precheck = `eval_qrel JOIN eval_corpus_chunk`。
4. EvalIngestor 复用组件灌库，不触 `ParseTaskPipeline`、不写生产 MySQL/MinIO；namespace 护栏生效。
   **✅ 活栈 smoke 已验证（§十二）：dense/sparse/ES 三路写进评测 namespace，生产 `kb_document_chunk` Δ=0。**
5. 趋势/回归直接查 `eval_metric_result`；报告 HTML/冻结 jsonl 入 MinIO 评测桶。
6. import-lint 守：生产路径不 import `evaluation/store`；§四治理规则不被触发。

---

## 十二、活栈联调结论（2026-06-19，commit f2f6074）

最小 smoke（`smoke_live_indexer.py`，dataset 990299，3 passage）连远端栈（Qdrant 36333 / ES 39200 /
BGE-M3 37997 @103.205.254.30）端到端跑通，**全绿**：

| 核验 | 结果 |
| --- | --- |
| 生产 `kb_document_chunk` 零新增 | ✅ Δ=0 |
| Qdrant `eval_kb_bucket_9` dense+sparse 点 | ✅ 3 |
| ES `tolink_rag_eval_index` 文档 | ✅ 3 |
| eval.db `eval_corpus_chunk` 落库 | ✅ 3 |

**联调中确认/修正的事实**（已并回 §4.2/§五/§六/§七）：
1. dense 写入耦合 `llm_user_config`（per-user，无系统兜底）→ 加 `_DecoupledDenseIndexer` 解耦缝。
2. chunk_id 必须是合法 Qdrant point id → 确定性 `uuid5`。
3. sparse 默认 store 前缀取 `settings` → 必须显式注入 eval 前缀 store。
4. ES/sparse 直接调 `db.commit/rollback` → `_NullSession` + `NoOpChunkRepository`。
5. ES `write_es_index` 静默吞失败 → 校验 `is_success`。

**顺带修生产潜伏 bug**（`src/core/storage/es/mapping.py`）：ES 强制路由键应为 `_routing`（带下划线），
代码写成 `routing`，新版 ES 建**任何新索引**都 400（`mapper_parsing_exception`）。生产
`tolink_rag_index` 早已存在从不重建故未触发；评测建新索引正好踩到，已修。

**活栈跑测前置**：venv 解释器 + `PYTHONPATH`=worktree + `NLTK_DATA`=主仓库 `nltk_data`（worktree
无 punkt_tab 且本机 SSL 下不动）+ `.env` 连接值。dense 用系统 embedder，**无需** Kafka/MinIO/990001
provision（区别于旧 `CorpusIngestor` 路径）。

### 十二.1 召回侧验证（2026-06-19 补，`smoke_live_recall.py`）

写入侧隔离验完后补的另一段：**生产 `RecallPipeline` 在评测 namespace 命中刚灌的 chunk**。
灌同 3 passage 后用单例 pipeline（`bm25,sparse`）查"新冠疫苗接种禁忌/不良反应"，**全绿**：

| 核验 | 结果 |
| --- | --- |
| 命中全部来自 eval namespace（返回 chunk_id ⊂ eval uuid5 集） | ✅ 2 条均是 |
| 目标 passage（doc 970002）进 top_k 且排第一 | ✅ score 0.0328 |
| bm25 路有命中 | ✅ `per_source={bm25:1}` |
| sparse 路有命中 | ✅ `per_source={sparse:2}` |
| 无失败召回路 | ✅ `failed_sources=[]` |

**召回侧 namespace 怎么隔离的**：召回 retriever 在装配期从 `settings` 读 `ES_INDEX_NAME` /
`CHUNK_INDEX_COLLECTION_PREFIX` / `CHUNK_INDEX_BUCKET_COUNT`，故脚本在**任何 src 导入之前**用
`os.environ` 覆盖到评测值（env 优先级高于 `.env`），写入与召回自然落同一桶（`eval_kb_bucket_9`）。
**dense 召回故意不启用**——`_build_dense_retriever` 仍走 `aresolve_user_chunk_embedding_pipeline`
（写入侧那条 per-user 耦合的召回孪生），990001 无完整 `llm_user_config` 会失败；评测召回口径
本就是 `bm25,sparse`（[[eval-live-run-setup]] 第 6 条），无需再解耦 dense 召回。

> 召回侧若将来要验 dense，需对 `_build_dense_retriever` 也加系统 embedder 解耦缝（与写入侧
> `_DecoupledDenseIndexer` 对称），或给 990001 provision `llm_user_config`。本期不做。
