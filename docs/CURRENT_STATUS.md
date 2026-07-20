# 当前开发状态

> 更新时间：2026-07-20
> 本页是项目级进度的唯一维护入口。专题文档中的历史状态和实验结论不得覆盖本页。

## 总体结论

评测研发主链路已经完成，当前处于候选覆盖优化、独立 Blind 复验和生产化准备阶段。
LambdaMART 已证明相对固定 Hybrid 有收益，但尚未接入生产默认链路。

| 范围 | 状态 | 说明 |
| --- | --- | --- |
| 项目解耦 Step 0-4 | 完成 | 独立 MySQL、eval Qdrant、ProductComputer、SQLite FTS5 BM25 已落地 |
| 项目解耦 Step 5 | 主体完成 | 代码、CLI、报告、结果台账和 import 边界已迁入；仍需最终 clean run 固化 |
| 项目解耦 Step 6 | 代码完成、验收未关闭 | 已从 Qdrant BM25 转向 SQLite FTS5；缺三路 clean run 和 BM25 delta |
| Golden V2 | 主链路完成 | chunk 粒度、候选池、标注、QC、仲裁、tune/blind、20k 评测已落地 |
| 2000 条 LTR 数据 | 完成 | 420 条基集加 1580 条严格新增样本 |
| LambdaMART 实验 | 完成首轮独立验证 | Blind v2 Recall@10 从 20.95% 提升到 27.62% |
| LambdaMART 生产化 | 未完成 | 缺在线特征、模型版本、延迟、降级、Shadow 和回滚验证 |
| 10 万背景语料 | 暂缓 | 当前先完善 20k；不属于本轮阻塞项 |

## 已固化结果

- 2000 条训练候选并集覆盖率为 95.25%。
- Tune OOF：固定 Hybrid Recall@10 为 35.90%，2000 条 LambdaMART 为 43.55%，提升 7.65pp。
- 全新 Blind v2 共 210 条，Query 和正标签与历史集合隔离。
- Blind v2：固定 Hybrid Recall@10 为 20.95%，1050/2000 模型均为 27.62%。
- 2000 模型相对 1050 模型没有提高 Blind v2 Top10 命中数，但 MRR@10 从 7.13% 提升到 8.46%。
- Blind v2 三路候选并集覆盖率为 89.05%，23 条在排序前已丢失，排序模型无法补回。

不同报告的数据分布、Query 数量和候选参数不同，只能在同一报告内比较变化量。
历史四域 `recall@10 ~= 0.901` 等价门槛不能与 Hard Blind v2 的绝对值直接比较。

## 尚未关闭的验收项

1. 审计 Blind v2 候选缺失的 23 条，优先处理 `short_keyword`、`alias` 和 `number_time`。
2. 加强 `exact_identifier` 数据门禁，确保 Query 真正包含编号、日期或版本号。
3. 优化候选召回后冻结参数，创建未曝光 Blind v3；Blind v2 只保留作回归集。
4. 重建 SQLite BM25 sidecar，取得 `failed_sources=0`、`zero_ranked=0` 的三路 clean run，并记录 BM25 delta。
5. 若进入生产试验，实现 LambdaMART 模型序列化、在线特征、版本管理、降级、Shadow 和回滚。
6. 推送并启用 CI workflow；当前 `.github/workflows/ci.yml` 尚未纳入远端分支。

## 非阻塞增强项

- 第三判官自动仲裁。
- 数十万或百万规模时将 Alt Embedding sidecar 升级为 ANN/HNSW。
- 10 万背景语料分批扩容。

## 相关文档

- [解耦架构](architecture/decoupling-plan.md)
- [Golden V2 计划](plans/golden-v2-realistic-evaluation.md)
- [LambdaMART 实验](experiments/ltr-fusion-v1.md)
- [统一报告索引](reports/REPORT_INDEX.md)
