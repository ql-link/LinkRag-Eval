# NevIR：基础英文特征与 legacy 的同条件重训对照

**问题：只改变基础英文处理规则，在相同监督与训练设置下是否改善开发表现？** 比较对象是本轮 legacy 控制组与英文适配组，各拟合一次。原 A 仅为历史参照，不是本轮控制组。

范围为已有 Train／开发快照：1,869 条训练查询进入损失；开发 76 条，74 条指定目标共同覆盖。结论是英文组严格正确 44/74，legacy 为 47/74；技术验收通过，开发效果未提高。此处不是独立确认，语义归因仍待人工复核。完整解释见[正式报告](../../../docs/reports/nevir_english_features_2026_09_07.md)。

当前复现入口是 [nevir_compare_feature_versions.py](../../../scripts/nevir_compare_feature_versions.py)；原命令记录中的 `nevir_feature_compare.py` 是改名前名称，参数与行为不变。

## 按目的打开文件

| 要看什么 | 文件／目录 | 读到什么 |
| --- | --- | --- |
| 两组对照结果 | [comparison/comparison.json](comparison/comparison.json) | 指标、纠正／改坏、来源分布、特征响应与成本 |
| 启动配置与实际执行 | [comparison-config.json](comparison-config.json) · [comparison-execution.json](comparison-execution.json) · [执行日志](comparison-execution.log) | 指定输入、实际命令、退出状态与耗时 |
| 英文训练记录 | [english/selection.json](comparison/english/selection.json) | 六个实际输入、排除项、参数及选择的树数 |
| 当前英文基线 | [models/english-baseline/manifest.json](../../../models/english-baseline/manifest.json) | 历史版本 `nevir-english-same38-20260907`，特征 `candidate_difference_v3_en_v1` |
| 英文开发分数与特征 | [dev-predictions.jsonl](comparison/english/dev-predictions.jsonl) · [开发矩阵](comparison/english/development-candidate_difference_v3_en_v1.npz) | 全池分数与英文特征矩阵 |
| 历史控制与逐题差异 | [legacy/selection.json](comparison/legacy/selection.json) · [development-comparison.jsonl](comparison/development-comparison.jsonl) | 本轮控制组记录；两组逐题比较 |
| 验收及检查日志 | [technical-acceptance.json](technical-acceptance.json) · [产物复核](saved-artifact-verification.json) · [checks/README.md](checks/README.md) | 技术验收、保存产物复核、按用途命名的日志 |

## 容易混淆的位置

- 英文模型包已移至 `models/english-baseline/`，中文基线（原 A）位于 `models/chinese-baseline/`；`comparison/legacy/model-b/` 仍是本轮历史控制。训练记录、矩阵和分数未移动，加载方式及旧路径对应查[模型入口](../../../models/README.md)。
- `before-code/`、`structure-features.py` 及 `*-before*` 是改动前／阶段性对照证据，不是当前源码。当前源码在 `src/linkrag_eval/retrieval/learning_to_rank/`。
- `legacy_replay.py` 是当时的重放工具，配套 `legacy-replay-inputs.jsonl`、`legacy-before.npz` 和 `legacy-before-order.json`。这些有固定路径依赖，保留原名；不要为查看结果运行它。
- `initial-*`、`*-acceptance.json`、`*-replay.json` 等记录各阶段状态；通常只需上表验收入口，追溯时再读。

[数据入口](../../../data/README.md)说明共享快照与使用边界；[实验总入口](../README.md)区分本实验与后续英文诊断。检查日志的新旧文件名映射见 `checks/README.md`；原运行记录中的历史命令不改写。
