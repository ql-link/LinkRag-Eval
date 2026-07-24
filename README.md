# LinkRag-Eval

`LinkRag-Eval` 是 toLink-Rag 的**独立评测/质检项目**:衡量三路召回(dense/sparse/bm25)、解析清洗(CLEANING)、生成等环节的质量。它从生产仓库 `src/evaluation/` 剥离独立,**只通过产物级纯函数复用生产计算能力**,自己负责入库、检索、算分,使用独立 MySQL 库 `tolink_rag_eval_db`(同生产服务器、库级隔离)+ eval 独立前缀的 Qdrant collection,与生产隔离。

## 为什么独立

原评测模块与生产强耦合:直接 import 生产的写 pipeline、共享 Qdrant collection,导致生产清库会波及评测、生产改签名评测会断、被 per-user 配置拽回共享库。独立化切断这些坏耦合,只保留对"纯计算函数"和"被测对象"的依赖。详见 [docs/architecture/decoupling-plan.md](docs/architecture/decoupling-plan.md)。

## 文档导航

| 看这里 | 内容 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | **实现约定**(依赖边界、存储、配置、测试、安全纪律) |
| [下一对话交接](docs/HANDOFF.md) | 当前冻结决策、关键缺口、执行顺序和必读材料 |
| [当前开发状态](docs/CURRENT_STATUS.md) | 已完成范围、验收缺口和下一步 |
| [文档目录与完成状态](docs/DOCUMENT_CATALOG.md) | 已有文档、对应工作状态和历史替代关系 |
| [docs/architecture/](docs/architecture/) | 权威架构(解耦方案、依赖边界、存储设计) |
| [docs/plans/](docs/plans/) | 当前实施方案与验收标准 |
| [docs/experiments/](docs/experiments/) | 已验证实验和待验证候选方案 |
| [docs/archive/](docs/archive/) | 已被替代的历史设计，仅供追溯 |
| [docs/reports/](docs/reports/) | 历史评测实证(语料规模、稀疏模型对比、标注可靠性等) |
| [测试报告索引](docs/reports/REPORT_INDEX.md) | 当前与历史各阶段报告、机器可读结果及其用途 |

## 报告保留规则

- 每个测试阶段的 HTML、Markdown、JSON、CSV 报告及配套结果必须保留原路径。
- 新一轮测试必须使用新的 run/batch 目录或带时间戳文件名,禁止覆盖历史报告。
- 每个阶段结束后运行 `python3 scripts/build_report_index.py`,更新统一报告索引。
- 验收前运行 `python3 scripts/build_report_index.py --check`,确保没有未收录的新报告。

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

`init_eval_schema()`（`create_all`）仅供单测 / 本地快速起库。`0001` baseline 由 `EvalBase.metadata` 建全表；后续字段变更走显式 Alembic revision。当前 head 为 `0003`，新增 `eval_run` 运行质量摘要列，用于筛选 clean run。

## 当前阶段

代码已物理迁入本 repo,并按 [迁移路径](docs/architecture/decoupling-plan.md#分步迁移路径每步可验证基线-recall10--0901) 完成 Step 0–5 的主体实现:

- `EvalVectorIndexer` / `EvalVectorStore` / `EvalCorpusRepo` 已取代旧的生产写 pipeline 依赖。
- `ProductComputer` 已收口产物计算;dense/sparse 由 eval 自带 `llm/` 编码器承载,chunk 与 bm25 分词经 adapter 复用 rag 纯函数。
- 召回侧通过 `build_eval_recall_pipeline` 指向 eval Qdrant 前缀,query 编码走 eval 编码器;BM25 默认使用评测项目自持的 SQLite FTS5 sidecar,Qdrant BM25 仅保留兼容模式。
- MySQL eval 自持库 ORM 与 Alembic `0001` baseline 已落地。
- `run` 命令已在文件结果之外同步写入 `eval_run` / `eval_metric_result` 台账。
- 召回侧分路默认 `EVAL_RECALL_DENSE_SCORE_THRESHOLD=0.20`、`EVAL_RECALL_SPARSE_SCORE_THRESHOLD=0.10`。后者依据 Golden V2 realistic tune 调整,避免新 query 分布下 sparse 路由被全部过滤;历史四域基线需单独复验。
- CLI 已覆盖 `ingest` / `golden-gen` / `golden-opensource` / `cleaning` / `run` /
  `query-rewrite`。Query 重写使用独立 `EVAL_REWRITE_*`，只在 eval 内生成计划和做配对评测。

真实活栈已用正式 eval 前缀跑通 `alembic upgrade head`、小规模 ingest、四域 800 chunk/domain 重灌和 `run --precheck`;实证记录见 [docs/reports/live_smoke_2026_07_02.md](docs/reports/live_smoke_2026_07_02.md)。2026-07-04 的 `weighted-score-clean-20260704-top10` 已固化为 dense+sparse 两路 clean 基线:`failed_sources=0`,`zero_ranked=0`,`recall@10=0.9745`。

剩余关键工作统一维护在 [当前开发状态](docs/CURRENT_STATUS.md)。近期重点是补齐可复现运行快照和 CI 真契约门禁,完成 SQLite FTS5 A/B clean run,补真实 Query/多正例/多 Chunk 数据缺口,并在生产试验前实现不含 Rerank 的 LambdaMART 在线推理和降级能力。

## 验收

默认 CI / 本地检查不连接真实活栈:

```bash
python3 -m pytest -m "not integration" -q
lint-imports
```

真实 Qdrant/MySQL smoke 需要本地 `.env.eval` 且显式开启:

```bash
set -a; source .env.eval; set +a
alembic upgrade head
RUN_EVAL_INTEGRATION=1 python3 -m pytest tests/integration -q
```

## 基线

召回历史基线 `recall@10 ≈ 0.901`(四域语料)。每个迁移步骤以此为等价门槛(±0.005)。2026-07-01 首次正式 run 为 `0.8966`(在门槛内,但日志有少量 Qdrant 单路失败);2026-07-02 复跑为 `0.8919`(日志干净,但低于门槛)。分路诊断显示两条 ecom 回退样本 dense-only 均排第 1,启用 sparse 后被 RRF 融合挤出 top10;活栈 A/B 显示 `EVAL_RECALL_SPARSE_SCORE_THRESHOLD=0.30` 时 `recall@10=0.9571`,两条回退样本均修回。随后 weighted_score 正式 clean run `weighted-score-clean-20260704-top10` 固化为当前 dense+sparse 标准基线:`recall@10=0.9745`,`hit_rate@10=0.9898`,`map=0.8984`,`mrr=0.9212`,`failed_sources=0`,`zero_ranked=0`。
