# 文档目录与使用身份

项目进度只维护在 [CURRENT_STATUS.md](CURRENT_STATUS.md)。本目录说明保留文档的用途；旧方案和已经完成的盘点不再作为当前入口。

## 当前入口

| 文档 | 用途 |
| --- | --- |
| [项目 README](../README.md) | 项目介绍、运行检查和顶层导航 |
| [实现约定](../AGENTS.md) | 依赖边界、存储隔离、配置与测试规则 |
| [当前状态](CURRENT_STATUS.md) | 项目进度、研究边界和下一步的唯一入口 |
| [解耦架构](architecture/decoupling-plan.md) | 当前工程组件及生产依赖方式 |
| [研究思路与暂定计划](plans/post-recall-research-plan.md) | 当前问题、候选假设、数据用途、评测与对照逻辑、未决事项；算法尚未冻结，实现进度另见当前状态 |
| [独立审查与回应](plans/research-direction-review-2026-09-06.md) | 研究讨论、项目证据与未决问题；附录 D 保存表示盲点，附录 E 保存问题复现阶段的对齐原文 |
| [运行链路简化与恢复](plans/runtime-simplification-2026-09-06.md) | 工程简化结果、必要保留项和版本恢复位置 |

研究限定在三路召回后的固定候选集合。具体方法、窗口、阈值和实验版本保持暂定；讨论稿不构成实现要求。

## 保留的工程与实证依据

- [Golden V2 真实召回评测](plans/golden-v2-realistic-evaluation.md)：既有数据构建、标注与评测说明；历史规模和阶段参数不自动沿用。
- [LambdaMART 三路融合](experiments/ltr-fusion-v1.md)：现有 v3 与训练、评测历史，包含 Qwen 直接重排和分数特征的负结果。
- [Query 重写配对基准](experiments/query-rewrite-benchmark-v1.md)与[软分流候选](experiments/query-soft-routing-candidates.md)：已有实验和候选方案，不是当前默认执行计划。
- [报告索引](reports/REPORT_INDEX.md)：实际运行结果、失败诊断和人工汇总；本目录不重复列报告清单。
- [文献地图](plans/robust-fusion-literature.md)：既有阅读记录、来源与适用边界；不能据此认定当前方法有效或创新成立。

## 历史材料

[Robust Fusion 历史导航](archive/robust-fusion/README.md)保留解释原数据所需的来源、标签和量表文档。R1 的 `INCONCLUSIVE` 与 R2 的待仲裁状态不因文件整理改变；原始提交和报告继续保留。

已删除的研究总方案、旧执行说明、任务登记、盘点台账及早期关系融合草案通过 Git 历史追溯，不再复制一套工作区归档。具体版本与本地数据备份见[恢复说明](plans/runtime-simplification-2026-09-06.md#recovery)。

[早期设计归档](archive/README.md)仍用于追溯 monorepo 设计。当前没有人工作业，[人工任务说明](../human_tasks/README.md)中的旧入口只作历史；它们不是继续仲裁或运行旧 Gate 的授权。
