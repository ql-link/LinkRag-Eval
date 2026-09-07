# LinkRag-Eval 解耦架构

本文件说明当前工程边界与组件职责；强制规则见 [AGENTS.md](../../AGENTS.md)，实施进度和待办只在 [CURRENT_STATUS.md](../CURRENT_STATUS.md) 维护。旧 Step 0–6 的迁移计划已成为历史，不再作为本次研究的执行清单。版本与备份见[恢复说明](../plans/runtime-simplification-2026-09-06.md#recovery)。

## 项目边界

LinkRag-Eval 是独立评测／质检项目。它复用 toLink-Rag 的纯计算、检索被测对象和 Qdrant 原语，自己负责数据、入库、召回装配、评测与报告。元数据和结果使用本地 SQLite；向量使用含 `eval` 前缀的独立 collection。不得调用生产写 pipeline、生产 ORM、per-user 配置解析、MinIO 或 MQ 来完成评测。

包使用 src-layout：文件位于 `src/linkrag_eval/`，import 为 `linkrag_eval.*`。外层 `src/` 不是本项目包，避免与生产的顶层 `src.*` 包遮蔽。

## 产物计算与依赖收口

| 能力 | 实现与边界 |
| --- | --- |
| chunk 切分 | 经 `compute/rag_adapter.py` 复用 `ChunkingEngine.aprocess` |
| BM25 分词 | eval 自持 `local_bm25_tokens`／`SQLiteBm25Tokenizer`，写入与查询口径一致 |
| Dense／Learned Sparse 编码 | 使用 eval 自持 `llm/` 编码器，按 `EVAL_EMBED_*`／`EVAL_SPARSE_*` 配置，不读取生产用户配置 |
| 向量存储 | `store/vector_store.py` 复用 `QdrantIndexStore` 和 point 模型，显式指定 eval collection |
| 检索装配 | `retrieval/recall_factory.py` 复用 `RecallPipeline`、Dense／Sparse Retriever 及 storage facade，注入 eval 存储和编码器 |
| 请求／响应适配 | `retrieval/recall_adapter.py` 转换生产被测对象类型 |

生产 import 只允许出现在上述四个 adapter 文件，其他模块依赖 eval 抽象；具体白名单和黑名单由 AGENTS、import-lint 与 `tests/test_import_boundary.py` 约束。

`ProductComputer` 定义 `compute_chunks`、`compute_dense`、`compute_sparse`、`dense_dim` 和 `fingerprint`。计算方法只产出 chunk／向量，不写存储。测试可注入 fake；契约测试验证真实依赖的接口。写入侧与 query 侧须使用同一编码口径，快照记录模型与实际配置。

Dense 的 `aembed_with_metadata` 返回 `DenseVec`，Sparse 的 `aencode` 返回 `SparseVec`；产物的 `input_chars` 是成功请求所发送文本的 Unicode 码点数，`None` 表示未知。现有召回所需的 Dense `aembed` 仍返回向量值。两路客户端分别支持 `reject` 和 `prefix_on_length_error`，后者只响应各端点已核实的明确长度错误，缩短本条请求副本；普通错误不会改变文本。Dense 批长度错误先逐条原样检查。查询使用相同策略，但当前逐查询产物不持久化发送长度，不能由策略记录反推其实际长度。

## 独立存储

`EvalVectorStore` 校验前缀包含 `eval`，并在 eval 内按固定 routing 常量计算 bucket，显式构造 `{prefix}_{bucket_id}` collection 名。它不依赖生产 `BucketRouter` 或用户表。向量 schema 与固定版本的生产 Qdrant 原语保持一致，Sparse 名由 eval 配置提供，默认 `sparse_text`；写入与召回必须使用相同名称和编码口径。

chunk ID 使用 `uuid5(NAMESPACE_DNS, f"tolink-eval:eval-{dataset_id}-{doc_id}-{ordinal}")`，固定数据、文档和 ordinal 产生相同 ID，三路候选与 qrels 共用该 ID。确定性 ID 本身不保证语料正文未变，复现实验仍需核对输入快照。

`EvalCorpusRepo` 与结果台账使用 `runs/linkrag_eval.sqlite3`。`EvalBase` 包含 `eval_dataset`、`eval_corpus_chunk`、`eval_query`、`eval_qrel`、`eval_run`、`eval_metric_result` 六表；schema 演进经仓库根目录 `alembic/` 完成，与生产迁移隔离。当前不保留旧 MySQL 配置、驱动或迁移入口，禁止访问生产库。

迁移 `0004` 给 corpus 行新增可空整数 `dense_input_chars`、`sparse_input_chars`，旧行保留 NULL，不推定为全文编码。入库始终从原文分别生成两路编码和全文 BM25，正文、原始 `char_len`、ID 不随编码截短改变。重写已有行时，先撤销旧的三路完成标记和长度回执，再写索引；最终将全文、两路回执与完成标记同次写入 SQLite。跨存储失败后该行需重新核对，不继承旧完成状态。长度回执用于接入记录、续接完整性核验与汇总，不加入排序候选字段。

完整 T2 接入通过 `runners/t2_workflow.py` 绑定运行目录内独立的 `corpus.sqlite3`、`bm25.sqlite3` 和专用 eval Qdrant collection，不改全局环境配置。独立语料库仍使用同一 Alembic 迁移链，程序化显式 SQLite URL 优先于默认库。正文流式分批处理，续接按原始身份与正文核对实际索引；状态说明见研究计划，不凭本地写入标记断言远端数据存在。

BM25 由 eval 的 SQLite FTS5 sidecar 承载，使用预分词 token 和 FTS5 `bm25()` 排序，不依赖生产 ES。`bm25_mode=sqlite_fts5` 启用第三路；`stub` 仅运行 Dense／Sparse。旧 `qdrant_bm25` 模式明确拒绝运行，不是兼容后端；不得用 Sparse 结果伪装 BM25。

FTS sidecar 的 schema 2 用普通索引表 `bm25_chunk_rows` 将 chunk ID 关联到 FTS rowid，更新时先定位 rowid，避免按 FTS 的未索引 ID 列反复扫描。现有 schema 1 在初始化时一次迁移，保留 FTS 正文、rowid 和排序口径；正常读批次不执行迁移。该 sidecar 版本由 `SQLiteBm25Store` 管理，不属于六表的 Alembic schema。

## 检索与评测职责

`build_eval_recall_pipeline` 装配生产检索被测对象，显式注入 eval collection、eval 编码器和选定的 BM25 后端。查询权重、阈值、候选深度与融合配置属于运行配置，必须随快照记录，不能仅依赖文档中的历史默认值复现。

探索采集使用 `open_eval_recall_pipeline` 异步上下文，由 factory 显式关闭本次创建的 Dense、Sparse 和 Qdrant 客户端；正常结束、失败和取消均走同一释放路径。eval Qdrant 客户端使用显式配置的端点直连，不继承系统 HTTP 代理。

向量写入侧同时给 `QdrantIndexStore` 和实际注入的 `AsyncQdrantClient` 设置 60 秒超时，避免只配置原语对象而实际 HTTP 请求仍使用默认 5 秒。入库失败记录保留有限的异常因果类型链、可取得的 HTTP 状态及 Sparse 固定失败类别，包含 SDK 包装的传输错误；不记录任意服务错误代码、异常正文、请求文本或凭证。Sparse 仅将精确的 HTTP 403 与 `AccountOverdueError` 映射为账户欠费，其他普通 4xx 保留一般 HTTP 错误类别；这些诊断字段不改变重试或输入长度处理规则。

`EvalVectorStore` 对原语未识别的 SDK 网络包装异常，在 Dense／Sparse 各自的写入调用周围最多尝试 3 次，间隔为 1、2 秒。每次复用本路已经构造的向量和 ID；一条向量写入成功后，另一条的重试不会再次调用编码器或覆盖已成功的命名向量。重试判断只沿显式异常因果与 SDK 的 `source` 识别已知传输类型，普通 HTTP 响应、参数错误和取消按原路径退出；原语已有的重试不会在此叠加。这里的尝试次数针对一次原语写入调用，该调用内部可能包含多个 HTTP 请求。

候选路由、现有 38 维 `candidate_difference_v3` LambdaMART、在线模型加载与回退属于 eval 已有工程能力。保留这些实现不代表新研究已选择某种方法，也不改变已有生产接入结论；结果与适用范围见[实验记录](../experiments/ltr-fusion-v1.md)和[报告索引](../reports/REPORT_INDEX.md)。

`run` 同时保留文件产物与 SQLite 台账，记录输入／结果位置、实际配置、Git 提交及未提交状态、特征版本和运行质量；不逐次扫描工作区或 BM25 正文计算摘要。历史报告保留原路径，新一轮使用独立目录或时间戳；报告是否存在与方法是否有效是两件事。

## 测试与隔离约束

- 单元测试使用 fake 和临时文件，默认不连接真实活栈；生产依赖的契约测试验证固定版本接口，缺少真实依赖不能冒充通过。
- 集成测试连接真实 Qdrant／编码服务，需显式开启并使用 eval 配置；Qdrant 前缀护栏不得绕过。
- 生产依赖固定版本，升级后检查契约；签名漂移在负责该能力的 adapter 收口，不扩散生产 import。
- 密钥只存本地 `.env.eval`；生产库、生产 collection 和旧远端写入链路均不属于评测写入范围。

## 研究流程与工程架构的关系

当前研究仅在三路召回后的固定候选集合上探索融合／重排，不回原文补信息，不改召回。具体候选方法保持暂定，不能把局部窗口、比较器、关系结构、阈值或实验版本写成架构硬约束。新增兼容或校验机制必须有当前用途；不预设哈希台账和多阶段准入流程。

原 Robust Fusion 的 R1／R2、Gate、相似度测量与仲裁流程属于历史研究协议，退出活动执行身份。已移除的原稿通过 Git 历史追溯，保留的数据定义与证据由[历史导航](../archive/robust-fusion/README.md)说明用途；保留历史证据不要求保留旧版本运行兼容。

## 迁移历史与版本恢复

原 Step 0–6 记录了替换生产写 pipeline、引入独立存储、收口 `ProductComputer`、独立装配召回及物理拆仓的迁移过程。早期曾计划使用远端 eval MySQL 和 Qdrant BM25，后续工程改为本地 SQLite 与 SQLite FTS5。旧四域 `recall@10 ≈ 0.901`（±0.005）仅是当时固定语料的迁移等价参考，不能用作新数据或新研究的统一验收阈值。

重构前完整架构原文保全于标签 `research-pre-restructure-20260906`（提交 `4d31f18`）；可用 `git show research-pre-restructure-20260906:docs/architecture/decoupling-plan.md` 只读查看，或在独立目录检出标签恢复核对。Git 忽略的历史证据另有独立备份，范围与恢复方式见[恢复说明](../plans/runtime-simplification-2026-09-06.md#recovery)。
