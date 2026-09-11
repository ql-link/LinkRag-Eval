# #23 列表诊断与背景 N=8 实验

2026-09-11 接收成员在 `da46a431b93481d910159959a1879f13e1bada0e` 上的交付，接入当前仓库并验证。原包包含 32 文件，完整归档在 [原始交付包](../_handover/issue23-n8-delivery-20260911.tar.gz)；包内 SHA256SUMS 的 31 项及归档后的每个文件均已核对。原项目入口、规则、状态和台账快照只作为历史证据留在归档，不覆盖当前文档。

## 已接入内容

- [results.json](results.json)：成员开发／确认聚合原件，保留不覆盖。
- [background-n8-training/](background-n8-training/)：N=8 的 selection.json 和 model-b/ 完整模型包。
- [baseline-disabled-replay/](baseline-disabled-replay/)：默认关闭重放的 selection.json 和 model-b/；模型权重与现有英文基线一致。
- [evaluate.py](evaluate.py)：接收后补的本地复验入口，原成员同名脚本未交付。
- [acceptance.json](acceptance.json)：本地复验结果；整数精确相同，浮点列表聚合允许 1e-12 绝对误差。
- [实验报告](../../../docs/reports/list_collapse_2026_09_11.md)：结果、代价、历史纠错和证据限制。
- [成员 Test 聚合](../nevir-test-final-20260911/README.md)：独立于本目录已复现的开发／确认。

源码接入 `pairwise_training.py` 及对应单元测试。`--background-negatives` 默认为 0；显式 N=8 时只在 Train 加入确定性抽取的背景候选，标签为 2/1/0，Development 沿用指定两段早停。N=8 是实验模型，不替换 `models/english-baseline/`。

## 本地验证

从仓库根目录运行：

```bash
.venv/bin/python runs/post_recall/list-collapse-20260910/evaluate.py
```

读取已有 76 条开发／374 条确认完整候选，重新生成 E0 与 N=8 的本地分数，并从四份已存确认分数核对 A／B／E0／融合。E0 全池分数与已有缓存精确相同；全部成员开发／确认指标通过复验，模型包的 6 个合成契约向量通过。该命令不训练、不采集、无远端请求，也不读取 Test 逐题。原 results.json 不变；本地生成的评分为 `E0-<role>-scores.jsonl`、`background_n8-<role>-scores.jsonl`。

确认严格正确：A／B／E0／融合／N=8 分别 193／201／208／189／198（分母 371）。N=8 首选段 MRR 为 0.6133、两段同进 Top10 为 363；E0 对应 0.3169、12。列表位置改善伴随相对 E0 少 10 条成对正确，不称全面提升。

模型、训练原件、生成的逐题分数和原始包仅在本地保留，Git 提供说明、轻量聚合和复验入口。本地复验约 11.98 秒，不是成员原训练成本。成员记录的 N=8 拟合／预测／导出为 0.85 秒，不含约一分钟的候选特征准备；原过程日志未交付。

工程验证：训练模块 39 项通过；完整非 integration 回归 1,264 passed、23 skipped、3 deselected（6 个既有依赖警告），相关 Ruff 通过。原始验证日志保留在 [_engineering-checks/](_engineering-checks/)。本 PR 纳入源码、轻量聚合、复验入口和报告；模型、原始分数及交付归档仍按上述本地产物范围保存。
