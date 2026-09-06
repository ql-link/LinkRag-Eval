# LinkRag-Eval 解耦架构

本文件说明当前工程边界与组件职责；强制规则见 [AGENTS.md](../../AGENTS.md)，实施进度和待办只在 [CURRENT_STATUS.md](../CURRENT_STATUS.md) 维护。旧 Step 0–6 的迁移计划已成为历史，不再作为本次研究的执行清单。重构范围和版本记录见[执行记录](../plans/research-restructure-execution-2026-09-06.md)。

## 项目边界

LinkRag-Eval 是独立评测／质检项目。它复用 toLink-Rag 的纯计算、检索被测对象和 Qdrant 原语，自己负责数据、入库、召回装配、评测与报告。元数据和结果使用本地 SQLite；向量使用含 `eval` 前缀的独立 collection。不得调用生产写 pipeline、生产 ORM、per-user 配置解析、MinIO 或 MQ 来完成评测。

包使用 src-layout：文件位于 `src/linkrag_eval/`，import 为 `linkrag_eval.*`。外层 `src/` 不是本项目包，避免与生产的顶层 `src.*` 包遮蔽。

## 产物计算与依赖收口

| 能力 | 实现与边界 |
| --- | --- |
| chunk 切分 | 经 `compute/rag_adapter.py` 复用 `ChunkingEngine.aprocess` |
| BM25 分词 | 经同一 adapter 复用 `RagFlowTokenizer.tokenize` |
| Dense／Learned Sparse 编码 | 使用 eval 自持 `llm/` 编码器，按 `EVAL_EMBED_*`／`EVAL_SPARSE_*` 配置，不读取生产用户配置 |
| 向量存储 | `store/vector_store.py` 复用 `QdrantIndexStore` 和 point 模型，显式指定 eval collection |
| 检索装配 | `retrieval/recall_factory.py` 复用 `RecallPipeline`、Dense／Sparse Retriever 及 storage facade，注入 eval 存储和编码器 |
| 请求／响应适配 | `retrieval/recall_adapter.py` 转换生产被测对象类型 |

生产 import 只允许出现在上述四个 adapter 文件，其他模块依赖 eval 抽象；具体白名单和黑名单由 AGENTS、import-lint 与 `tests/test_import_boundary.py` 约束。

`ProductComputer` 定义 `compute_chunks`、`compute_dense`、`compute_sparse`、`compute_bm25_tokens`、`dense_dim` 和 `fingerprint`。计算方法只产出 chunk／向量／token，不写存储。测试可注入 fake；契约测试验证真实依赖的接口。写入侧与 query 侧须使用同一编码口径，快照记录模型与配置指纹。

## 独立存储

`EvalVectorStore` 校验前缀包含 `eval`，并在 eval 内按固定 routing 常量计算 bucket，显式构造 `{prefix}_{bucket_id}` collection 名。它不依赖生产 `BucketRouter` 或用户表。向量 schema 与固定版本的生产 Qdrant 原语保持一致，Sparse 名由 eval 配置提供，默认 `sparse_text`；写入与召回必须使用相同名称和编码口径。

chunk ID 使用 `uuid5(NAMESPACE_DNS, f"tolink-eval:eval-{dataset_id}-{doc_id}-{ordinal}")`，固定数据、文档和 ordinal 产生相同 ID，三路候选与 qrels 共用该 ID。确定性 ID 本身不保证语料正文未变，复现实验仍需核对输入快照。

`EvalCorpusRepo` 与结果台账使用 `runs/linkrag_eval.sqlite3`。`EvalBase` 包含 `eval_dataset`、`eval_corpus_chunk`、`eval_query`、`eval_qrel`、`eval_run`、`eval_metric_result` 六表；schema 演进经仓库根目录 `alembic/` 完成，与生产迁移隔离。正常评测不依赖远端 MySQL；旧 eval MySQL 只允许由专用迁移工具只读核对，禁止访问生产库。

BM25 由 eval 的 SQLite FTS5 sidecar 承载，使用预分词 token 和 FTS5 `bm25()` 排序，不依赖生产 ES。`bm25_mode=sqlite_fts5` 启用第三路；`stub` 仅运行 Dense／Sparse。旧 `qdrant_bm25` 模式明确拒绝运行，不是兼容后端；不得用 Sparse 结果伪装 BM25。

## 检索与评测职责

`build_eval_recall_pipeline` 装配生产检索被测对象，显式注入 eval collection、eval 编码器和选定的 BM25 后端。查询权重、阈值、候选深度与融合配置属于运行配置，必须随快照记录，不能仅依赖文档中的历史默认值复现。

候选路由、现有 38 维 `candidate_difference_v3` LambdaMART、在线模型加载与回退属于 eval 已有工程能力。保留这些实现不代表新研究已选择某种方法，也不改变已有生产接入结论；结果与适用范围见[实验记录](../experiments/ltr-fusion-v1.md)和[报告索引](../reports/REPORT_INDEX.md)。

`run` 同时保留文件产物与 SQLite 台账，记录输入／配置快照、编码器指纹、Git 与工作区身份、特征版本和运行质量。历史报告保留原路径，新一轮使用独立目录或时间戳；报告是否存在与方法是否有效是两件事。

## 测试与隔离约束

- 单元测试使用 fake 和临时文件，默认不连接真实活栈；生产依赖的契约测试验证固定版本接口，缺少真实依赖不能冒充通过。
- 集成测试连接真实 Qdrant／编码服务，需显式开启并使用 eval 配置；Qdrant 前缀护栏不得绕过。
- 生产依赖固定版本，升级后检查契约；签名漂移在负责该能力的 adapter 收口，不扩散生产 import。
- 密钥只存本地 `.env.eval`；生产库、生产 collection 和旧远端写入链路均不属于评测写入范围。

## 研究流程与工程架构的关系

当前研究仅在三路召回后的固定候选集合上探索融合／重排，不回原文补信息，不改召回。具体候选方法保持暂定，不能把局部窗口、比较器、关系结构、阈值或实验版本写成架构硬约束。

原 Robust Fusion 的 R1／R2、Gate、相似度测量与仲裁流程属于历史研究协议，退出活动执行身份。原稿与证据保留在原路径，由[历史导航](../archive/robust-fusion/README.md)说明用途；复用通用计算和校验工具不恢复旧研究阶段。

## 迁移历史与版本恢复

原 Step 0–6 记录了替换生产写 pipeline、引入独立存储、收口 `ProductComputer`、独立装配召回及物理拆仓的迁移过程。早期曾计划使用远端 eval MySQL 和 Qdrant BM25，后续工程改为本地 SQLite 与 SQLite FTS5。旧四域 `recall@10 ≈ 0.901`（±0.005）仅是当时固定语料的迁移等价参考，不能用作新数据或新研究的统一验收阈值。

重构前完整架构原文保全于标签 `research-pre-restructure-20260906`（提交 `4d31f18`）；可用 `git show research-pre-restructure-20260906:docs/architecture/decoupling-plan.md` 只读查看，或在独立目录检出标签恢复核对。Git 忽略的历史证据另有独立备份，位置和核对清单见[执行记录](../plans/research-restructure-execution-2026-09-06.md)。
