# 历史文档归档

本目录保存已被当前架构或实施方案替代的历史设计，只用于追溯决策背景，不作为当前实现依据。

## design-v1

`design-v1/` 来自 monorepo 时期的 `.specs/rag-quality-eval/`，包含早期框架、存储、灌库、
MinIO、Phase 0-3 和趋势看板设计。其中部分内容依赖生产写 pipeline、生产存储或旧数据模型，
与独立评测仓库的当前边界不一致。

当前替代关系：

| 历史主题 | 当前依据 |
| --- | --- |
| 存储、灌库和隔离 | [解耦架构](../architecture/decoupling-plan.md) 与 [AGENTS.md](../../AGENTS.md) |
| 黄金集生成和评测口径 | [Golden V2](../plans/golden-v2-realistic-evaluation.md) |
| Rerank、Query 重写和融合 | [LambdaMART 实验](../experiments/ltr-fusion-v1.md) |
| 项目完成度 | [当前开发状态](../CURRENT_STATUS.md) |

归档文档不再维护。需要恢复其中的设计时，应重新核对当前代码、依赖边界和实测报告，
不能直接复制历史方案。
