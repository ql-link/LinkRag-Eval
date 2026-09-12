# 当前研究数据：英文 NevIR

本页维护数据查找路线；各次实验的用途与文件说明见[实验产物入口](../runs/post_recall/README.md)，进度看[当前状态](../docs/CURRENT_STATUS.md)，实验设计看[研究计划](../docs/plans/post-recall-research-plan.md)。

- **查当前英文模型实际输入，先读 [selection.json](../runs/post_recall/nevir-english-features-20260907/comparison/english/selection.json)**：`input_paths` 是六个输入文件，`train`／`development` 记录数量和排除项；不要根据目录日期或名称猜测。
- 默认查找范围是已有 Train／开发材料与保存候选。确认集、Test 的使用边界见下表；本页不授权扩大评价或重新召回。
- 本页可纳入 Git；数据本体和 `runs/` 产物仍被忽略。其他工作区可能缺少它们，缺失时报告具体路径，不自动下载、重建或替换。

阅读顺序：**官方原始数据 → 项目查询与监督 → 保存候选 → 英文特征与模型 → 开发结果**。

## 1. 官方划分与本项目用途

原始数据在 [post_recall/nevir/](post_recall/nevir/)，来源记录见 [provenance.json](post_recall/nevir/provenance.json)。该目录的 `README.md` 是上游数据说明，不负责本项目的使用记录。

| 项目用途 | 官方来源 | 当前记录 | 使用边界 |
| --- | --- | --- | --- |
| `train` 训练 | Train | 948 对／1,896 查询；1,869 查询进入损失 | 已用于拟合；排除 25 条目标未共同召回、2 条结构冲突查询 |
| `development` 开发 | Validation 的 38 对 | 76 查询，74 条目标共同覆盖 | 已用于选模、早停和诊断，不是独立测试 |
| `confirmation` 历史确认 | Validation 的其余 187 对 | 374 查询，371 条目标共同覆盖 | 已用于历史 A/B 确认并曝光，不作为新方法的独立确认 |
| 官方 Test | Test | 成员已交付 #23 的 E0／融合／N=8 终评聚合，未用于当前英文基线拟合 | [Test 接收范围](../runs/post_recall/nevir-test-final-20260911/README.md)：原候选／监督与编码采集记录已补交并通过 #19 程序验收，成员逐题模型分数仍缺；#20 仅完成离线准备。不得称全局未曝光，不显示逐题内容或据结果调参 |

官方 Validation 不等于本项目 `development`。划分与历史用途依据见[同特征重训报告](../docs/reports/nevir_same38_retraining_2026_09_07.md)；当前训练数量以英文 `selection.json` 为准。

## 2. 当前英文训练实际使用的六个输入

| 用途 | 查询 `queries.jsonl` | 官方偏好监督 `supervision.jsonl` | 完整候选池 `inputs.jsonl` |
| --- | --- | --- | --- |
| Train | [训练查询](../runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment/prepared/train/queries.jsonl) | [训练监督](../runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment/prepared/train/supervision.jsonl) | [训练候选](../runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment/candidates/train/inputs.jsonl) |
| 开发 | [开发查询](../runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment/prepared/development/queries.jsonl) | [开发监督](../runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment/prepared/development/supervision.jsonl) | [开发候选](../runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment/candidates/development/inputs.jsonl) |

共同语料见 [corpus.jsonl](../runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment/prepared/corpus.jsonl)，原段落与匿名 chunk 对应见 [passage-mapping.jsonl](../runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment/prepared/passage-mapping.jsonl)。训练与诊断优先读取上表保存候选，不从语料补入漏召回目标。上述英文基线的特征基于完整候选池计算，损失只使用已标注的指定候选。#23 另有[显式 N=8 弱负例实验](../runs/post_recall/list-collapse-20260910/README.md)，默认关闭；抽取背景的弱标签不能当作人工相关性标注。

这些输入沿用原 `nevir-ltr-validation-20260907` 快照，英文适配没有另建一套查询或候选。监督文件中的配对和来源信息不作为排序特征。

## 3. 英文模型、缓存与结果

| 要找什么 | 直接入口 |
| --- | --- |
| 实际输入、参数、排除项和选模记录 | [英文 selection.json](../runs/post_recall/nevir-english-features-20260907/comparison/english/selection.json) |
| 英文基线身份和特征契约 | [models/english-baseline/manifest.json](../models/english-baseline/manifest.json)；加载方式见[模型入口](../models/README.md) |
| 开发特征缓存 | [development-candidate_difference_v3_en_v1.npz](../runs/post_recall/nevir-english-features-20260907/comparison/english/development-candidate_difference_v3_en_v1.npz)，仅对应英文版本，不与 legacy 混用 |
| 开发完整候选分数 | [dev-predictions.jsonl](../runs/post_recall/nevir-english-features-20260907/comparison/english/dev-predictions.jsonl) |
| 同条件重训比较与解释 | [comparison.json](../runs/post_recall/nevir-english-features-20260907/comparison/comparison.json) → [英文适配报告](../docs/reports/nevir_english_features_2026_09_07.md) |
| 后续诊断的证据与限制 | [离线诊断报告](../docs/reports/nevir_offline_diagnostic_2026_09_07.md)，包含英文模型在原开发快照上的重放 |

当前只维护 `models/chinese-baseline/`（原 A）与 `models/english-baseline/`（英文适配版）。英文模型包已从实验目录移至 `models/`；训练记录、矩阵和分数留在上表原位。历史 B 与 legacy 控制只作追溯，模型身份及旧路径对应统一查[模型入口](../models/README.md)。

其他历史数据在 `data/robust_fusion/`，用途查[历史导航](../docs/archive/robust-fusion/README.md)；不从中自动混入当前英文训练或开发输入。
