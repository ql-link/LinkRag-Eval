# LinkRag-Eval 文档中心

判断项目进度以 [CURRENT_STATUS.md](CURRENT_STATUS.md) 为准；实现约束见 [AGENTS.md](../AGENTS.md) 和[解耦架构](architecture/decoupling-plan.md)。实验报告只证明对应数据、输入和参数下的结果，文档位于 `plans/` 不等于它仍是执行计划。

## 阅读顺序

1. [当前状态](CURRENT_STATUS.md)：项目级进度、未决工作与下一步。
2. [交接说明](HANDOFF.md)：工程基线、当前研究边界和历史保留纪律。
3. [研究讨论与独立审查](plans/research-direction-review-2026-09-06.md)：原问题、不同审查意见与回应；具体方法保持暂定。
4. [运行链路简化记录](plans/runtime-simplification-2026-09-06.md)：当前删除、简化和必要保留项；[前次重构记录](plans/research-restructure-execution-2026-09-06.md)仅保存当时处理。
5. [文档目录](DOCUMENT_CATALOG.md)：各文档的使用身份。

## 目录职责

| 目录 | 用途 | 阅读规则 |
| --- | --- | --- |
| `architecture/` | 当前工程架构 | 随实现维护，与 AGENTS 的强制边界共同使用 |
| `plans/` | 实施计划、研究讨论及保留原路径的旧协议 | 先查当前状态与文档目录，区分暂定、活动及历史身份 |
| `experiments/` | 已有实验与候选方案记录 | 区分历史结果、工程可用性和未验证假设 |
| `reports/` | 阶段报告与统一索引 | 原报告与证据保留，不覆盖成新一轮结果 |
| `archive/` | 历史导航与早期设计 | 只用于追溯，不据此恢复旧执行顺序 |

## 工程与证据入口

- [LambdaMART 三路融合](experiments/ltr-fusion-v1.md)：已有特征、训练及评测历史；包括直接 Rerank 和分数特征的负结果。
- [Golden V2 真实召回评测](plans/golden-v2-realistic-evaluation.md)：已有数据构建、候选池与标注纪律；其历史人口和阶段配置不自动沿用到新研究。
- [Query 重写配对基准](experiments/query-rewrite-benchmark-v1.md)与[Query 软分流候选](experiments/query-soft-routing-candidates.md)：已有实验和候选深度选择记录。
- [报告索引](reports/REPORT_INDEX.md)：阶段产物的完整导航。
- [人工任务说明](../human_tasks/README.md)：当前无活动任务，不建立空注册表或预设校验流程。

## 历史资料与恢复

[Robust Fusion 历史导航](archive/robust-fusion/README.md)汇总保留在原路径的 R1／R2、Gate、Internal、相似度与人工审查协议。旧正文保留，退出活动执行身份；R1 的 `INCONCLUSIVE` 和 R2 的待仲裁状态不因重构而改变。

[早期归档说明](archive/README.md)对应 monorepo 迁入的 `archive/design-v1/` 设计，其旧存储和阶段划分可能已被当前架构替代。

重构前标签为 `research-pre-restructure-20260906`。源码可从该标签在独立目录恢复核对；Git 忽略的证据需使用独立备份及清单，不能仅靠 Git 恢复。保全位置与验证见[执行记录](plans/research-restructure-execution-2026-09-06.md)。
