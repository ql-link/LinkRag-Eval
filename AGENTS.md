# LinkRag-Eval 实现约定

`LinkRag-Eval` 是从生产 RAG 仓库(toLink-Rag)剥离的**独立评测/质检项目**。它只通过"产物级纯函数"复用生产计算能力,自己负责入库、检索、算分,使用独立 Postgres + eval 独立前缀的 Qdrant collection。

本文件是 Agent / 开发者的**强制规范**。总方案见 [docs/architecture/decoupling-plan.md](docs/architecture/decoupling-plan.md);历史设计见 [docs/design/](docs/design/);实证报告见 [docs/reports/](docs/reports/)。

> 当前阶段:仓库承载文档与约定。代码按 [迁移路径](docs/architecture/decoupling-plan.md#分步迁移路径每步可验证基线-recall10--0901) 的 Step 0–4 先在源仓库 `src/evaluation/` 内迭代,Step 5 用 `git filter-repo` 物理迁入本 repo。

---

## 一、命名约定

| 项 | 取值 |
| --- | --- |
| 仓库名 | `LinkRag-Eval` |
| Python 包 | `linkrag_eval`(`src/linkrag_eval/`,src-layout) |
| CLI 入口 | `linkrag-eval`(`linkrag_eval.cli:main`) |
| 生产依赖包 | `toLink-Rag`(import 名 `src.*`,通过 path/git 依赖装入) |
| 环境变量前缀 | `EVAL_`(judge 用 `EVAL_JUDGE_*`) |
| 配置文件 | `.env.eval`(gitignored,绝不进版本库) |
| Qdrant 前缀 | 必须含 `eval`(如 `eval_kb_bucket`) |
| Postgres 库 | eval 独立实例,DSN 经 `EVAL_PG_DSN` |

---

## 二、仓库目录结构(最终形态)

```
LinkRag-Eval/
├── AGENTS.md                  # 本文件(实现约定)
├── CLAUDE.md                  # → AGENTS.md 的 symlink(物理同一份)
├── README.md                  # 项目入口
├── pyproject.toml             # src-layout;rag 钉版本依赖
├── .env.eval.example          # 配置样例(真值进 .env.eval,gitignored)
├── .gitignore
├── docs/
│   ├── architecture/          # 权威架构(decoupling-plan / dependency-boundary / storage)
│   ├── design/                # 迁移自源仓库的历史设计(monorepo 时期)
│   └── reports/               # 历史评测实证发现
├── src/linkrag_eval/
│   ├── compute/               # 产物计算封装(唯一允许 import rag 的地方)
│   ├── store/                 # 独立存储(EvalVectorStore + Postgres repo)
│   ├── retrieval/             # 召回装配(注入 eval 前缀)
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
│   └── integration/           # 真实活栈 smoke(连远端 Qdrant/PG)
└── scripts/                   # ingest / run / report 驱动脚本
```

---

## 三、依赖边界(机器强制,最高优先级)

这是本项目存在的理由。**任何违反都视为破坏解耦**,由 import-lint 在 CI 拦截。

### 白名单 — 允许 import 的 rag 模块

| 类别 | 模块 |
| --- | --- |
| 纯计算 | `ChunkingEngine.aprocess`、`create_chunk_embedding_pipeline`/`aembed_chunks`、`SparseVectorService.vectorize_texts`、`RagFlowTokenizer.tokenize` |
| Qdrant 原语 | `QdrantIndexStore`、`BucketRouter`、`point_factory`、`qdrant.models`(复用 schema,自己装配 writer) |
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

- **rag 的 import 只允许出现在 `compute/rag_adapter.py` 与 `retrieval/recall_factory.py` 两个文件**。其余模块依赖 `compute/protocol.py` 的抽象。
- 新增对 rag 的任何 import,必须先问:这是纯计算 / 被测对象吗?能否走 `ProductComputer` 抽象?默认答案是"走抽象"。

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
- 复用 rag 的 `QdrantIndexStore` + `BucketRouter`,named vectors:`dense` / `sparse` /(预留)`bm25`。
- **`chunk_id` 用 uuid5 确定性**:`uuid5(NAMESPACE_DNS, f"tolink-eval:eval-{dataset_id}-{doc_id}-{ordinal}")`。同输入恒等 → 冻结语料 re-ingest 不变 → qrels 不失效;dense/sparse/bm25 三路与 qrels 共用同一 id。
- 写入侧 `compute_dense` 与召回侧 query embedding resolver **必须用同一系统 embedder**(硬约束,见方案风险 C)。

### Postgres(eval 自持元数据/结果)

- `EvalBase` 六表迁 PG:`eval_dataset` / `eval_corpus_chunk` / `eval_query` / `eval_qrel` / `eval_run` / `eval_metric_result`。
- `_AutoPK` 改纯 `BigInteger`;枚举字段保持 `String + 注释`(改值不需 migration)。
- 字段变更:`eval_corpus_chunk.es_indexed` → `bm25_indexed`;`eval_run` 增 `computer_fingerprint`。
- Schema 演进唯一入口是 `alembic/`(eval 自己的迁移链,与生产 alembic 完全隔离)。

---

## 六、配置约定

- 所有运行时配置经 `linkrag_eval/config.py` 加载,**不 import `src.config`**。
- 环境变量样例放 `.env.eval.example`;真值放 `.env.eval`(gitignored)。
- 关键变量:`EVAL_QDRANT_HOST/PREFIX/BUCKET_COUNT`、`EVAL_PG_DSN`、`EVAL_JUDGE_BASE_URL/API_KEY/MODEL`、系统 embedder 端点。
- **`EVAL_USER_ID=990001` 是 routing/partition 常量,不是真实用户**;只用于 bucket 路由,不得据此查 `llm_user_config`。

---

## 七、rag 包依赖管理

- `pyproject.toml` 把 toLink-Rag 声明为 path/git 依赖,**钉 git sha 或版本**;升级走 PR。
- 每次升级 rag,CI 先跑 `tests/contract/` —— 对每个 `ProductComputer` 方法断言输出形状/维度。红 = 签名漂移,只在 `compute/rag_adapter.py` 一处修。
- 不得为了"图省事"绕过抽象直接 import rag 内部实现;漂移成本会扩散到全仓。

---

## 八、测试约定

| 层 | 目录 | 依赖 | 跑法 |
| --- | --- | --- | --- |
| 单元 | `tests/unit/` | 注入 fake,零活栈 | 默认 CI |
| 契约 | `tests/contract/` | 真 rag 包,无远端 | rag 升级 / 默认 CI |
| 集成 | `tests/integration/` | 真 Qdrant/PG/embedder | 手动 / nightly,需 `.env.eval` |
| import-lint | `tests/` | — | 断言黑名单零命中 |

- 每个迁移步骤(Step 0–6)以 `recall@10 ≈ 0.901`(±0.005)为**等价门槛**,固定数据集重灌后对比。
- 集成测试连远端栈,标 marker 跳过默认 CI。

---

## 九、安全与隔离纪律(不可妥协)

- `api_key` 只写入本地 `.env.eval`(gitignored),**绝不打印到终端、绝不进版本库**。
- 评测**只读**生产 DB(若需);**绝不写共享 MySQL**。索引状态记在 eval 自己的 Postgres。
- `.env.eval`、`golden/`、`.specs/` 等含数据/密钥的产物 gitignored。
- Qdrant 前缀护栏(第五节)是写串生产的最后一道防线,不得删除或绕过。

---

## 十、分支 / 提交 / PR

- 主分支 `master`。功能分支从 `master` 切,`feat/` `fix/` `docs/` `refactor/` 前缀。
- 提交信息中文为主,首行 `type(scope): 摘要`(沿用源仓库惯例)。
- 改动后同步受影响文档;`docs/architecture/` 是权威,`docs/design/` 是历史(monorepo 时期,存储/灌库部分已被 decoupling-plan 取代,引用时注明)。
- 不主动 commit/push,除非用户明确要求。

---

## 十一、回答风格(面向开发者沟通)

- 语言清晰、专业、得体;不过度口语化,也不堆砌术语。
- 少用生僻术语和生造比喻;确需专业术语时用一句话点明含义。
- 先给结论,再讲原因;结构清楚,长短结合。
- 目标:读起来顺畅、专业,又不让人被术语挡住。
