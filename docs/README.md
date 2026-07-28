# LinkRag-Eval 文档中心

本文档树按职责分类。判断当前实现进度时以 [CURRENT_STATUS.md](CURRENT_STATUS.md) 为准；
判断实现约束时以 [AGENTS.md](../AGENTS.md) 和权威架构为准；实验报告只证明对应数据集和参数下的结果。

## 阅读顺序

1. [实现约定](../AGENTS.md)：依赖边界、存储隔离、配置和测试纪律。
2. [下一对话交接](HANDOFF.md)：冻结决策、最新审计、执行顺序和必读材料。
3. [当前状态](CURRENT_STATUS.md)：完成度、验收缺口和下一步。
4. [文档目录](DOCUMENT_CATALOG.md)：已有文档及其对应工作的完成状态。
5. [解耦架构](architecture/decoupling-plan.md)：项目边界和 Step 0-6 迁移基线。
6. [Golden V2 计划](plans/golden-v2-realistic-evaluation.md)：黄金集、候选池、标注和 blind 纪律。
7. [LambdaMART 实验](experiments/ltr-fusion-v1.md)：融合方案、对照实验和 Blind v3 结果。

## 目录职责

| 目录 | 性质 | 维护规则 |
| --- | --- | --- |
| `architecture/` | 当前权威架构 | 随代码演进维护；冲突时优先级最高 |
| `plans/` | 当前实施方案 | 记录目标、模块、验收标准和未完成工作 |
| `experiments/` | 可复现实验与候选方案 | 必须区分已验证结论和待验证假设 |
| `reports/` | 阶段报告与统一索引 | 历史产物只追加、不覆盖、不删除 |
| `archive/` | 已被替代的历史设计 | 仅用于追溯，不得作为当前实现依据 |

## 当前专题

- [Golden V2 真实召回评测](plans/golden-v2-realistic-evaluation.md)
- [LambdaMART 三路融合](experiments/ltr-fusion-v1.md)
- [Query 重写配对基准](experiments/query-rewrite-benchmark-v1.md)
- [Query 软分流候选](experiments/query-soft-routing-candidates.md)
- [质检模块总览](reports/LinkRag-Eval-质检模块全解.md)（沿用历史报告路径）

## 报告

- [统一报告索引](reports/REPORT_INDEX.md)：收录 `docs/reports/` 和 `runs/` 下的阶段产物及用途。
- 每轮测试使用独立目录或时间戳文件名，禁止覆盖历史报告。
- 更新索引：`python3 scripts/build_report_index.py`。
- 验收索引：`python3 scripts/build_report_index.py --check`。

## 历史资料

[archive/design-v1/](archive/design-v1/) 保存从 monorepo 迁入的早期设计。其存储、灌库、
MinIO、阶段划分等内容可能已被当前架构替代，阅读前先看
[归档说明](archive/README.md)。
