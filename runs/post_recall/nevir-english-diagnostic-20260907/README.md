# NevIR：原 A 与英文模型的开发集机械诊断

**问题：现有英文规则在保存候选上产生了什么信号，模型如何利用这些信号？** 对比原 A 与当前英文模型；没有重训。两者的规则和权重均不同，差异不能全部归因于英文词表。

两者现命名为中文基线／英文基线，位于 `models/chinese-baseline/`／`models/english-baseline/`；本次运行的历史路径按[模型入口](../../../models/README.md)对应。

范围为同一开发快照的 76 查询／10,465 候选行，其中 74 查询可评价。保存分数与特征重放一致；英文否定特征已有响应，但不足以据此确认语义理解。机械诊断完成，人工复核待提交。实证见[正式报告 §7](../../../docs/reports/nevir_offline_diagnostic_2026_09_07.md#7-英文适配版在同一快照上的重跑2026-09-07)。

## 按目的打开文件

| 要看什么 | 文件／目录 | 读到什么 |
| --- | --- | --- |
| 范围、模型与运行状态 | [diagnostic/manifest.json](diagnostic/manifest.json) | 输入、A／英文模型身份、机械及人工状态 |
| 聚合诊断结果 | [diagnostic/summary.json](diagnostic/summary.json) | 指标、特征响应及机械观察 |
| 实际命令与执行 | [execution.json](execution.json) · [execution.log](execution.log) | 保存输入、命令、退出状态与耗时 |
| 逐题比较与全池分数 | [cases.jsonl](diagnostic/cases.jsonl) · [raw-predictions.jsonl](diagnostic/raw-predictions.jsonl) | 官方偏好下的逐题分析、A／英文候选分数 |
| 分模型特征与树路径 | [A/](_superseded/diagnostic/A/) · [English/](_superseded/diagnostic/English/) · [tree-audit.jsonl](_superseded/diagnostic/tree-audit.jsonl) | 各自版本的矩阵、特征追踪与逐树成对核验 |
| 重放与工程验收 | [replay-check.json](diagnostic/replay-check.json) · [artifact-verification.json](artifact-verification.json) · [acceptance.json](acceptance.json) | 精确重放、保存产物复核与工程检查结果 |
| 公共盲审材料 | [diagnostic/review/README.md](diagnostic/review/README.md) | 两份公共材料与提交格式；与旧诊断公共材料相同，尚非人工金标 |
| 测试和 CLI 日志 | [checks/README.md](checks/README.md) | 四份检查日志及原名称 |

`before-diagnostic-features.py` 和 `before-diagnostic-summary.py` 是诊断修改前的源码副本，不是运行入口。当前脚本为 `scripts/nevir_english_diagnostics.py`；本说明不触发重放或人工任务。

输入路径的来源见[数据入口](../../../data/README.md)；英文模型产自[英文特征对照](../nevir-english-features-20260907/README.md)，不是本诊断训练的。[返回实验总入口](../README.md)。

> 2026-09-10 归档：两模型的逐树特征追踪与树路径核验明细已移入 [`_superseded/`](_superseded/MANIFEST.md)，未删除；当前结论所需文件保留原位。
