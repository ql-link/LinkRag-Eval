# 解耦独立化方案(已批准基线)

> 本文是 `LinkRag-Eval` 从生产 RAG 仓库(toLink-Rag)`src/evaluation/` 剥离、独立成项目的总方案。
> 实现细节与硬规则见 [实现约定](../../AGENTS.md);当前进度见 [CURRENT_STATUS.md](../CURRENT_STATUS.md);历史设计见 [archive/](../archive/)。

## Context

原评测/质检模块(`src/evaluation/`)与生产 RAG 强耦合:`store/live_indexer.py`、`store/ingestor.py` 直接 import 生产的三个"算+写绑死"的写 pipeline(`EsIndexingPipeline.write_es_index`、`SparseIndexingPipeline.run`、`VectorStoragePipeline.index_chunks`)和生产 ORM;`golden/ingest_common.py` 还直驱 `ParseTaskPipeline` + 写生产 MySQL/MinIO/MQ。后果:

- 生产改写 pipeline 内部签名,评测灌库会跟着断;
- 评测与生产共享 Qdrant collection,**生产清库(剔 ES、迁 Qdrant named-dense、清 chunk)会波及评测数据**;
- 评测被 per-user 模型配置(`llm_user_config`)拽回共享 MySQL。

目标:质检独立成单独 git repo(`LinkRag-Eval`),只通过"产物级纯函数"复用生产计算能力,自己负责入库/检索/算分,使用本地 SQLite + eval 独立 collection 前缀的 Qdrant。

**已确认决策**:① 对齐目标态 Qdrant 统一、无 ES;② 独立 repo + 把 toLink-Rag 作为库依赖 import;③ Qdrant 同 host、eval 独立 collection 前缀;④ 自持元数据/结果使用 **本地 SQLite `runs/linkrag_eval.sqlite3`**。旧 MySQL 已于 2026-07-25 停用并完成一次性只读迁移。

## 生产已有的纯计算函数(eval 唯一应依赖的计算面)

| 产物 | 纯函数 | 位置(toLink-Rag) |
| --- | --- | --- |
| chunk 切分 | `ChunkingEngine.aprocess(text) -> list[Chunk]` | `src/core/splitter/chunking_engine.py:86` |
| dense 向量 | `create_chunk_embedding_pipeline()` → `aembed_chunks()` | `src/core/splitter/embedding_pipeline.py:230` / `factory.py:274` |
| sparse 向量 | `SparseVectorService.vectorize_texts()` | `src/core/encoding/sparse/pipeline.py:50` |
| bm25 分词 | `RagFlowTokenizer.tokenize() -> TokenizedText` | `src/core/preprocessor/ragflow_tokenizer.py:33` |

> 缺口:生产尚无"token → Qdrant 可查 BM25 sparse(IDF 权重)"的 compute 函数(现 bm25=ES)。bm25 路做成可插拔,P1 用 STUB,待生产落地后接入。

## 独立 repo 结构

> 布局:**src-layout**(包在 `src/linkrag_eval/`,import 仍 `from linkrag_eval.x`)。包名**不能**叫 `src`——会与 toLink-Rag 的 `src` 顶层包遮蔽、无法同时 import。详见 [AGENTS.md 二](../../AGENTS.md)。

```
src/linkrag_eval/
├── compute/        protocol.py(新) rag_adapter.py(新,唯一碰 rag) bm25_stub.py(新)
├── store/          vector_store.py(新 EvalVectorStore) indexer.py(替换 live_indexer)
│                   corpus_repo.py(本地 SQLite) ingestor.py(改写去 ORM) models.py/engine.py
│                   result_store.py catalog.py(搬迁)
├── retrieval/      recall_factory.py(新,注入 eval 前缀) recall_adapter.py(搬迁)
├── metrics/        retrieval.py cleaning.py registry.py(搬迁)
├── golden/         loader/schema/gen/synth/opensource(搬迁) ingest_corpus.py(重写,取代 ingest_common)
├── judge/          eval_llm.py(原样搬迁)
├── contracts/ runners/ reporters/(搬迁) config.py(新) cli.py(新)
└── alembic/        eval 自己的迁移(EvalBase.metadata,与生产隔离)
```

**废弃不搬**:`live_indexer.py`(被 `EvalVectorIndexer` 取代)、`noop_repository.py`、`golden/ingest_common.py`(全栈 Track A/B 整体废弃)。

## 核心组件

**`EvalVectorStore`**:复用 `QdrantIndexStore`+`BucketRouter`(dense/sparse schema 一致),用 eval 独立前缀实例化,绕开所有写 pipeline,自己用 `point_factory` 构点 upsert。BM25 不再推荐写 Qdrant sparse-vector,默认迁到 SQLite FTS5 sidecar。**启动护栏**:前缀必须含 `eval`,否则抛错。chunk_id 沿用 uuid5 确定性。

**`EvalCorpusRepo`(本地 SQLite)**:`EvalBase` 6 表落 `runs/linkrag_eval.sqlite3`，`_AutoPK` 使用 SQLite `Integer` 自增兼容。`eval_corpus_chunk.es_indexed` 改名 `bm25_indexed`;`eval_run` 新增 `computer_fingerprint`。

**`EvalDbResultStore`(SQLite 结果台账)**:`run` 命令保留文件产物用于审计/报告,同时把运行快照写入 `eval_run`,把聚合指标与问题类型分桶写入 `eval_metric_result`。`eval_run` 打平记录 `run_quality`、`failed_samples`、`failed_sources_json`、`zero_ranked`,用于筛选可固化的 clean run。domain 分桶当前仍保留在 JSON 报告,未扩 DB schema。

**召回:复用生产 `RecallPipeline` 指向 eval collection**(融合/排序 RRF+rerank 正是被测对象,自持会排序漂移)。`build_eval_recall_pipeline` 用 `compose_vector_storage_facade` 注入 eval 前缀 store + **系统 embedder**(query 侧 resolver 也走系统,绕开 per-user→共享库)。query 侧默认 `EVAL_RECALL_DENSE_SCORE_THRESHOLD=0.20`、`EVAL_RECALL_SPARSE_SCORE_THRESHOLD=0.10`;后者按 Golden V2 realistic tune 调整,历史四域基线需单独复验。

**bm25 可插拔**:`Bm25Mode = {STUB, SQLITE_FTS5(推荐), QDRANT_BM25(旧)}`。`sqlite_fts5` 把 `RagFlowTokenizer` 产出的 coarse/fine token 写入本地 SQLite FTS5 虚表,用内置 `bm25()` 排序,避免 Qdrant sparse-vector BM25 的远端延迟和性能波动。`qdrant_bm25` 仍保留作兼容模式,collection 指向 eval 独立 `EVAL_QDRANT_BM25_COLLECTION`。mode 写进 `EvalRun.snapshot_json`。

## 当前实现状态

本 repo 已完成物理迁入,并落地 Step 0–5 的主体代码。当前实现状态:

- Step 0:已落地。`LiveEvalChunkIndexer` 已由 `EvalVectorIndexer` 替代,写入经 `EvalVectorStore`,不再依赖三个生产写 pipeline。
- Step 1:已落地并完成后端收口。`EvalCorpusRepo`、独立 `EvalBase` ORM、Alembic `0001` baseline 均指向本地 SQLite。
- Step 2:已落地。`ProductComputer` / `RagProductComputer` 已收口产物计算;dense/sparse 已迁至 eval `llm/` 模块。
- Step 3:已落地。`build_eval_recall_pipeline` 指向 eval Qdrant 前缀,query 侧编码器由 eval 配置注入。
- Step 4:已落地。bm25 mode 配置与索引状态字段已存在;`stub` 只装 dense+sparse,`sqlite_fts5` 写本地 SQLite FTS5 并在召回侧装入 BM25 路;`qdrant_bm25` 保留为旧兼容模式。
- Step 5:已完成。代码、测试、CLI、报告、golden/cleaning 相关模块已迁入本 repo;import 边界由 `tests/test_import_boundary.py` 和 import-lint 强制。`Snapshot`、文件报告和 DB 台账现已固化 BM25 backend、sidecar identity、computer fingerprint、feature version、Git SHA、dirty 状态与工作区内容指纹。CI workflow 已补固定 SHA 依赖与 contract 缺包强制失败门禁，尚待提交推送后取得远端 Actions 证据；这不影响本步存储/报告迁移验收结论。
- Step 6:已完成。2026-07-24 从 `tolink_rag_eval_db` 重建 20k SQLite FTS5 sidecar（992000–992003 各 5,000 chunks），并在同一 116 条冻结集上完成 OFF/ON clean A/B。两轮均 `failed_sources=0`、`zero_ranked=0`，chunk Recall@10 `31.32%→36.74%`（`+5.42pp`），MRR `16.58%→17.03%`（`+0.45pp`）；完整快照与延迟观测见 `bm25_sqlite_final_acceptance_20260724` 报告。
- 2026-07-25:从 `100.86.10.52` 停机前备份中的 `tolink_rag_eval_db` 只读迁移到 `runs/linkrag_eval.sqlite3`。六表计数和逐行内容摘要一致；正常运行不再连接 MySQL。

文档中的迁移路径保留为验收清单;每步最终仍需用固定数据集验证 `recall@10 ≈ 0.901`(±0.005)。

## 分步迁移路径(每步可验证,基线 recall@10 ≈ 0.901)

- **Step 0(承重墙,先做)**:`LiveEvalChunkIndexer` 换 `EvalVectorIndexer`(走 `EvalVectorStore`,不再 import 三个写 pipeline),仍用 SQLite。验证:固定数据集重灌→`recall@10` 仍 ≈0.901(±0.005)。
- **Step 1(历史路径,已被 2026-07-25 决策替代)**:曾迁入独立 MySQL；当前已回迁本地 SQLite，以彻底移除远端数据库依赖。
- **Step 2**:抽 `ProductComputer` Protocol + `RagProductComputer`,收口散落 rag 直调,加契约测试。验证:`grep` 确认除 `rag_adapter.py`/`recall_factory.py` 外无 rag import;`recall@10` 不变。
- **Step 3**:`build_eval_recall_pipeline` 系统 embedder + eval 前缀替换对 `get_recall_pipeline()` 单例的直接复用。验证:日志确认不再查 `llm_user_config`,`recall@10` 仍 ≈0.901。
- **Step 4**:bm25 可插拔落地,P1 设 STUB。验证:三路重叠率符合 mode 预期。
- **Step 5**:`git filter-repo` 抽 `src/evaluation/` 历史到本 repo,按上节重排,`pyproject.toml` 把 rag 声明 path/git 依赖,生产删 `src/evaluation/`。验证:`pip install -e .` 跑全套,`recall@10` ≈0.901;import-lint CI 对黑名单生效。
- **Step 6(协同)**:生产剔 ES、迁 named-dense、落 Qdrant BM25 compute 后,bm25 切 `QDRANT_BM25`。验证:记录 bm25 接入 delta。

## 风险与协同

- **A. rag 包签名漂移**:契约测试(eval CI)对每个 `ProductComputer` 方法断言输出形状/维度;rag 依赖钉 git sha,升级走 PR 触发契约测试,漂移只需改 `rag_adapter.py` 一处。
- **B. 同 host 清库误伤**:eval 前缀强制含 `eval`;生产清库脚本须显式排除 `eval*`;清库 PR 注明"不影响 eval_* 前缀",窗口后 eval 重跑基线确认。
- **C. 系统 embedder vs per-user 偏差**:不强行对齐;把 `fingerprint`(dense 模型/sparse provider/bm25 mode)写进 `EvalRun.snapshot_json` 并在报告标注。**硬约束**:写入侧 `compute_dense` 与召回侧 query resolver 必须用同一系统 embedder,否则 eval 内部分布不一致比线上偏差更糟。

## 采纳的默认决策

1. bm25 P1 = **STUB**(只跑两路,不用 sparse 假装 bm25)。
2. 枚举字段 = **String + 注释**(改值不需 migration)。
3. **先在源 repo 内完成 Step 0–4 解耦,再 Step 5 物理拆 repo**(承重墙验证在源 repo 做,基线对比最干净)。

> 注:本段是迁移计划的原始执行路径。当前仓库已完成 Step 5 的主体迁入,后续以"当前实现状态"与 AGENTS.md 为准推进验收和收尾。
