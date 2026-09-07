# NevIR：历史 A/B 的开发集离线诊断

**本目录检查原 A 与历史重训 B，二者使用 legacy 特征；不含后来的英文规则诊断。** 范围为 76 条开发查询，74 条目标共同覆盖。机械诊断已完成，语义归因待人工复核；当时发现两个否定特征、两个同文档特征恒零。

完整实证见[离线诊断报告](../../../docs/reports/nevir_offline_diagnostic_2026_09_07.md)。当前 A／英文模型的诊断另见[英文诊断目录](../nevir-english-diagnostic-20260907/README.md)，不能将两个目录的 `summary.json` 或追踪混用。

| 要看什么 | 文件／目录 | 读到什么 |
| --- | --- | --- |
| 运行范围与状态 | [manifest.json](manifest.json) | 原 A/B 模型、输入和机械／人工状态 |
| 聚合诊断结果 | [summary.json](summary.json) | 原 legacy 特征下的统计 |
| 逐题分析与分数 | [cases.jsonl](cases.jsonl) · [raw-predictions.jsonl](raw-predictions.jsonl) | 含官方方向的分析与候选分数，不作公共盲审材料 |
| 特征与树路径 | [feature-traces.jsonl](feature-traces.jsonl) · [tree-audit.jsonl](tree-audit.jsonl) | 原规则的特征取值与模型树路径 |
| 重放和独立验收 | [replay-check.json](replay-check.json) · [independent-acceptance.json](independent-acceptance.json) | 保存分数重放及产物机械检查 |
| 原公共盲审材料 | [review/README.md](review/README.md) | 公共材料、匿名映射边界和提交格式 |

`diagnosis.md`／`decision.md` 是当次自动诊断的输出；`probe_plan.json`／`training-support.json` 记录当时状态，不代表已启动新训练。`execution-plan.md` 是历史执行说明，本地同名重训报告是当时副本；当前正式报告以 `docs/reports/` 为准。

[数据入口](../../../data/README.md)解释开发材料的已使用范围。[返回实验总入口](../README.md)。
