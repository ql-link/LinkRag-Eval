# 文件与产物存放总览

本页回答“东西保存在哪、是否随 Git、能否清理”；按 2026-09-07 的实际工作树核对，包含隐藏目录和被忽略的本地产物。文档怎么选见[文档选读](DOCUMENT_CATALOG.md)，进度只看[当前状态](CURRENT_STATUS.md)。

路径相对仓库根目录。下文“可纳入 Git”不表示已经提交；当前有未提交改动与新文件，单独 clone 不能还原这个工作区。

## 1. 按保存内容找位置

运行产物的目录状态、依赖链与清理候选统一维护在 [runs/post_recall/README.md](../runs/post_recall/README.md)；本页只记录保存位置与备份。

| 保存什么 | 实际位置／首选入口 | 保存方式与职责 |
| --- | --- | --- |
| 实现、测试、运行入口 | `src/linkrag_eval/`、`tests/`、[scripts/README.md](../scripts/README.md) | 源码进 Git；脚本编排与可复用计算分开 |
| 配置与依赖 | `pyproject.toml`、`uv.lock`、`configs/`、[配置样例](../.env.eval.example) | 样例和依赖进 Git；配置真值 `.env.eval` 仅本地，含密钥 |
| 数据库结构 | `alembic/` | 迁移源码进 Git，数据库文件另存 |
| 计划、决策与实证 | [docs/DOCUMENT_CATALOG.md](DOCUMENT_CATALOG.md) | 文档可纳入 Git；报告正文在 `docs/reports/`，不代替原始结果 |
| 原始数据与派生标签 | [data/README.md](../data/README.md) | 原始 NevIR 在 `data/post_recall/nevir/`；历史下载／派生数据在 `data/robust_fusion/`；只有根 README 可纳入 Git |
| 两个当前模型 | [models/README.md](../models/README.md) | `chinese-baseline/` 可纳入 Git；`english-baseline/` 仅本地。两包都包含权重、特征契约与校验材料 |
| 保存候选、实验配置、分数、矩阵、追踪、日志 | [runs/post_recall/README.md](../runs/post_recall/README.md) | 按实验保存；仅列入白名单的 README 可纳入 Git，运行产物忽略 |
| 默认评测库与两个 sidecar | `runs/linkrag_eval.sqlite3`、`runs/bm25_eval.sqlite3`、`runs/alt_embedding_eval.sqlite3` | 分别保存评测元数据／正文／结果、FTS5 索引、替代 embedding 缓存；均仅本地，不是本轮 NevIR 的独立库 |
| 真实召回的向量索引 | 远端 eval Qdrant collection；实验的 `storage/owner.json` 等记录位置 | 不在 Git 或 SQLite 内；本轮未连接远端检查。已有离线候选诊断不依赖重建索引 |
| 旧人工材料 | [human_tasks/README.md](../human_tasks/README.md)、`runs/robust_fusion/` 及既有归档 | 无当前人工任务；指南可进 Git，提交／原始记录仅本地或在旧归档，三个失效入口链接已清理 |
| 本地论文全文 | [docs/papers/README.md](papers/README.md) | PDF 仅本地；文献地图与目录进 Git |
| 助手资料 | `.ai/`、`.agents/skills/` | 前者是随仓库保留的共享资料，含旧生产流程；后者是被忽略的本地技能，不是实验数据 |
| 运行环境与工具缓存 | `.venv/`、`__pycache__/`；工具按需生成 `.pytest_cache/`、`.ruff_cache/`、`.import_linter_cache/` | 后三类已清理；虚拟环境及 Python 字节码保留，虚拟环境含单独安装的生产依赖 |
| 历史数据库副本 | [linkrag-eval-sqlite-share-20260827/README.md](../linkrag-eval-sqlite-share-20260827/README.md) | 三个数据库的一致性导出，约 306 MiB；不是整个项目备份 |
| Git 历史与独立备份 | `.git/`、[恢复说明](plans/runtime-simplification-2026-09-06.md#recovery) | Git 保存已提交源码；独立 tar 只覆盖当时选入的本地产物，范围见 §3 |

`golden/`、`.specs/`、`runs/golden_v2/` 当前本地不存在。历史报告引用它们只说明当时的位置，不表示可以直接打开，也不要求恢复旧流程。

## 2. 当前英文实验的实际保存链

**原始 NevIR → 共享 Train／开发输入与候选 → 英文特征对照 → 两个当前模型 → 开发诊断。**
当前英文模型使用的六个输入由[英文 selection.json](../runs/post_recall/nevir-english-features-20260907/comparison/english/selection.json)指定；数量、划分和排除规则统一查[数据入口](../data/README.md)，这里不重复维护。

| 环节 | 保存位置 | 当前用途 |
| --- | --- | --- |
| 上游数据 | `data/post_recall/nevir/` | 原始划分及来源记录；不从名称猜测试使用状态 |
| 查询、监督、共同语料和保存候选 | `runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment/` | `prepared/` 是查询／监督／语料，`candidates/train/` 与 `candidates/development/` 是当前复用候选；六个直接链接见[数据入口](../data/README.md#2-当前英文训练实际使用的六个输入) |
| 本轮语料库与 BM25 索引 | 同上目录的 `storage/corpus.sqlite3`、`storage/bm25.sqlite3` | 与根级默认数据库隔离；[owner.json](../runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment/storage/owner.json)记录远端 collection `eval_nevir_ltr_20260907_9` 等身份 |
| 英文训练比较 | [nevir-english-features-20260907/](../runs/post_recall/nevir-english-features-20260907/README.md) | `comparison-config.json` 是启动配置；`comparison/english/` 保留选择记录、开发分数和英文 NPZ；`comparison/legacy/` 是历史控制 |
| 当前模型包 | [models/](../models/README.md) | 中文与英文各一个目录；英文包已移出训练目录，训练记录和矩阵仍在原位 |
| 当前两个模型的机械诊断 | [nevir-english-diagnostic-20260907/](../runs/post_recall/nevir-english-diagnostic-20260907/README.md) | `diagnostic/` 保存聚合统计、逐题分数；`A/`、`English/` 分别保存版本矩阵及追踪；`checks/` 是工程检查日志 |
| 已生成的盲审材料 | [英文 diagnostic/review/README.md](../runs/post_recall/nevir-english-diagnostic-20260907/diagnostic/review/README.md) | 公共表单在 `reviewer_1/`、`reviewer_2/`；匿名对应在 `private/`。尚无人工作答，不能当金标 |
| 历史模型和诊断参照 | [同特征重训目录](../runs/post_recall/nevir-ltr-validation-20260907/README.md)、[旧 A/B 诊断目录](../runs/post_recall/nevir-offline-diagnostic-20260907/README.md) | 历史 B 在 `training-preparation/training/model-b/`；旧诊断与当前英文诊断不是一套结果 |
| 可读结论 | [报告选读中的英文研究](reports/REPORT_INDEX.md#英文研究与-nevir) | 正式报告引用上述产物；开发比较和机械诊断不能写成独立测试收益 |

`nevir-ltr-validation-20260907/` 是**历史实验与当前输入共存**的目录，不能整目录删除。其确认材料已经用于历史评价；本轮盘点只核对路径，不读确认／Test 的逐题内容。

## 3. 哪些已经有备份，哪些没有核实

已核对[既有备份目录](../../LinkRag-Eval-restructure-backups/20260906-122751/)中的文件、原 manifest 与 tar 成员目录，未解包或重建：

- `source-before-restructure.bundle`：重构前源码与本地标签；不包含当前未提交工作。
- `protected-research-artifacts.tar`：当时纳入的 Robust Fusion 运行、派生材料、人工材料与部分论文，含旧 Internal v6 的四个 SQLite 文件。已经从工作树消失的 R2 路径可在其成员目录中定位；具体恢复仍按[恢复说明](plans/runtime-simplification-2026-09-06.md#recovery)。
- **该归档不包含** `runs/post_recall/`、`data/post_recall/`、`models/english-baseline/`、公共下载、下载模型缓存、根级工作数据库及密钥。不能用它证明 9 月 7 日英文实验已有备份；旧 Internal v6 数据库也不能替代当前库。
- `linkrag-eval-sqlite-share-20260827/` 只保存旧时点的三个 SQLite 副本，不含远端向量，也不含后续 NevIR 独立数据库。

本轮没有创建新备份，未核实其他备份渠道。后续若做保全，应覆盖当前未提交源码、两个模型包及对应输入／运行证据；不因已有旧归档就先删工作副本。

## 4. 历史产物处理

2026-09-07 已按负责人要求清理下表前三项，其余保留。删除前目录合计占盘约 **3.223 GiB**；大小不是持续维护的容量统计，也不等于已测量文件系统实际释放空间。

| 对象与位置 | 判断 | 依据与删除影响 |
| --- | --- | --- |
| 三个失效历史链接：`human_tasks/r2-adjudication/{START_HERE.html,relation,similarity}` | 已删除 | 仅删除失效链接，未删除原始提交；已同步两个目录 README，旧指南查 Git、R2 材料查已有 tar |
| `.pytest_cache/`、`.ruff_cache/`、`.import_linter_cache/`，合计约 380 KiB | 已清理 | 自动生成的工具缓存，不是实验日志或模型缓存；工具以后可能重新生成 |
| `data/robust_fusion/models/huggingface/`，约 3.2 GiB | 已清理 | 当前源码、脚本和英文实验输入未发现对该缓存的依赖；四个模型 ID 与 snapshot revision 保存在下表。权重本身不保留，本轮未验证上游仍可下载 |
| `data/robust_fusion/public/`，约 4.1 GiB，其中 T2Ranking 约 3.5 GiB | 暂不删 | 包含暂停 T2 接入的原始输入及历史数据来源；既有备份未覆盖，不能因研究转英文就当作无用副本 |
| 历史 B 与 legacy 控制模型包，合计约 144 KiB | 保留 | 分别位于上表同特征训练目录和 `nevir-english-features-20260907/comparison/legacy/model-b/`；用于解释权重重训及规则适配对照，占用很小，不列为当前工作模型 |
| 当前／历史 NevIR 候选、分数、追踪、检查日志与 `before-code/` | 保留 | 包含当前共享输入、历史负结果和旧行为回归依据；部分源码当时尚未提交，不能假定可从 Git 还原，也未被 9 月 6 日归档覆盖 |
| `data/robust_fusion/derived/`、`internal_stress_v6/`、`runs/robust_fusion/` | 保留证据 | 派生标签、来源／曝光记录和历史实测，不是仅靠再次下载即可恢复的公共缓存；备份有部分覆盖，不等于现有文件全部可删 |
| `runs/` 内 SQLite 与 `linkrag-eval-sqlite-share-20260827/` | 保留 | 工作库与旧时点一致性副本职责不同，没有确认新的等价恢复副本。T2 的 `-wal`／`-shm` 不能按普通日志单独删除 |
| `docs/papers/` 的相似题名 PDF、`.ai/` 的旧共享资料 | 暂不整体清理 | 同题可能是不同论文版本，旧助手资料也含通用能力；本轮只核对位置，没有完成内容替代与引用审查 |

本次没有扩大到公共数据、两个当前 LambdaMART 基线、历史控制模型、数据库、实验候选或原始结果。

### 旧下载模型的版本记录

以下取自清理前本地缓存的 snapshot 目录，用于追溯版本；它们不是两个 LambdaMART 基线，也不是权重备份。本轮未核验上游是否仍可下载。

| 模型 ID | Snapshot revision |
| --- | --- |
| `Qwen/Qwen3-Reranker-0.6B` | `e61197ed45024b0ed8a2d74b80b4d909f1255473` |
| `intfloat/multilingual-e5-base` | `d128750597153bb5987e10b1c3493a34e5a4502a` |
| `jinaai/jina-reranker-v2-base-multilingual` | `9cfeff2df7d40d1b78e75e5e9cebec92a99813c9` |
| `sentence-transformers/distiluse-base-multilingual-cased-v2` | `bfe45d0732ca50787611c0fe107ba278c7f3f889` |

## 5. 同级临时工作树与备份（2026-09-09 核对）

以下 `../LinkRag-Eval-pr-*` 是为隔离提交和 PR 建立的 Git worktree，共用本仓库 Git 历史，不是新的评测项目。清理前，三者 HEAD 均等于对应 PR 的最终 head，完整文件树也与该 PR 的合并结果相同；工作区干净，没有未跟踪或被忽略的本地产物。源码、脚本、测试、配置和文档未发现依赖这些临时路径。

| 同级目录 | 原用途及已合并 PR | 盘点时占盘 | 当前状态 |
| --- | --- | ---: | --- |
| `../LinkRag-Eval-pr-research-foundation/` | [研究基础整理 #5](https://github.com/ql-link/LinkRag-Eval/pull/5) | 4.8 MiB | 已按负责人授权清理目录及 worktree 登记 |
| `../LinkRag-Eval-pr-doc-cleanup/` | [研究文档清理 #6](https://github.com/ql-link/LinkRag-Eval/pull/6) | 3.7 MiB | 已按负责人授权清理目录及 worktree 登记 |
| `../LinkRag-Eval-pr-nevir-review/` | [条件聚合与盲审 #11](https://github.com/ql-link/LinkRag-Eval/pull/11) | 4.5 MiB | 已按负责人授权清理；其中 runs 只有随 Git 的入口，不含本地实验数据 |
| `../LinkRag-Eval-restructure-backups/` | §3 所述重构前源码 bundle、历史研究 tar 及 manifest | 111 MiB | 历史恢复材料，继续保留；它不覆盖当前 NevIR 本地产物 |

另有系统临时目录下的 `linkrag-upstream-pr-ntn90g38/worktree`，对应已合并 [引号／准入修复 #12](https://github.com/ql-link/LinkRag-Eval/pull/12)。源码树与合并结果一致，无未提交源码，仅有 Python／pytest／Ruff 缓存，约 10 MiB，也属于完成用途的临时工作树。

负责人随后明确授权清理三个同级 `LinkRag-Eval-pr-*` 目录。再次核对未提交、未跟踪及被忽略产物为空后，已用 `git worktree remove` 逐一移除，并确认三个目录和对应登记均不存在。分支与提交历史保留；主仓库、历史备份及上述系统临时工作树保持。容量为清理前 `du -sh` 读数，不含共用的主仓库 `.git`，不等于实测文件系统释放量。
