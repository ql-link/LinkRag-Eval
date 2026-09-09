# N08 运行产物入口

完整实证与执行命令见[唯一正式报告](../../../docs/reports/nevir_subject_binding_pilot_2026_09_08.md)。本目录包含敏感的私有研究信息；对外仅分别分发 `handoff-structured-v2/reviewer_1_package.zip` 和 `handoff-structured-v2/reviewer_2_package.zip`。

- `config.json`、`extraction-spec.json`：显式数据输入、固定规则与预算。
- `handoff/`：两个原公共包与研究侧校验 manifest。
- `stage-a/`：构造探针、历史重放、开发覆盖、事实和分数。
- `stage-b/`：五臂、41 列契约、模型、逐候选预测、来源与四格、计时；E0 使用标准英文 38 列契约。
- `stage-b-input/`、`stage-b-parse/`：Train 原文输入与解析记录。
- `parse-cache/`、`environment/`：完全相同文本的版本化缓存与隔离解析环境。
- `checks/`：实际命令日志、基线 diff、回归和验收。

历史目录不覆盖；人类原始提交尚未收到，未创建假 human 数据。此 README 仅导航，不另维护实验状态。

- `handoff-structured-v2/`：当前两份五文件公共分发包，答案格式 2；同目录 manifest 只留研究侧。
- `handoff-structured-audit/`：结构化修订的代码／文档前态、实际最终包 DOM 脚本＋接收验收和回归日志；临时 QA 不是人类提交。
- `handoff-durable-v1/`：此前持久化和教程版本，保留供恢复旧草稿，不再作为当前分发入口。
