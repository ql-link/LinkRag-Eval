# LinkRag-Eval

`LinkRag-Eval` 是从 toLink-Rag 剥离的独立评测／质检项目。它复用生产的纯计算、检索被测对象和 Qdrant 原语，自己负责评测入库、检索装配与算分，使用本地 SQLite 和含 `eval` 前缀的 Qdrant collection，与生产存储隔离。

## 文档入口

| 文档 | 用途 |
| --- | --- |
| [当前状态](docs/CURRENT_STATUS.md) | 项目进度、未完成工作和下一步的唯一入口 |
| [交接说明](docs/HANDOFF.md) | 继续工作前应区分的工程边界、研究讨论与历史证据 |
| [实现约定](AGENTS.md) | 依赖边界、存储隔离、配置与测试纪律 |
| [解耦架构](docs/architecture/decoupling-plan.md) | 当前组件职责及生产依赖的复用方式 |
| [研究讨论与独立审查](docs/plans/research-direction-review-2026-09-06.md) | 原问题、审查意见、回应与未决事项；方法仍为暂定 |
| [重构执行记录](docs/plans/research-restructure-execution-2026-09-06.md) | 本次清理的授权范围、保全版本、实际改动与验证 |
| [文档目录](docs/DOCUMENT_CATALOG.md) | 各文档的使用身份和历史替代关系 |
| [报告索引](docs/reports/REPORT_INDEX.md) | 各阶段实证与运行产物的保留路径 |
| [Robust Fusion 历史导航](docs/archive/robust-fusion/README.md) | 原 R1／R2、Gate、标注与相似度协议；保留原文，不再作为活动流程 |

## 工程能力与研究边界

工程保留独立入库、Dense／Learned Sparse／SQLite FTS5 BM25 召回、候选快照、评测指标，以及现有 38 维 `candidate_difference_v3` LambdaMART 和回退能力。Dense／Sparse 编码由 eval 自带 `llm/` 模块承载；chunk 切分经 adapter 复用生产纯计算，BM25 在 eval 内分词。启用三路召回需配置 `bm25_mode=sqlite_fts5`；`stub` 仅装配 Dense／Sparse。

当前研究围绕三路召回后的固定候选集合，探索如何利用候选的可见关键差异与逐路分数／排名改进融合或重排；不回原文补充信息，不改变召回。具体方法、特征、比较方式与实验版本尚未定案。历史协议中的步骤、门槛或“唯一下一步”不自动成为新研究的前置条件，具体工作以当前状态和用户当轮授权为准。

## 本地数据库与检查

元数据和结果库默认位于 `runs/linkrag_eval.sqlite3`。在已配置 eval 环境的终端中，通过仓库根目录的 Alembic 迁移建表：

```bash
alembic upgrade head
```

`init_eval_schema()` 的 `create_all` 仅供测试／本地快速起库；正式 schema 演进使用 Alembic revision。配置真值只存于被 Git 忽略的 `.env.eval`。

默认检查不连接真实活栈：

```bash
python3 -m pytest -m "not integration" -q
lint-imports
```

当前没有人工作业；[human_tasks/README.md](human_tasks/README.md)仅说明历史入口。当前运行接口不为旧研究流程保留兼容层，简化范围见[运行链路简化记录](docs/plans/runtime-simplification-2026-09-06.md)。

## 历史与恢复

阶段报告、标签、原始提交、锁和运行证据保留原路径；新报告使用独立目录或带时间戳的文件名。生成报告后运行 `python3 scripts/build_report_index.py`，交付前用同一脚本的 `--check` 校验索引。

重构前源码保全于标签 `research-pre-restructure-20260906`（提交 `4d31f18`）。可用 `git show research-pre-restructure-20260906:相对路径` 查看旧文件，或在独立目录检出该标签进行恢复核对，避免覆盖当前工作区。Git 忽略的证据另有经过散列核对的备份；其位置、范围与恢复依据见[执行记录](docs/plans/research-restructure-execution-2026-09-06.md)。保留证据或退役流程均不改变历史实验结论。
