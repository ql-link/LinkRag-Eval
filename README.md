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

仓库已初始化(master 分支),承载文档与约定。代码按 [迁移路径](docs/architecture/decoupling-plan.md#分步迁移路径每步可验证基线-recall10--0901) 推进:Step 0–4 先在源仓库 `src/evaluation/` 内解耦,Step 5 用 `git filter-repo` 物理迁入本 repo。

## 基线

召回基线 `recall@10 ≈ 0.901`(8000 篇语料,四域)。每个迁移步骤以此为等价门槛(±0.005)。
