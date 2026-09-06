# 文档目录与使用身份

本目录回答“有哪些文档，以及现在如何使用”。它不另行维护实验完成度或下一步；项目进度以 [CURRENT_STATUS.md](CURRENT_STATUS.md) 为准。文档已经写完、文件仍在 `plans/`、历史报告已有结论，均不表示相应流程仍待执行。

## 当前入口与工程约束

| 文档 | 使用身份与职责 |
| --- | --- |
| [项目 README](../README.md) | 项目介绍、工程能力与顶层导航 |
| [实现约定](../AGENTS.md) | 强制依赖边界、存储隔离、配置与测试规则 |
| [文档中心](README.md) | 推荐阅读顺序与目录职责 |
| [交接说明](HANDOFF.md) | 工程基线、研究边界、历史材料与恢复方式 |
| [当前状态](CURRENT_STATUS.md) | 项目级进度、未完成工作与下一步的唯一入口 |
| 本目录 | 文档用途与历史替代关系 |
| [解耦架构](architecture/decoupling-plan.md) | 当前工程职责与生产依赖方式；旧 Step 0–6 只作迁移历史 |
| [人工任务说明](../human_tasks/README.md) | 当前无活动任务；旧入口仅用于追溯 |

## 本次研究讨论与重构

| 文档 | 使用身份与限制 |
| --- | --- |
| [研究方向独立审查与回应](plans/research-direction-review-2026-09-06.md) | 讨论记录与历史证据；保留不同意见和未决事项，方法尚未定案 |
| [召回后关系融合概念稿](plans/post-recall-relational-fusion-concept-2026-09-05.md) | 早期候选方案及论证记录，不是冻结的实施计划 |
| [重构盘点清单](plans/research-restructure-inventory-2026-09-06.md)与[逐文件 JSON](plans/research-restructure-inventory-2026-09-06.json) | 保留盘点时的分类和条件，不覆盖成删除执行结果 |
| [重构执行记录](plans/research-restructure-execution-2026-09-06.md) | 实际授权、保全、分段变更、提交与验证；进度仍在当前状态维护 |

研究范围是三路召回后的固定候选集合，利用已有可见候选信息和逐路分数／排名探索融合或重排。具体方法、窗口、阈值、比较规则和实验版本仍为暂定。重构不将任一候选方案升级为强制主线。

## 已有工程方案与实验记录

| 文档 | 使用身份与限制 |
| --- | --- |
| [Golden V2 真实召回评测](plans/golden-v2-realistic-evaluation.md) | 既有数据构建、标注与评测方案；历史人口、规模与阶段配置不自动成为新研究要求 |
| [LambdaMART 三路融合](experiments/ltr-fusion-v1.md) | 38 维 v3、训练与评测历史；保留直接重排／分数特征负结果，具体使用范围看原报告 |
| [Query 重写配对基准](experiments/query-rewrite-benchmark-v1.md) | 已有配对实验及负结果，不作为当前默认链路的执行计划 |
| [Query 软分流候选](experiments/query-soft-routing-candidates.md) | 已有候选深度与分流实验，不因文档保留而重新选参 |
| [质检模块全解](reports/LinkRag-Eval-质检模块全解.md) | 历史系统说明，路径保留；当前架构以 AGENTS 和解耦架构为准 |

## Robust Fusion 历史协议与文献

[Robust Fusion 历史导航](archive/robust-fusion/README.md)逐项列出原科研／工程协议、研究清单、R1→R2 继承、相似度测量、Internal、标注、source lock、自动执行、仲裁与发表治理文件。它们退出活动执行身份，原文件仍保留原路径与字节，便于追溯原报告。旧正文中的 Gate、下一步或授权条件属于当时协议，不能据此启动旧流程。

文献与证据仍可使用，但应区分文献主张与项目实测：

- [文献综述](plans/robust-fusion-literature.md)：历史综述与来源；具体时效和论断应按新的问题核验。
- [证据卡片](plans/robust-fusion-evidence.md)：历史证据组织，不自动继承其研究主张或方案选择。
- 原人工登记 `docs/plans/robust-fusion-human-task-registry.json`、HTML、symlink、提交与锁均保留为历史；当前没有活动任务，不保留空注册表。

R1 历史结果仍为 `INCONCLUSIVE`；R2 最后记录状态仍为待仲裁。退出流程不等于完成验证，也不抹掉失败、负结果或未决事项。

## 阶段报告与原始证据

完整路径与用途集中在[报告索引](reports/REPORT_INDEX.md)，本目录不再重复维护第二套报告清单。重点入口包括：

| 报告 | 证据用途 |
| --- | --- |
| [Blind v4 验收](reports/blind_v4_final_acceptance_2026_07_24.md)与[Blind v5 生产契约验收](reports/blind_v5_production_contract_acceptance_2026_07_28.md) | 历史一次性评测与工程使用边界；不重新用于选参或新方法验证 |
| [池化重标可靠性](reports/label_reliability_pooled_relabel.md) | 单正例 qrels 与漏标问题 |
| [Golden V2 阶段实证](reports/golden_v2_realistic_991004_run_2026_07_10.md) | 数据、候选池与标注流程的既有证据 |
| [候选快照字段审计](reports/robust_fusion_candidate_snapshot_field_gap_audit_2026_08_28.md) | 历史字段缺口与契约核对，不等于新实验已具备输入 |
| [R1 相似度失败诊断](reports/robust_fusion_r2_similarity_failure_diagnostic_2026_08_29.md) | 文件名含 R2，但记录的是 R1 失败诊断及后续修订依据 |
| [R2 人工审查前仲裁状态](reports/robust_fusion_r2_human_review_pre_adjudication_2026_08_29.md) | 保留未完成仲裁的事实，不视为最终效度结论 |
| [资产恢复与对账](reports/sqlite_share_restore_and_asset_reconciliation_2026_08_28.md) | 存储、来源与资产身份，不是新研究的确认性分母 |

报告、标签、原始人工提交、锁与运行证据保留原路径；新产物使用新目录或时间戳。历史汇总可帮助理解项目，但不应读取封存原始结果来选方法、调参或生成新结论。

## 早期设计与版本恢复

[早期归档说明](archive/README.md)保留 `archive/design-v1/` 的 monorepo 设计与替代关系。旧存储、MinIO、阶段划分与迁移要求仅供追溯。

本次重构前源码保全于标签 `research-pre-restructure-20260906`（`4d31f18`）；旧版本可以在独立目录恢复核对。Git 忽略的证据需要独立 tar 与 manifest，Git 标签本身不包含这些文件。具体保全范围、位置和实际删除映射见[执行记录](plans/research-restructure-execution-2026-09-06.md)。
