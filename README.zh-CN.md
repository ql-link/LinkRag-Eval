# LinkRag-Eval

中文 | [English](README.md)

## 项目简介

`LinkRag-Eval` 是从 toLink-Rag 剥离的**独立检索评测／质检项目**。它复用生产的纯计算、
检索被测对象和 Qdrant 原语，自己负责评测入库、检索装配与算分，使用本地 SQLite
（默认 `runs/linkrag_eval.sqlite3`）和含 `eval` 前缀的 Qdrant collection，与生产
存储隔离：不读写生产库表，配置真值只存于被 Git 忽略的 `.env.eval`。

项目同时承载科研实验与论文复现：论文产物为独立分发的缓存复算包（见"科研与论文复现"），
而本仓库是完整的评测工程，两者安装前提与运行依赖不同。

## 主要能力

- 独立数据入库：语料与查询入库、元数据与结果写入本地 SQLite。
- 三路召回：Dense、Learned Sparse、SQLite FTS5 BM25；Dense／Sparse 编码由 eval 自带
  `llm/` 模块承载，chunk 切分经 adapter 复用生产纯计算，BM25 在 eval 内分词。
  启用三路召回需配置 `bm25_mode=sqlite_fts5`；`stub` 仅装配 Dense／Sparse。
- 候选快照：保存逐路候选与分数，供固定候选集合上的后续实验复用。
- 指标计算：偏好与位置等评测指标（纯函数）。
- LambdaMART 与排序诊断：现有 38 维 `candidate_difference_v3` 特征与回退能力；
  中文基线（`models/chinese-baseline/`）与英文基线（`models/english-baseline/`）
  均保留，历史 A/B 与 legacy 控制仅保留历史证据。

## 科研与论文复现

配套论文：**Preference Is Not Position: Evaluating Reranking on NevIR in Fixed
Hybrid Candidate Pools**。研究在三路召回后的固定候选集合内，联合评价指定段落的
严格偏好与位置，比较 Fusion、E0、N=8、BGE、Qwen 五种排序方法；不改变召回。

复现包是独立分发的缓存复算包，从保存的逐查询分数重算论文的三张表、两份图数据与
辅助破同分结果。需要 **Python 3.11 或更新版本**；NumPy 是唯一第三方 Python 依赖。
**CPU 即可运行，无需 GPU、API 密钥、数据库或 Qdrant 服务**
（该简化仅适用于复算包，不适用于完整项目，见下节）。

- Release 页面：[reproduction](https://github.com/ql-link/LinkRag-Eval/releases/tag/reproduction)
- 附件下载：[`linkrag-nevir-reproduction.zip`](https://github.com/ql-link/LinkRag-Eval/releases/download/reproduction/linkrag-nevir-reproduction.zip)
  （请下载该附件；GitHub 自动生成的 Source code 包不含缓存分数数据）

```bash
unzip linkrag-nevir-reproduction.zip
cd linkrag-nevir-reproduction
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -B -m unittest -v test_reproduction
.venv/bin/python -B reproduce.py --output reproduced
```

输出目录 `reproduced` 必须尚不存在；再次运行请为 `--output` 指定新的目录名。

已验证环境：macOS arm64、Python 3.11.15、NumPy 2.4.6；10 项测试通过，
`reproduced/verification.json` 状态 `VERIFIED_CACHE_REPLAY`。验证范围是保存分数复算，
不包括重新训练、真实模型推理或重建召回；包内 README 仅另有可选 Qwen/BGE
重新推理说明。

## 项目安装与开发

> 待核项：toLink-Rag 的本地可编辑安装路径按本机实际填写；CI 将其钉在固定 git SHA
> `861f2481`（见 pyproject.toml 注释与 AGENTS.md）。安装前请确认该依赖可用。

- Python ≥ 3.11；先以本地可编辑方式安装生产依赖 toLink-Rag（暴露 `src` 顶层包），
  再 `python3 -m pip install -e ".[dev,ltr]"` 安装本项目与检查依赖（与 CI 一致）；
  `ltr` 包含 LambdaMART 训练所需的 LightGBM 和 scikit-learn。
- 配置：复制 `.env.eval.example` 为 `.env.eval` 填写真值（gitignored）。
- 数据库：默认本地 SQLite `runs/linkrag_eval.sqlite3`，经 Alembic 迁移建表
  `alembic upgrade head`；`init_eval_schema()` 仅供测试快速起库。
- 检查（不连接真实活栈）：

```bash
python3 -m pytest -m "not integration" -q
lint-imports
```

## 文档导航与历史

| 你要做什么 | 去哪里 |
| --- | --- |
| 不确定读哪份 | [文档选读](docs/DOCUMENT_CATALOG.md) |
| 看当前进度与下一步 | [当前状态](docs/CURRENT_STATUS.md) |
| 逐项回顾实验、记录新实验 | [实验台账](docs/experiments/EXPERIMENT_LOG.md) |
| 看各类文件存在哪、Git 与备份覆盖什么 | [存放总览](docs/WORKSPACE_MAP.md) |
| 找输入与基线模型 | [数据入口](data/README.md) · [模型入口](models/README.md) |
| 选择脚本或命令 | [使用目录](scripts/README.md) |
| 查实验结论及其口径 | [报告选读](docs/reports/REPORT_INDEX.md) |
| 找某次运行的实际文件 | [实验目录](runs/post_recall/README.md) |
| 修改工程代码 | [实现约定](AGENTS.md) · [架构](docs/architecture/decoupling-plan.md) |

历史保全：重构前源码在标签 `research-pre-restructure-20260906`（提交 `4d31f18`），
用 `git show research-pre-restructure-20260906:相对路径` 查看或在独立目录检出；
Git 忽略证据的备份位置与恢复方式见
[恢复说明](docs/plans/runtime-simplification-2026-09-06.md#recovery)。
当前没有人工作业，[human_tasks/README.md](human_tasks/README.md) 仅说明历史入口；
历史协议中的步骤与门槛不自动成为当前研究的前置条件。
