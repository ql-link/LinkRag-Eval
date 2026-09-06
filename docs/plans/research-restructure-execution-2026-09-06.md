# 研究重构执行记录

> 负责人已授权按[盘点清单](research-restructure-inventory-2026-09-06.md)推进实际删除／重构，并为每一步做好版本管理。原清单与 JSON 保留其盘点时身份，不覆盖成执行结果。
> 本记录保存执行依据、版本和验证结果；当前进度统一见 [CURRENT_STATUS](../CURRENT_STATUS.md)。研究方法保持暂定，不在本次清理中定义替代算法。

## 范围与保留边界

- 移除旧流程的活动执行身份，并在依赖闭合和源码保全后退役 D10–D14。
- H01／H02 只抽离现有可复用的纯函数和人工入口校验，不建立新研究框架。
- 保留共享召回／存储、依赖 pin、现有 38 维 LambdaMART、冻结模型和回退、核心契约测试。
- 旧协议、历史报告、原始人工提交、锁、源数据和单次运行证据保留原路径与字节。R1 仍为历史 `INCONCLUSIVE`；R2 最后记录状态仍为待仲裁，退役不等于完成仲裁。
- 不读取封存结果作方法选择，不运行旧 finalizer／readiness／Gate／Blind／编码 API，不连接或修改生产服务。
- 仅删除 D01 显示元数据及 D02 已核对副本；公共下载、模型缓存、SQLite／sidecar、分享包和仓库外共享缓存不进入删除范围。

## S0：保全重构前状态

版本：`4d31f18`，提交信息 `chore(restructure): 保存重构前工作区与审阅清单`。
本地保全标签：`research-pre-restructure-20260906`。

该提交原样保存开始时的 6 个 tracked 修改，以及 13 个未跟踪路径（含本次盘点的两份文件）。没有把原始数据或密钥提交到 Git。基线提交是保全状态，不声称旧研究测试已通过；staged whitespace 检查发现旧 `robust-fusion-human-task-entrypoints.md` 末尾已有空行，为保持旧文档字节未在此阶段修正。

独立备份位置：`/Users/kawauso/Documents/Projects/LinkRag-Eval-restructure-backups/20260906-122751/`。

| 产物 | 范围／校验 |
| --- | --- |
| `source-before-restructure.bundle` | 2,242,153 字节，包含保全提交、标签及当时全部本地 Git refs；`git bundle verify` 通过。 |
| `protected-research-artifacts.tar` | 113,653,760 字节，922 个成员；研究 runs、derived、Internal Dev、人工作业链接、两份 PDF 与显示元数据。逐成员与源文件 SHA-256／symlink 目标一致。 |
| `manifest.json` | 每个保全路径的大小、mtime、SHA-256 或链接目标；记录未纳入备份且不修改的数据库、公共下载、模型缓存、密钥与外部缓存。 |

备份仅以字节复制和散列核对进行，不解析研究记录，不恢复已删除或撤回的结果。当前源码可由保全标签恢复；ignored 证据可从独立 tar 按 manifest 核对。数据库、公共下载和模型缓存仍保留原处，不因没有复制进入 tar 而获得删除资格。

## 后续执行分段

| 分段 | 变更范围 | 必要验证 |
| --- | --- | --- |
| S1 文档与入口 | 当前导航、历史原协议索引、停用旧任务的活动注册；原 registry／HTML／symlink 保留 | 文档链接、原协议哈希、活动任务不再指向 R2／Gate |
| S2 通用能力抽离 | 数值／向量诊断、候选证据序列化、人工入口校验与对应测试 | 临时数据单测，无旧 release／标签／正式目录依赖 |
| S3 旧流程退役 | D10–D14 完整依赖组；被迁移替代的 H01／H02 旧源码／包装 | 精确删除台账、无残留运行导入、所有删除文件可从 S0 找回 |
| S4 低风险去重与描述整理 | 两个低风险文件、文献映射、共享实现中的旧 Gate 文字 | 主 PDF 哈希不变、历史计数仍按历史口径说明 |
| S5 收口验证 | 保留链路、导入边界、模型契约、索引和保护资产 | 单元／契约检查、保全资产未变、逐项执行映射、工作区版本清晰 |

各段完成后在本记录追加实际提交或对应记录，并在 CURRENT_STATUS 更新当前状态；不以空提交充当完成证明。

## S1：当前入口与历史身份

当前入口改为“工程基线／暂定研究讨论／历史协议”三类导航，旧协议不再提供当前任务顺序。21 份 A01 原协议保持原路径与字节，另建历史索引。AGENTS 与架构的过时 BucketRouter、Qdrant BM25 和旧迁移待办说明已对齐保留实现；未改生产依赖 pin 或扩大生产 import 白名单。

新 `human_tasks/registry.json` 的活动任务和计划接触点均为空；旧 registry、HTML 与三个链接保留。顶层人工作业说明和 R2 目录新 README 提醒历史身份，R2 仍为待仲裁。报告索引明确历史证据用途，并校正文件名含 R2 的失败诊断实际分析 R1 的说明；原报告未改。

验证：12 份当前入口共 168 个本地链接存在，21 份原协议与 S0 逐字节一致；报告索引单测 2 passed；当前空 registry 检查 PASS，读取输入数为 0。该检查不读取历史注册表或人工提交。

S1 版本：`329cdcd`（`docs(restructure): 分离当前研究入口与历史协议`）。

## S2：通用能力抽离

新增四个叶子模块及其测试，不增加方法框架：`compute/similarity.py` 保留文本规范化、float32 指纹及 float64 余弦；`compute/vector_diagnostics.py` 保留描述性向量诊断，去除旧流程 policy ID；`retrieval/candidate_evidence.py` 只投影候选证据和校验已知评价字段；`human_task_entrypoints.py` 与新 checker 使用显式注册表。

候选工具显式接收语料允许集和完整路由列表，不读取 release、标签、模型或存储。候选与逐路顺序、分数、缺失值及并集检查保留；摘要 `route_hit_counts` 明确统计当前 `route_hits`，不同于生产响应中过滤前的同名来源计数。字段名护栏不是自由文本泄漏检测器。

独立复核发现原人工校验器会跟随工作区内的文件链接，因此迁出时补充角色目录归属检查：所有输入和已有／断链输出先验证，再读取任何 CSV 行数。checker 不仲裁答案，但显式指定非空 registry 时会读取对应指南和输入 CSV；默认空 registry 不触及历史数据。

验证：四份新单测 **64 passed**；数值模块原有 12 个函数在抽离时 AST 一致，人工校验器的上述隔离修复另有临时目录负测。迁移前后工具均未运行编码器或旧研究阶段。

S2 版本：`eb5f4d6`（`refactor(restructure): 抽离通用证据工具并收紧人工入口隔离`）。

## S3：旧流程依赖组退役

已退役 D10–D14 共 86 个源码／脚本／测试，以及 H01／H02 中被抽离替代的 10 个旧入口，共 **96 个 tracked 文件**。逐文件路径由原清单及本次 Git 删除记录完整保存，所有删除前字节均与 S0 一致。完整逐项处置台账在 S5 汇总。

新增退役的 10 个 H01／H02 旧路径：

- `scripts/check_robust_fusion_human_task_entrypoints.py`
- `scripts/diagnose_robust_fusion_dense_replay.py`
- `scripts/probe_robust_fusion_route_contract.py`
- `src/linkrag_eval/robust_fusion/__init__.py`
- `src/linkrag_eval/robust_fusion/human_task_entrypoints.py`
- `src/linkrag_eval/robust_fusion/replay_contract.py`
- `src/linkrag_eval/robust_fusion/similarity.py`
- `tests/unit/test_robust_fusion_human_task_entrypoints.py`
- `tests/unit/test_robust_fusion_replay_contract.py`
- `tests/unit/test_robust_fusion_similarity.py`

两个 probe／diagnose 包装随旧运行流程退役，只保留其通用向量诊断能力；旧 `__init__` 不保留 facade。相似度、向量诊断和人工入口的旧模块／测试由 S2 新路径替代。候选证据只抽离序列化及字段检查，不携带 Internal release、构造、标注或数据资格流程。

删除前全仓 Python AST 检查确认：保留 src／scripts／tests 没有导入待退役模块；旧版本间依赖按完整组处理。此阶段没有调用旧 finalizer／readiness／measurement，也未恢复任何已撤回制品。

退役后验证：保留单元测试与生产 import 边界 **399 passed**，固定生产依赖契约 **19 passed**；仅有既有 SWIG 弃用警告。`lint-imports --no-cache` 可执行并通过；其配置当前没有自定义 forbidden contract，实际生产白／黑名单由已通过的 `tests/test_import_boundary.py` 强制，不能把 0 broken 单独当作边界证明。运行目录、CLI／CI／保留源码中没有旧工作流运行导入。

为使这些保留检查与活栈隔离，本阶段同时修复两处测试：vector-store 配置测试不再读取 `.env.eval`，并注入 fake 底层 store；召回装配契约保留真实 Qdrant 客户端类型，但关闭构造时的兼容性后台联网检查。未改生产客户端行为。

S3 版本：`0db80e8`（`refactor(restructure): 退役旧研究流程并保留隔离契约验证`）。

## S4：低风险去重与共享说明

按 D01／D02 删除两个 ignored 文件；两者均已在 S0 的独立 tar 中逐字节保全。Git 不跟踪其删除，因此本记录和最终逐项台账保存确切身份，不能宣称仅靠 Git 可恢复这些文件。

| 已删除路径 | 字节数 | 删除前 SHA-256 |
| --- | ---: | --- |
| `docs/.DS_Store` | 8196 | `1b32429e16d4967af07b3e5244630353a9ad8f14052d6dd65cb4669c4fc7e6d9` |
| `docs/papers/Language Model Re-rankers are Fooled by Lexical Similarities〔重复副本〕.pdf` | 604585 | `1e80e5bfc6352d932f7ccbd72e9b9ac13bfedda501bf0a52256c5c745cbe95d6` |

保留的主 PDF `docs/papers/Language Model Re-rankers are Fooled by Lexical Similarities.pdf` 仍为 604,585 字节，SHA-256 为 `1e80e5bfc6352d932f7ccbd72e9b9ac13bfedda501bf0a52256c5c745cbe95d6`。文献卡只修正副本链接、增加去重说明；历史 48 文件预检／OCR 计数仍标为 2026-08-28 快照，当前 47 PDF／45 实体，不重新解释论文结果。其他正式版／预印本版本对不删除。

共享实现只去除过时 Gate 用语、解释不再支持的 Qdrant BM25 配置；Dense／Sparse 兼容客户端保留。现有 38 维特征、冻结模型、候选适配、依赖 pin、CI 和存储接口未回退。

S4 版本：`f040ae1`（`chore(restructure): 清理重复资产并更新共享实现说明`）。

## S5：最终对账与验证

[实际处置台账](research-restructure-disposition-2026-09-06.json)覆盖原盘点的 **509 个路径**，记录每项原分类、实际处置、保全／当前指纹和恢复位置；原盘点文件未改。96 个 tracked 退役路径均可由 S0 找回，2 个 ignored 删除项由独立 tar 找回。实际保留不是漏做：依赖 pin、CI、共享 judge、数据库／sidecar、模型缓存和历史研究原始资产没有删除或回退理由。

保护资产复核：S0 的 922 个成员中 **919 个文件哈希／链接目标不变**；其余三项恰为两项低风险清理和顶层 `human_tasks/README.md` 的活动入口改写。原 R2 registry、HTML、三个浅入口链接、人工提交和锁均未变化。21 份 A01 原协议、16 个 K02 基线／模型／核心测试路径和 54 份未修改的 K01 历史证据与 S0 一致；文献地图唯一变化是 S4 的副本映射说明。

独立终审未发现保留代码中的旧模块导入或退役脚本调用。终审另纠正 AGENTS 对依赖安装的旧描述：rag 实际由显式安装和 CI 固定 SHA，不在 pyproject dependencies 中；候选适配器只将旧调用方名称改为通用描述，没有改变接口或行为。

| 检查 | 结果／范围 |
| --- | --- |
| `PYTHONDONTWRITEBYTECODE=1 RUN_EVAL_INTEGRATION=0 .venv/bin/python -m pytest tests/unit tests/test_import_boundary.py -q -p no:cacheprovider` | 399 passed；含通用抽离后的 64 个测试及真实生产 import 边界扫描。 |
| `PYTHONDONTWRITEBYTECODE=1 LINKRAG_EVAL_REQUIRE_RAG=1 RUN_EVAL_INTEGRATION=0 .venv/bin/python -m pytest tests/contract -q -p no:cacheprovider` | 19 passed；保留固定依赖的计算、召回与 LTR-v3 模型契约，缺包强制失败；未运行集成活栈。 |
| `PYTHONDONTWRITEBYTECODE=1 .venv/bin/lint-imports --no-cache` | 可执行，162 files / 726 dependencies；当前 0 自定义 contract，不能代替已通过的源码边界测试。 |
| 新增／修改 Python 的 Ruff 与 `git diff --check` | 通过；历史原文的既有格式不被重新改写。 |
| 报告索引与当前人工作业 registry | 通过；活动任务、计划接触点、输入读取数量均为 0。 |
| 导入与保护资产核验 | 96 个退役路径不存在；无保留运行依赖，原历史资产指纹保持上述一致。 |

测试只出现已有 SWIG 弃用警告。未训练、未运行编码 API／旧 Gate／readiness／finalizer／正式研究评测，未 push；没有获得或声称当前版本的远端绿色 CI。研究仍停留在明确边界下的暂定方法讨论，后续先讨论有限的评测与方法选择，不以完成旧 R2 仲裁作为前置条件。

S5 的最终文档与对账作为单独本地提交保存；其提交号可由 `git log --oneline -- docs/plans/research-restructure-disposition-2026-09-06.json` 获取，避免在提交内容中自引用尚未生成的哈希。

最终补充核对：安装的 `tolink-rag` 分发元数据为非 editable Git 安装，commit 与 requested revision 均是 `861f24810c3482ec0d86768a24f952b1e08ae675`。13 份本轮新增／修改 Markdown 的 221 个本地链接全部存在；最终报告索引和空 registry 再次检查通过。最终适配器注释更正前后可执行 AST 一致，因此没有因文案变化重跑整套代码测试。
