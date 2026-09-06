# LinkRag-Eval 实现约定

`LinkRag-Eval` 是从生产 RAG 仓库(toLink-Rag)剥离的**独立评测/质检项目**。它只通过"产物级纯函数"复用生产计算能力,自己负责入库、检索、算分,使用本地 SQLite `runs/linkrag_eval.sqlite3` + eval 独立前缀的 Qdrant collection。

本文件是 Agent / 开发者的**强制规范**。总方案见 [docs/architecture/decoupling-plan.md](docs/architecture/decoupling-plan.md);当前进度见 [docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md);历史设计见 [docs/archive/](docs/archive/);实证报告见 [docs/reports/](docs/reports/)。

> 当前阶段以 [docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md) 为唯一进度入口，避免在规则文档中重复维护易过期的实验状态。

研究材料的使用身份见 [文档目录](docs/DOCUMENT_CATALOG.md)。本次[重构执行记录](docs/plans/research-restructure-execution-2026-09-06.md)记录实际变更与验证；原 Robust Fusion、R1／R2、Gate、相似度和人工仲裁协议退出活动执行身份，原文仍按[历史导航](docs/archive/robust-fusion/README.md)保留原路径及字节。不得仅因旧正文含“唯一下一步”或自动执行指令而恢复流程。

当前研究边界是三路召回后的固定候选集合，利用已有可见候选信息与逐路分数／排名探索融合或重排；不回原文补信息，不改召回。具体方法、阈值、窗口与实验版本保持暂定，不能从讨论稿推定为实现要求。人工作业以 `human_tasks/registry.json` 为当前登记，使用 `scripts/check_human_task_entrypoints.py` 校验；旧 registry、HTML、symlink 和提交保留作历史，不表示活动任务。

重构前源码标签为 `research-pre-restructure-20260906`（`4d31f18`）；需要追溯时在独立目录恢复核对，避免覆盖当前工作区。Git 忽略的证据通过独立备份及 manifest 恢复，具体范围见执行记录，不能把未跟踪或被忽略视为删除依据。

---

## 一、命名约定

| 项 | 取值 |
| --- | --- |
| 仓库名 | `LinkRag-Eval` |
| Python 包 | `linkrag_eval`(**src-layout**,包在 `src/linkrag_eval/`;包名是 `linkrag_eval`,**不是** `src`) |
| CLI 入口 | `linkrag-eval`(`linkrag_eval.cli:main`) |
| 生产依赖包 | `toLink-Rag`(import 名 `src.*`,通过 path/git 依赖装入) |
| 环境变量前缀 | `EVAL_`(judge 用 `EVAL_JUDGE_*`) |
| 配置文件 | `.env.eval`(gitignored,绝不进版本库) |
| Qdrant 前缀 | 必须含 `eval`(如 `eval_kb_bucket`) |
| 元数据/结果库 | 本地 SQLite `runs/linkrag_eval.sqlite3`(`EVAL_DB_URL`) |

---

## 二、仓库目录结构(最终形态)

> **为什么 src-layout 但包名不是 `src`**:src-layout 规范指"包放进 `src/` 文件夹",包名不变——`src/` 只是外层目录、本身不是包(无 `__init__.py`),import 仍是 `from linkrag_eval.x`。**包名绝不能叫 `src`**:toLink-Rag 自身打成名为 `src` 的顶层包(`import src.core`),若本项目包也叫 `src`,两个顶层 `src` 在 sys.path 互相遮蔽、无法同时 import,而 eval 必须 import rag。故采 src-layout + 包名 `linkrag_eval`。

```
LinkRag-Eval/
├── AGENTS.md                  # 本文件(实现约定)
├── CLAUDE.md                  # → AGENTS.md 的 symlink(物理同一份)
├── README.md                  # 项目入口
├── pyproject.toml             # src-layout;rag 单独显式安装,CI 固定 SHA(见第七节)
├── .importlinter              # 依赖边界机器规则(第三节)
├── .env.eval.example          # 配置样例(真值进 .env.eval,gitignored)
├── .gitignore
├── docs/
│   ├── architecture/          # 权威架构(decoupling-plan / dependency-boundary / storage)
│   ├── plans/                 # 方案、暂定讨论及保留原路径的旧协议(身份见文档目录)
│   ├── experiments/           # 已验证实验和候选方案
│   ├── reports/               # 当前与历史评测实证
│   └── archive/               # 历史设计及原协议导航
├── human_tasks/               # 当前人工任务登记与历史入口(保留不等于活动)
├── src/linkrag_eval/          # ← src-layout:包在此,import 仍 `from linkrag_eval.x`
│   ├── compute/               # 产物计算封装(本目录内仅 rag_adapter 允许 import rag)
│   ├── store/                 # 独立存储(EvalVectorStore + 本地 SQLite repo)
│   ├── retrieval/             # 召回装配(recall_factory 注入 eval 前缀)
│   ├── metrics/               # 指标(纯函数)
│   ├── golden/                # golden 生成 / 编目
│   ├── judge/                 # eval_llm(judge,已解耦)
│   ├── contracts/ runners/ reporters/
│   ├── config.py              # eval 独立配置(不 import src.config)
│   └── cli.py
├── alembic/                   # eval 自己的迁移(EvalBase.metadata)
├── tests/
│   ├── unit/                  # 纯核心(注入 fake,零活栈)
│   ├── contract/              # rag 纯函数契约测试(防签名漂移)
│   └── integration/           # 真实活栈 smoke(本地 SQLite + 远端 Qdrant/embedder)
└── scripts/                   # ingest / run / report 驱动脚本
```

---

## 三、依赖边界(机器强制,最高优先级)

这是本项目存在的理由。**任何违反都视为破坏解耦**,由 import-lint 在 CI 拦截。

### 白名单 — 允许 import 的 rag 模块

| 类别 | 模块 |
| --- | --- |
| 纯计算 | `ChunkingEngine.aprocess`(chunk 切分)、`RagFlowTokenizer.tokenize`(bm25 分词)。**dense/sparse 已移到 eval `llm/` 模块,不再经 rag** |
| Qdrant 原语 | `QdrantIndexStore`、point 模型、`qdrant.models`(复用 schema,自己装配 writer；显式指定 eval collection) |
| 被测对象 | `RecallPipeline`、`Retriever`、`compose_vector_storage_facade`、`DenseRetriever`、`SparseRetriever`、`ParserFactory` |
| 纯 dataclass | `recall.models.*`、`preprocessor.models.*`(ChunkWithTokens 等) |

### 黑名单 — 禁止 import(zero tolerance)

- 三个"算+写绑死"的写 pipeline:`EsIndexingPipeline`、`SparseIndexingPipeline`、`VectorStoragePipeline`
- `src.models.*` 任何写 ORM(`ChunkRecordDB`/`DocumentParseTask` 等)
- `ParseTaskPipeline`(全栈解析)、`StorageFactory`(MinIO)、MQ producer
- `src.config.settings`(用本项目 `config.py`)
- `aresolve_user_*` / `ChunkRepository`(per-user 配置解析,会拖回共享库)
- 整条 `src.core.storage.es`(对齐"目标态无 ES")

### 收口原则

- **rag 的 import 只允许出现在这几个 adapter 文件**,按关注点:
  - `compute/rag_adapter.py` —— 纯计算(chunk 切分 + bm25 分词;dense/sparse 走 eval llm)
  - `store/vector_store.py` —— Qdrant 原语(`QdrantIndexStore`/point 模型；bucket 在 eval 内计算)
  - `retrieval/recall_factory.py` —— 召回装配(被测对象 `RecallPipeline`,指向 eval 前缀)
  - `retrieval/recall_adapter.py` —— `RecallRequest`/`RecallResponse` marshalling(被测对象类型)
  其余模块依赖 `compute/protocol.py` 的抽象。
- 新增对 rag 的任何 import,必须先问:这是纯计算 / 被测对象 / Qdrant 原语吗?能否走抽象?默认答案是"走抽象"。允许的 adapter 文件清单由 `tests/test_import_boundary.py` 强制。

---

## 四、ProductComputer 契约

产物计算抽象成接口,默认实现 `RagProductComputer` 是唯一碰 rag 纯函数的类。方法:

```python
class ProductComputer(Protocol):
    async def compute_chunks(self, text: str, *, source_file: str | None = None) -> list[EvalChunk]: ...
    async def compute_dense(self, contents: Sequence[str]) -> list[DenseVec]: ...
    async def compute_sparse(self, contents: Sequence[str]) -> list[SparseVec]: ...
    def       compute_bm25_tokens(self, content: str) -> Bm25Tokens: ...
    @property
    def dense_dim(self) -> int: ...        # 建 collection 用
    @property
    def fingerprint(self) -> dict: ...      # 模型名/版本,写入 EvalRun 快照
```

- 所有 `compute_*` **纯计算**:输入文本/chunk,输出向量/token,**不写任何存储**。
- 测试注入 `FakeProductComputer`;契约测试用固定输入断言输出形状/维度。
- `fingerprint` 必须如实反映 dense 模型、sparse provider、bm25 mode,供偏差标注。

---

## 五、存储约定

### Qdrant(eval 独立前缀,同 host)

- **护栏(强制)**:`EvalVectorStore` 构造时断言 collection 前缀含 `eval`,否则抛 `RuntimeError` 拒跑。防写串生产。
- 复用 rag 的 `QdrantIndexStore`，在 eval 内计算 bucket 并显式指定 `{prefix}_{bucket_id}` collection，不依赖生产 `BucketRouter`。向量 schema 与固定版本的生产原语对齐；Sparse 名由 eval 配置提供，默认 `sparse_text`，写入与召回必须一致。
- **`chunk_id` 用 uuid5 确定性**:`uuid5(NAMESPACE_DNS, f"tolink-eval:eval-{dataset_id}-{doc_id}-{ordinal}")`。同输入恒等 → 冻结语料 re-ingest 不变 → qrels 不失效;dense/sparse/bm25 三路与 qrels 共用同一 id。
- **dense/sparse 均由 eval `llm/` 模块承载**(config 驱动,`EVAL_EMBED_*` / `EVAL_SPARSE_*`,模型可选),不经 rag。写入侧 `compute_dense` 与召回侧 query 编码 **必须用同一 eval dense 编码器口径**(硬约束,见方案风险 C);否则 eval 内部向量空间不一致。

### SQLite(eval 自持元数据/结果,本地单文件)

- 默认 `EVAL_DB_URL=sqlite+aiosqlite:///runs/linkrag_eval.sqlite3`。正常评测禁止依赖远端 MySQL，数据库文件 gitignored。
- 旧 `tolink_rag_eval_db` 只允许作为一次性只读迁移源；迁移工具必须校验库名并逐表核对计数与内容摘要，绝不读取或写入生产 `tolink_rag_db`。
- `EvalBase` 六表:`eval_dataset` / `eval_corpus_chunk` / `eval_query` / `eval_qrel` / `eval_run` / `eval_metric_result`。
- `_AutoPK` 在 SQLite 使用 `Integer` 自增、旧 MySQL 迁移源使用 `BigInteger`;枚举字段保持 `String + 注释`(改值不需 migration)。
- 字段变更:`eval_corpus_chunk.es_indexed` → `bm25_indexed`;`eval_run` 增 `computer_fingerprint`。
- Schema 演进唯一入口是 `alembic/`(eval 自己的迁移链,与生产 alembic 完全隔离)。
- BM25 使用 eval 自持 SQLite FTS5 sidecar；`bm25_mode=sqlite_fts5` 启用第三路，`stub` 仅装配 Dense／Sparse。旧 `qdrant_bm25` 模式不再支持，不得用 Sparse 结果伪装 BM25。

---

## 六、配置约定

- 所有运行时配置经 `linkrag_eval/config.py` 加载,**不 import `src.config`**。
- 环境变量样例放 `.env.eval.example`;真值放 `.env.eval`(gitignored)。
- 关键变量:`EVAL_QDRANT_HOST/PREFIX/BUCKET_COUNT`、`EVAL_DB_URL`(本地 SQLite)、`EVAL_SPARSE_*`、`EVAL_JUDGE_BASE_URL/API_KEY/MODEL`、系统 embedder 端点。
- **`EVAL_USER_ID=990001` 是 routing/partition 常量,不是真实用户**;只用于 bucket 路由,不得据此查 `llm_user_config`。

---

## 七、rag 包依赖管理

- toLink-Rag 当前不在 `pyproject.toml` 的 dependencies 中，须单独显式安装；精确 SHA 由 CI 安装步骤固定，并在 pyproject 注释中记录。普通 `pip install .` 不会自动安装或固定 rag；本地契约验证须核对所装版本，升级走 PR。
- 每次升级 rag,CI 先跑 `tests/contract/` —— 验证计算产物与被测对象契约。签名漂移在负责该能力的 adapter 收口，不扩散生产 import。
- 不得为了"图省事"绕过抽象直接 import rag 内部实现;漂移成本会扩散到全仓。

---

## 八、测试约定

| 层 | 目录 | 依赖 | 跑法 |
| --- | --- | --- | --- |
| 单元 | `tests/unit/` | 注入 fake,零活栈 | 默认 CI |
| 契约 | `tests/contract/` | 真 rag 包,无远端 | rag 升级 / 默认 CI |
| 集成 | `tests/integration/` | 本地 SQLite + 真 Qdrant/embedder | 手动 / nightly,需 `.env.eval` |
| import-lint | `tests/` | — | 断言黑名单零命中 |

- 原 Step 0–6 的 `recall@10 ≈ 0.901`(±0.005)只对应历史固定语料的迁移等价参考；不作为新数据或新研究的统一验收门槛。当前变更运行与其影响范围相符的检查。
- 集成测试连远端栈,标 marker 跳过默认 CI。

---

## 九、安全与隔离纪律(不可妥协)

- `api_key` 只写入本地 `.env.eval`(gitignored),**绝不打印到终端、绝不进版本库**。
- 元数据和结果只写本地 SQLite。**绝不写生产库 `tolink_rag_db` 的任何表**；旧 eval MySQL 也仅允许迁移工具只读访问。
- `.env.eval`、`golden/`、`.specs/` 等含数据/密钥的产物 gitignored。
- Qdrant 前缀护栏(第五节)是写串生产的最后一道防线,不得删除或绕过。

---

## 十、分支 / 提交 / PR

- 主分支 `master`。功能分支从 `master` 切,`feat/` `fix/` `docs/` `refactor/` 前缀。
- 提交信息中文为主,首行 `type(scope): 摘要`(沿用源仓库惯例)。
- 改动后同步受影响文档;`docs/architecture/` 是权威,项目级进度只更新 `docs/CURRENT_STATUS.md`,`docs/archive/` 仅作历史追溯。
- 不主动 commit/push,除非用户明确要求。

---

## 十一、回答风格(面向开发者沟通)

- 语言清晰、专业、得体;不过度口语化,也不堆砌术语。
- 少用生僻术语和生造比喻;确需专业术语时用一句话点明含义。
- 先给结论,再讲原因;结构清楚,长短结合。
- 目标:读起来顺畅、专业,又不让人被术语挡住。
