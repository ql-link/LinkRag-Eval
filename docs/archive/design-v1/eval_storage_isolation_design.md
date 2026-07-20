# 评测专用存储隔离设计（eval storage isolation）

> **归档文档：仅供追溯，不是当前权威依据。** 替代关系见 [归档说明](../README.md)。

> ⚠️ **已废弃（方案甲）。权威设计见 [eval_storage_design.md](eval_storage_design.md)。**
> 本文的「复用整条 `ParseTaskPipeline` + MySQL 镜像表 `eval_kb_document_chunk`」方案已被替换为
> 「不走 ParseTaskPipeline、只调 core 组件 + 评测自持 `EvalBase`（默认 SQLite）」。本文仅作历史
> 背景保留，**勿再据此实现**；语料编目/生命周期/护栏等已迁入权威稿。

> 目标：评测语料的 chunk 真值、ES 索引、Qdrant 向量与**生产存储物理隔离**，不再共用
> `kb_document_chunk` / `tolink_rag_index` / `kb_bucket_*`。原则：**只换存储落点，不 fork
> 管线逻辑**——评测仍走生产的 `ParseTaskPipeline`（写）与 `RecallPipeline`（读），否则就失去
> “评测口径对齐生产”的意义。

---

## 一、隔离三个后端的机制（关键：两个零代码 + 一个新表）

| 后端 | 生产落点 | 评测落点 | 隔离机制 | 是否改生产代码 |
| --- | --- | --- | --- | --- |
| **ES 索引** | `tolink_rag_index` | `tolink_rag_eval_index` | env 覆盖 `ES_INDEX_NAME` | **否** |
| **Qdrant 集合** | `kb_bucket_*`（128 桶） | `eval_kb_bucket_*`（16 桶） | env 覆盖 `CHUNK_INDEX_COLLECTION_PREFIX`（+ `CHUNK_INDEX_BUCKET_COUNT`） | **否** |
| **MySQL chunk 表** | `kb_document_chunk` | `eval_kb_document_chunk` | 新 ORM 模型 + 迁移；写入侧注入 `ChunkRepository(model_cls=...)` | 仅**新增**模型，不改既有逻辑 |

### 1.1 为什么 ES / Qdrant 是零代码

- ES：写入侧 `es/pipeline.py` 与读取侧 `es/retrieval.py` 都是 `index_name or settings.ES_INDEX_NAME`。
  评测进程把 `ES_INDEX_NAME` 设成 `tolink_rag_eval_index`，灌库与召回**同一索引名**，自动对齐。
- Qdrant：`vector/factory.py` 从 `settings.CHUNK_INDEX_COLLECTION_PREFIX` / `CHUNK_INDEX_BUCKET_COUNT`
  造 `BucketRouter`，写入与召回共用同一 facade。改前缀即换一整套集合；评测语料小，桶数调到 16
  即可（生产 128）。两个索引/集合都在**首次写入时自动建**，无需预建。

### 1.2 chunk 表为什么要新表（而非 env 覆盖）

表名写死在 ORM 模型 `ChunkRecordDB.__tablename__`，SQLAlchemy 无法按运行时换表。故新增一个
**字段完全对齐**的并行模型 `EvalChunkRecordDB`（`__tablename__ = "eval_kb_document_chunk"`），
通过既有注入口落到评测表：

- **写入路径基本可注入**：`ParseTaskPipeline.__init__(chunk_repository=None)`、
  `ChunkRepository.__init__(model_cls=ChunkRecordDB)` 都是现成参数。评测灌库这样装配：
  ```python
  ParseTaskPipeline(chunk_repository=ChunkRepository(model_cls=EvalChunkRecordDB))
  ```
  > **一处必要的生产改动（行为不变）**：写入管线 commit 后会**直接 `select(ChunkRecordDB)`**
  > 反查 chunk truth set（`StageServices._load_chunks_by_doc_id`，dense/sparse 阶段依赖它）。
  > 若只注入 repository，写入落评测表但读回查生产表 → 读到空 → 索引拿不到 chunk。故这一处
  > SELECT 改用 `self._chunk_repository.model_cls`（默认 `ChunkRecordDB`，生产语义完全不变）。
  > 这是隔离方案对生产代码的**唯一**改动，仅一行，已被现有 parse_task 单测覆盖。
- **precheck 读取**：评测侧 precheck 属 `src/evaluation`，直接查 `EvalChunkRecordDB`。
- **正文回填**：`pipeline/chunk_content.fetch_chunk_contents` 目前硬引用 `ChunkRecordDB`，仅在
  **rerank（阶段2）/ 生成（阶段3）** 时被调；检索层（阶段1）只用 chunk_id、**不需要正文回填**。
  故本期检索评测无需触碰它，留到阶段2 再引入“chunk 模型解析器”统一处理（见 §五）。

---

## 二、评测存储目录（语料编目）

评测租户沿用 `user_id = 990001`（现在它只是评测表内的逻辑分区，不再污染生产）。按来源各占一个
`set_id`，构成可分类对比的测试语料库：

| dataset_id | 来源 | 垂域 | 体裁 | 相关性 | 批次 |
| --- | --- | --- | --- | --- | --- |
| 990201 | CovidRetrieval | 政策 | 正式公文/通告 | 二值 | 一 |
| 990202 | T2Retrieval | 通用 | 网页段落 | **分级 0-3** | 一 |
| 990203 | MLDR-zh | 通用 | **长文档** | 二值 | 一（待确认 zh 配置） |
| 990204 | CmedqaRetrieval | 医疗 | 社区问答 | 二值 | 二 |
| 990205 | MedicalRetrieval | 医疗 | 诊疗建议 | 二值 | 二 |
| 990206 | EcomRetrieval | 电商 | 商品短文本（关键词 query） | 二值 | 二 |

> 既有的 `990111`（gen 自合成）、`990121`（DuReader）属旧的“共用生产表”阶段产物，本设计落地后
> 评测一律灌进 `eval_kb_document_chunk`；旧数据可保留或清理，不影响生产。

---

## 三、`eval_kb_document_chunk` 表结构

**与 `kb_document_chunk` 字段一一对齐**（保证生产写入路径零改动即可落表）。列：
`chunk_id` / `doc_id` / `set_id` / `user_id` / `chunk_index` / `content` /
`dense_vector_status` / `sparse_vector_status` / `es_status` / `lifecycle_status` /
`bucket_id` / 时间戳等——以 `ChunkRecordDB` 当前列为准，不增不减必填列（保持纯镜像，降风险）。
索引与 `kb_document_chunk` 同（`doc_id`、`set_id+user_id`、`lifecycle_status`）。

> 之所以做纯镜像而非借机加“评测专用列”：写入复用生产管线，多一个必填列就要改生产写入；
> 评测维度（run_id / 数据集来源）已在黄金集与 manifest 侧承载，不必塞进 chunk 表。

---

## 四、生命周期与运维

- **建表**：Alembic 迁移新增 `eval_kb_document_chunk`（生产库内的独立表）。
- **建索引/集合**：首次评测灌库时 ES/Qdrant 自动创建 `tolink_rag_eval_index` / `eval_kb_bucket_*`。
- **灌库**：评测进程加载 `.env.eval`（在 `.env` 基础上覆盖 `ES_INDEX_NAME`、
  `CHUNK_INDEX_COLLECTION_PREFIX`、`CHUNK_INDEX_BUCKET_COUNT`），`CorpusIngestor` 注入
  `EvalChunkRecordDB` 的 repository。
- **清理**：`TRUNCATE eval_kb_document_chunk` + 删评测 ES 索引 + 删 `eval_kb_bucket_*` 集合，
  三者全在评测命名空间内，**绝不触碰生产**。

---

## 五、分期落地

- **本期（检索层隔离，最小集）**：
  1. 新增 `EvalChunkRecordDB` 模型 + Alembic 迁移 + 同步 `docs/api/schemas/mysql.md`（CLAUDE.md §四 机器规则）。
  2. `CorpusIngestor` 增加 `chunk_model` 参数，装配 `ParseTaskPipeline(chunk_repository=ChunkRepository(model_cls=...))`。
  3. 评测 precheck 改读注入的模型（评测侧代码）。
  4. 新增 `.env.eval` 覆盖三个存储名；评测 CLI 加载它。
- **阶段2/3（引入正文回填时）**：新增 `resolve_chunk_model()`（ContextVar，默认 `ChunkRecordDB`），
  把 `chunk_content.fetch_chunk_contents` 等少数直引用点改为经解析器；评测 runner 进入时设置 ContextVar。
  生产默认行为完全不变。

---

## 六、两个设计澄清（评审问题归档）

### 6.1 为什么“纯镜像”，加评测专用列会逼着改生产

评测表虽与生产物理隔离，但**写表的是共用的生产 `ParseTaskPipeline`**，它只认
`kb_document_chunk` 的字段集。给 `eval_kb_document_chunk` 加**非空新列**（如
`source_dataset` / `original_pid` / `ingest_batch`），管线写入时不会填它 → INSERT 失败；
要填就得改生产写入 stage（= 生产适配）。设成可空又永远留空、形同虚设。

故来源/批次/run 这类评测维度一律放在**黄金集 + manifest（评测侧）**承载，chunk 表保持纯镜像，
换取“生产写入零改动”。

### 6.2 user_id 是“分区键 + 模型配置键”，不是登录用户

`user_id` 在系统中身兼两职：① 存储分区（chunk.user_id、Qdrant 按 user_id 分桶、ES 路由、
召回过滤）；② **模型配置主键**——`llm_user_config` 按 `user_id + capability` 存 EMBEDDING/
CHAT/RERANK，`aresolve_user_model(user_id, capability)` 必须以 user_id 取模型。

因此“给测试单独配模型”与“不用 user_id”互斥：要配专属模型就**必须有一个 id 挂这套配置**，
而该 id 在本系统就是 user_id（无登录语义，纯保留号）。弱化 user_id 的两条路都属框架改动、
本期不做：(a) 评测改走 system 预置模型（`allow_system_fallback=True`，但要改写入/召回默认不兜底
的行为）；(b) 给模型配置新增非 user_id 维度（tenant/profile，伤筋动骨）。

**结论**：保留 `user_id=990001` 作纯分区/配置键，最省事、最低风险。

## 七、补充：边界、一致性陷阱、安全护栏、运维（实现必读）

### 7.1 隔离边界（哪些隔离、哪些仍共用）

- **物理隔离**：仅检索关键三件——`eval_kb_document_chunk` / `tolink_rag_eval_index` /
  `eval_kb_bucket_*`。
- **仍共用生产、仅 user_id 逻辑隔离**：parse 任务簿记表（`document_parse_file` /
  `document_parsed_log` / `document_parse_pipeline`）、MinIO 桶（评测对象走 `eval-corpus/` 前缀）。
  这是有意取舍——它们不参与召回，无需物理隔离。**勿误以为“全隔离”**。

### 7.2 三个一致性陷阱

- **Qdrant 桶数必须冻结**：`CHUNK_INDEX_BUCKET_COUNT` 决定 `chunk_id → bucket` 路由，灌库与召回
  必须同值；中途改会让已写向量“找不回”。评测命名空间一旦定（建议 16）即冻结。
- **ID 分配落到评测表**：`CorpusIngestor._resolve_id_base` 须按 `eval_kb_document_chunk` 算
  id base，否则与生产/旧数据撞号。
- **gen 轨采样**：`build_golden gen` 从 chunk 表反向采样，若用于评测数据须注入
  `EvalChunkRecordDB`；opensource 轨（本期主力）不受影响。

### 7.3 安全护栏（防误伤生产）

- env 覆盖是**进程全局**的：生产进程若误带评测 env 会写串库。评测灌库前**断言**
  `ES_INDEX_NAME` 与集合前缀含 `eval` 字样，否则拒写。
- `.env.eval` **不是第二个 pydantic env_file**，而是评测入口在**环境变量**里覆盖
  `ES_INDEX_NAME` / `CHUNK_INDEX_COLLECTION_PREFIX` / `CHUNK_INDEX_BUCKET_COUNT`（沿用
  `VAR=... python ...` 方式），避免与 `.env` 加载机制冲突。

### 7.4 落库与文档同步义务

- 新模型置 `src/models/eval_chunk_record.py`，须被 Alembic `Base.metadata` 收录（autogenerate 可见）。
- 触发 CLAUDE.md §四机器规则：`src/models/**` → 同步 `docs/api/schemas/mysql.md` + 新增
  `migrations/versions/*.py`；**不碰** `migrations/db.sql`（冻结 baseline）；迁移落库后同步
  `scripts/db/init.sql` 快照。
- ES/Qdrant 评测索引/集合**首次写入自动建**，继承生产建索引逻辑（同 mapping/分片、同 1024 维
  Cosine + sparse_text 命名向量），无需预建。

### 7.5 清理要清全

teardown 清单：`TRUNCATE eval_kb_document_chunk` + 删 `tolink_rag_eval_index` + 删
`eval_kb_bucket_*` 集合 + 清评测 user 的 parse 簿记行 + 清 MinIO `eval-corpus/` 对象。

---

## 八、待定决策

1. ~~评测租户 user_id~~ → 见 §6.2，保留 990001。
2. ~~表结构~~ → 见 §6.1，纯镜像。
3. Qdrant 评测桶数取 16 还是 32（语料量决定；500–3000 段用 16 足够，建议 16 并冻结）。
4. MLDR 中文长文档集需先确认 HF 上的 zh 配置是否可用，再决定 990203 是否启用。
