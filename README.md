# LinkRag-Eval

`LinkRag-Eval` 是 toLink-Rag 的**独立评测/质检项目**:衡量三路召回(dense/sparse/bm25)、解析清洗(CLEANING)、生成等环节的质量。它从生产仓库 `src/evaluation/` 剥离独立,**只通过产物级纯函数复用生产计算能力**,自己负责入库、检索、算分,使用独立 MySQL 库 `tolink_rag_eval_db`(同生产服务器、库级隔离)+ eval 独立前缀的 Qdrant collection,与生产隔离。

## 为什么独立

原评测模块与生产强耦合:直接 import 生产的写 pipeline、共享 Qdrant collection,导致生产清库会波及评测、生产改签名评测会断、被 per-user 配置拽回共享库。独立化切断这些坏耦合,只保留对"纯计算函数"和"被测对象"的依赖。详见 [docs/architecture/decoupling-plan.md](docs/architecture/decoupling-plan.md)。

## 文档导航

| 看这里 | 内容 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | **实现约定**(依赖边界、存储、配置、测试、安全纪律) |
| [docs/architecture/](docs/architecture/) | 权威架构(解耦方案、依赖边界、存储设计) |
| [docs/design/](docs/design/) | 历史设计(monorepo 时期,部分被解耦方案取代) |
| [docs/reports/](docs/reports/) | 历史评测实证(语料规模、稀疏模型对比、标注可靠性等) |

## 数据库初始化

评测库 `tolink_rag_eval_db` 的 schema 演进唯一入口是 `alembic/`（`EvalBase.metadata`，与生产隔离）：

```bash
# 1. 建库(utf8mb4),复用生产服务器/账号、只换库名
CREATE DATABASE IF NOT EXISTS tolink_rag_eval_db
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

# 2. 建表(6 张 eval_* 表 + alembic_version)
set -a; source .env.eval; set +a     # 提供 EVAL_DB_*
alembic upgrade head                  # URL 由 env.py 从 EVAL_DB_* 构建(aiomysql→pymysql)
```

`init_eval_schema()`（`create_all`）仅供单测 / 本地快速起库。`0001` baseline 由 `EvalBase.metadata` 建全表，`alembic check` 保证 baseline 与 ORM 零 diff；后续字段变更走 `alembic revision --autogenerate`。

## 当前阶段

代码已物理迁入本 repo,并按 [迁移路径](docs/architecture/decoupling-plan.md#分步迁移路径每步可验证基线-recall10--0901) 完成 Step 0–5 的主体实现:

- `EvalVectorIndexer` / `EvalVectorStore` / `EvalCorpusRepo` 已取代旧的生产写 pipeline 依赖。
- `ProductComputer` 已收口产物计算;dense/sparse 由 eval 自带 `llm/` 编码器承载,chunk 与 bm25 分词经 adapter 复用 rag 纯函数。
- 召回侧通过 `build_eval_recall_pipeline` 指向 eval Qdrant 前缀,query 编码走 eval 编码器。
- MySQL eval 自持库 ORM 与 Alembic `0001` baseline 已落地。
- `run` 命令已在文件结果之外同步写入 `eval_run` / `eval_metric_result` 台账。
- CLI 已覆盖 `ingest` / `golden-gen` / `golden-opensource` / `cleaning` / `run`。

真实活栈已用正式 eval 前缀跑通 `alembic upgrade head`、小规模 ingest、四域 800 chunk/domain 重灌和 `run --precheck`;实证记录见 [docs/reports/live_smoke_2026_07_02.md](docs/reports/live_smoke_2026_07_02.md)。

剩余关键工作:决策 2026-07-02 复跑 `recall@10=0.8919` 暴露的 sparse+RRF 融合口径问题,并等待生产 Qdrant BM25 compute/search 落地后再切 `EVAL_BM25_MODE=qdrant_bm25`。当前 P1 默认仍是 `stub`,即只跑 dense+sparse 两路。

## 基线

召回历史基线 `recall@10 ≈ 0.901`(四域语料)。每个迁移步骤以此为等价门槛(±0.005)。2026-07-01 首次正式 run 为 `0.8966`(在门槛内,但日志有少量 Qdrant 单路失败);2026-07-02 复跑为 `0.8919`(日志干净,但低于门槛)。分路诊断显示两条 ecom 回退样本 dense-only 均排第 1,启用 sparse 后被 RRF 融合挤出 top10,因此当前状态是"活栈可跑通,指标偏差已定位到融合口径,需决策是否优化或接受为新基线"。
