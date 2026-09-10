# N08 运行产物入口

完整实证与执行命令见[唯一正式报告](../../../docs/reports/nevir_subject_binding_pilot_2026_09_08.md)。本目录包含敏感的私有研究信息；对外仅分别分发 `handoff-structured-v2/reviewer_1_package.zip` 和 `handoff-structured-v2/reviewer_2_package.zip`。

- `config.json`、`extraction-spec.json`：显式数据输入、固定规则与预算。
- `handoff/`：两个原公共包与研究侧校验 manifest。
- `stage-a/`：构造探针、历史重放、开发覆盖、事实和分数。
- `stage-b/`：五臂、41 列契约、模型、逐候选预测、来源与四格、计时；E0 使用标准英文 38 列契约。
- `stage-b-input/`、`stage-b-parse/`：Train 原文输入与解析记录。
- `parse-cache/`、`environment/`：完全相同文本的版本化缓存与隔离解析环境。
- `checks/`：实际命令日志、基线 diff、回归和验收。

历史目录不覆盖；真实人类原始提交按版本只读保存在 `human/`，与临时 QA 分开。此 README 仅导航，不另维护实验状态。

- `handoff-structured-v2/`：当前两份五文件公共分发包，答案格式 2；同目录 manifest 只留研究侧。
- `handoff-structured-audit/`：结构化修订的代码／文档前态、实际最终包 DOM 脚本＋接收验收和回归日志；临时 QA 不是人类提交。
- `handoff-durable-v1/`：此前持久化和教程版本，保留供恢复旧草稿，不再作为当前分发入口。
- `human/20260909-intake-v1/`：两份真实原始提交、原规则收件及未裁定材料，保留原记录；标记数量不能直接解释为人类分歧率。
- `human/20260909-ambiguity-policy-v1/`：新规则收件、旧 JSON 兼容验收脚本与结果、回归日志；不包含新增裁定或模型分析。完整性例外见正式报告 §2.4，收件和缺项清单仅供研究侧使用。
- `human/20260909-intake-v2/`：负责人指定补写版的真实收件、原映射对齐、机械统计及 `adjudication/review-checklist.md` 人类裁定清单；原文件只读，原清单裁定栏保留接收时的空白状态；后续汇总与分析位于下述独立路径。
- `human/adjudication/current-results.json`：持续维护的讨论／裁定汇总数据；同名 Markdown 为阅读视图。`batches/` 保存每批原讨论、应用范围与核对，`history/` 保留更新前的汇总版本；`render_current.py` 仅生成阅读视图。`history/results-v5-frozen.json` 是当前固定人工输入，`analysis-policy-v2.json` 沿用原评价规则并关联第 60 题收尾；此前 v4 输入、阅读视图和政策 v1 保留；原始提交不覆盖。
- `human/adjudication/evaluate_saved.py`：本次一次性保存分数统计入口，`--out` 要求新目录；默认重放 v4，显式 `--policy analysis-policy-v2.json` 选择 v5（完整路径见报告命令）。`analysis-v2/` 保存最新结果、独立复算与验收，`analysis-v1/` 保留历史 51 题分析；均没有新增模型。
- `upstream-diagnostic-20260909/`：侧对话来源、v4/v5保存表示核查、21条错例机械定位与证据关联；不是完成的语义首因裁定，也没有修复或新训练。
- `repair-20260909/`：已实施的名词性引号／跨句引述范围与训练准入修复；v1/v2 配置、普通英文检查、完整回归、旧模型重放及同输入比较。最新结果为 `comparison-v2/results.json`，`comparison/` 保留首次工程检查中止；`development-cli/` 和 `cli-gate-checks.json` 验证当前入口拒绝无区分信号与旧版准入摘要。`compare.py --out-name 新目录名` 是本轮一次性重放入口；没有新研究模型。
- `representation-v3-20260909/`：版本覆盖、类型对称、事件／参数／证据保留及匹配接口修复。`config-v3-final.json` 关联当前源码 spec；`development-v1/v2/v3` 保存本轮原快照比较，`basic-training/` 保存固定 E0/EM/E1 模型、矩阵和逐候选预测；`source-at-fit/` 保留拟合时源码，`final-replay/` 保存证据字段最终校正后的完整数值等价验证，没有再次拟合。`model-audit.json`、`human-sensitivity.json` 和 `acceptance.json` 为模型、固定人工口径与交付核验入口；原配置和首次测试失败日志保留，不覆盖历史。

> 2026-09-10 归档：人审中间版本（intake-v1、analysis-v1、results-v1 到 v4）、前三版分发包、隔离环境副本、v2/v3 的全池重放与逐段事实记录已移入 [`_superseded/`](_superseded/MANIFEST.md)，未删除；当前结论所需文件保留原位。
