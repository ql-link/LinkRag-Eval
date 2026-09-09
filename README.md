# LinkRag-Eval

`LinkRag-Eval` 是从 toLink-Rag 剥离的独立评测／质检项目。它复用生产的纯计算、检索被测对象和 Qdrant 原语，自己负责评测入库、检索装配与算分，使用本地 SQLite 和含 `eval` 前缀的 Qdrant collection，与生产存储隔离。

## 文档入口

不确定读哪份，先看[文档选读](docs/DOCUMENT_CATALOG.md)。以下是常用直达入口：

| 你要做什么 | 去哪里 |
| --- | --- |
| 看当前进度与下一步 | [当前状态](docs/CURRENT_STATUS.md) |
| 逐项回顾实验、记录新实验 | [实验台账](docs/experiments/EXPERIMENT_LOG.md) |
| 看各类文件存在哪、Git 与备份覆盖什么 | [存放总览](docs/WORKSPACE_MAP.md) |
| 找输入与基线模型 | [数据入口](data/README.md) · [模型入口](models/README.md) |
| 选择脚本或命令 | [使用目录](scripts/README.md) |
| 查实验结论及其口径 | [报告选读](docs/reports/REPORT_INDEX.md) |
| 找某次运行的实际文件 | [实验目录](runs/post_recall/README.md) |
| 修改工程代码 | [实现约定](AGENTS.md) · [架构](docs/architecture/decoupling-plan.md) |

## 工程能力与研究边界

工程保留独立入库、Dense／Learned Sparse／SQLite FTS5 BM25 召回、候选快照、评测指标，以及现有 38 维 `candidate_difference_v3` LambdaMART 和回退能力。Dense／Sparse 编码由 eval 自带 `llm/` 模块承载；chunk 切分经 adapter 复用生产纯计算，BM25 在 eval 内分词。启用三路召回需配置 `bm25_mode=sqlite_fts5`；`stub` 仅装配 Dense／Sparse。

当前研究统一使用英文，沿用已完成的英文链路与 NevIR 可行性证据，不重复语言验证或切换中文案例。当前只维护[模型入口](models/README.md)中的中文基线（原 A，`models/chinese-baseline/`）与英文基线（`models/english-baseline/`）：中文基线为固定参照，英文基线为后续研究起点；B 和 legacy 控制仅保留历史证据。

研究围绕三路召回后的固定候选集合，探索如何利用候选的可见关键差异与逐路分数／排名改进融合或重排；不回原文补充信息，不改变召回。具体方法、特征、比较方式与实验版本尚未定案。历史协议中的步骤、门槛或“唯一下一步”不自动成为新研究的前置条件，具体工作以当前状态和用户当轮授权为准。

## 本地数据库与检查

元数据和结果库默认位于 `runs/linkrag_eval.sqlite3`。在已配置 eval 环境的终端中，通过仓库根目录的 Alembic 迁移建表：

```bash
alembic upgrade head
```

`init_eval_schema()` 的 `create_all` 仅供测试／本地快速起库；正式 schema 演进使用 Alembic revision。配置真值只存于被 Git 忽略的 `.env.eval`。

安装固定版本的生产依赖后，用 `python3 -m pip install -e ".[dev,ltr]"` 安装检查依赖（与 CI 一致）；`ltr` 包含 LambdaMART 训练所需的 LightGBM 和 scikit-learn。

默认检查不连接真实活栈：

```bash
python3 -m pytest -m "not integration" -q
lint-imports
```

当前没有人工作业；[human_tasks/README.md](human_tasks/README.md)仅说明历史入口。当前运行接口不为旧研究流程保留兼容层，简化范围见[运行链路简化记录](docs/plans/runtime-simplification-2026-09-06.md)。

## 探索数据接入

T2 接入目前暂停，已保留 `exploration ingest/candidates/coverage` 接口。参数与动作见[脚本和命令目录](scripts/README.md#3-数据准备与历史复现入口)，来源绑定、全文与续跑规则见[研究计划 §3.3](docs/plans/post-recall-research-plan.md#33-探索输入准备与交接)；实际进度见[当前状态](docs/CURRENT_STATUS.md)。

## LTR 模型与 NevIR 历史实验入口

当前模型的加载方式见[中文／英文基线](models/README.md)。开发诊断、特征版本训练比较及历史 A/B 复现入口统一查[脚本和命令目录](scripts/README.md)，所需输入与结果分别查[数据入口](data/README.md)和[实验目录](runs/post_recall/README.md)。

可复用计算位于 `src/linkrag_eval/retrieval/learning_to_rank/`，职责见[解耦架构](docs/architecture/decoupling-plan.md)。诊断复用已有快照与模型，不要求重跑数据准备、采集或训练。

## 历史与恢复

阶段报告、标签、原始提交、锁和运行证据保留原路径；新报告使用独立目录或带时间戳的文件名。每次已执行实验按[记录规则](docs/experiments/EXPERIMENT_LOG.md#记录规则)留存，并在台账追加入口，负结果、失败和中止同样登记。生成报告后运行 `python3 scripts/build_report_index.py`，交付前用同一脚本的 `--check` 校验索引。

重构前源码保全于标签 `research-pre-restructure-20260906`（提交 `4d31f18`）。可用 `git show research-pre-restructure-20260906:相对路径` 查看旧文件，或在独立目录检出该标签进行恢复核对，避免覆盖当前工作区。Git 忽略的证据另有既有备份；其位置、范围与恢复方式见[恢复说明](docs/plans/runtime-simplification-2026-09-06.md#recovery)。保留证据或退役流程均不改变历史实验结论。
