# NevIR：历史同 38 维重训与共享候选快照

**原实验比较冻结 A 与使用 NevIR 重训的 B，二者都使用 legacy 的 38 维特征。** 该 B 不是后来的英文适配模型。本目录的 Train／开发快照仍被当前英文实验复用；B 的训练和确认结果只作历史证据。

原结果未确认主指标的稳定净收益，完整结果见[同特征重训报告](../../../docs/reports/nevir_same38_retraining_2026_09_07.md)。`validation` 是目录的历史名称，不表示本目录只含官方 Validation，也不表示这些数据都是未使用的测试材料。

| 要看什么 | 文件／目录 | 身份 |
| --- | --- | --- |
| 当前仍在使用的六个输入 | [数据入口](../../../data/README.md#2-当前英文训练实际使用的六个输入) | Train／开发查询、监督、保存候选的直接链接 |
| 数据准备与采集记录 | [data-preparation/experiment/run.json](data-preparation/experiment/run.json) | 共享语料、分组与采集范围 |
| 输入完整性核对 | [input-verification.json](data-preparation/experiment/input-verification.json) | 原采集完成后的完整性记录，不是排序效果 |
| 历史 B 训练与选模 | [training/selection.json](training-preparation/training/selection.json) | 原六配置训练及开发选模记录 |
| 历史 B 模型及分数 | [模型 manifest](training-preparation/training/model-b/manifest.json) · [开发分数](training-preparation/training/dev-predictions.jsonl) | 历史 B 的模型包与全池预测 |
| 历史确认结果 | [正式报告](../../../docs/reports/nevir_same38_retraining_2026_09_07.md) | 聚合结果优先从报告查；`evaluation-preparation/confirmation/` 已使用、已曝光 |
| 工程回归日志 | [final-nonintegration-tests.log](final-nonintegration-tests.log) | 当时的非 integration 验证 |

`data-preparation/` 是数据准备与候选，`training-preparation/` 是历史 B 训练，`evaluation-preparation/` 是历史评测。这三层按当时分工命名，保留运行依赖路径；其中的 `*-plan.md` 是原执行安排，不是当前指令。

当前英文模型的产物见[英文特征对照](../nevir-english-features-20260907/README.md)。[返回实验总入口](../README.md)。
