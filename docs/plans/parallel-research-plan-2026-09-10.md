# 并行研究计划（2026-09-10 起）

> 本页是多人并行阶段的唯一任务分解入口。每项任务对应一个 GitHub issue（里程碑 [IEEE BigData 2026 投稿准备](https://github.com/ql-link/LinkRag-Eval/milestone/1)，截止 2026-09-20 AoE，赛道待负责人确认）。研究背景与已得结论见 [N09 报告](../reports/llm_judge_pilot_2026_09_10.md)，当前进度见 [CURRENT_STATUS](../CURRENT_STATUS.md)。本页只维护分工、依赖与协作规则，不复制实验结果。

## 1. 当前研究分工依据

2026-09-10 负责人明确：Qwen 用于固定权重和可复现的主实验，GPT 用于启发与参照。现行研究问题、Qwen 版本、L2 主方案和对照统一见[研究计划 §1.3](post-recall-research-plan.md#13-current-direction)及 §6，本页只维护任务范围和依赖。当前主比较沿用固定融合前 20＋单段判断，不以追平 GPT 或找到成功的触发规则作为继续主线的条件。

主研究链条为错误证据、来源诊断、开源方案修复与代价。N08 的提取缺口不直接解释 E0 的全部错排；#23 的列表观察与背景负例因果对照分开，不将原论文骨架中的强归因当作已证实结果。实际完成度看 [CURRENT_STATUS](../CURRENT_STATUS.md)，不以 issue 是否关闭推断产物是否存在。

下表是本轮纠偏后的本地任务口径。GitHub 原 issue 保留其发布时间的要求，本轮没有代负责人改写 issue；执行时将本轮明确决定与原验收缺口一起记录，不补造事前选择或冻结记录。

## 2. 任务分解

| 编号 | 任务 | 标签 | 依赖 | 预估 | 独占的改动范围 |
| --- | --- | --- | --- | --- | --- |
| [#14](https://github.com/ql-link/LinkRag-Eval/issues/14) | 开源判断器本地运行器 | judge／must | 无 | 2–3 天 | `llm_judge_local.py`、`llm_judge_pilot.py` 的 judge 参数、`runs/post_recall/open-judge-*` |
| [#15](https://github.com/ql-link/LinkRag-Eval/issues/15) | 记录 8B／14B 的开发 L1／L2 比较、固定选择与一个轻量文本参照；不继续 32B 选型 | judge／must | #14 | 2 天 | `runs/post_recall/open-judge-*`、`docs/reports/open_judge_selection_*` |
| [#16](https://github.com/ql-link/LinkRag-Eval/issues/16) | 保留既有首次／重试及协议偏差；按负责人后续要求对已曝光确认作固定配置复验，不充当新独立 Test | eval／must | 已有运行；核对 #15 的模型身份 | 1 天 | `runs/post_recall/open-judge-confirmation-*` |
| [#17](https://github.com/ql-link/LinkRag-Eval/issues/17) | 成本曲线与原触发对照；负结果照常交付，不要求产出成功门控 | eval／must | 一期无；二期 #16＋开发 L2 缓存 | 1 天 | `scripts/llm_judge_cost_curve.py`、`runs/post_recall/judge-cost-curve-*` |
| [#18](https://github.com/ql-link/LinkRag-Eval/issues/18) | 置信区间与配对检验 | eval／must | 无 | 1 天 | `pair_statistics.py`、`scripts/llm_judge_statistics.py`、`runs/post_recall/judge-statistics-*` |
| [#19](https://github.com/ql-link/LinkRag-Eval/issues/19) | 官方 Test 入库与候选快照（不评分） | data／must | 无 | 1–2 天 | Test 准备脚本、`runs/post_recall/nevir-test-candidates-*` |
| [#20](https://github.com/ql-link/LinkRag-Eval/issues/20) | 官方 Test 一次性终评；固定主配置和必要对照 | eval／must | #15 #16 #18 #19；#17 的结果用于报告，不要求触发成功 | 1 天 | `runs/post_recall/nevir-test-final-*` |
| [#21](https://github.com/ql-link/LinkRag-Eval/issues/21) | 错误类型双人标注 | analysis／must | 无 | 人工半天 | `runs/post_recall/error-taxonomy-*`、`docs/reports/error_taxonomy_*` |
| [#22](https://github.com/ql-link/LinkRag-Eval/issues/22) | 污染声明与改写探针 | analysis／must | 开源部分 #14 | 1 天 | `runs/post_recall/paraphrase-probe-*` |
| [#23](https://github.com/ql-link/LinkRag-Eval/issues/23) | 四排序器列表诊断必需；背景负例重训为因果扩展 | analysis／must＋optional | 无 | 0.5 + 2–3 天 | `pairwise_training.py`（唯一允许改它的任务）、`runs/post_recall/list-collapse-*` |
| [#24](https://github.com/ql-link/LinkRag-Eval/issues/24) | 跨分布小探针 | analysis／optional | #14 | 1 天 | `runs/post_recall/ood-probe-*` |
| [#25](https://github.com/ql-link/LinkRag-Eval/issues/25) | 论文骨架与图表 | paper／must | 骨架无；数字 #16 #17 #18 #20 | 4–5 天 | `docs/papers/manuscript/` |
| [#26](https://github.com/ql-link/LinkRag-Eval/issues/26) | 复现包 | paper／must | #16 #20 | 1 天 | `docs/papers/artifacts/` |
| [#27](https://github.com/ql-link/LinkRag-Eval/issues/27) | 清理审批 | infra／must | 无 | 决定即可 | 由负责人执行 |

接手时先核对已有 PR 和本地缓存，避免把 #14、#16、#17 和 #18 已落盘的成果误认作缺失。2026-09-11 负责人重启服务器并要求补齐 #15／#16 后，8B 开发 L2 与 14B 固定配置确认复验各自另存运行记录；不能用复验补造原事前文件或替换较低的历史结果。是否已经完成以[当前状态](../CURRENT_STATUS.md)为准，本分工表不重复维护实时进度。#19、#21、#22、#23 第一部分和 #25 骨架可独立推进；这份多人分工表不自动派发新 Agent 或启动实验。

## 3. 依赖关系

```
#14 → #15（既有选型记录／轻量参照）
#15、#16、#18、#19 → #20（固定配置终评）→ #26
#16＋开发 L2 缓存 → #17（二期）
#14 → #22（开源部分）、#24
#17、#18、#20、#21、#22、#23 → #25
```

## 4. 协作规则（防止分支冲突）

- **分支**：从 `master` 切 `feat/<slug>`；一个 issue 一个分支一个 PR；PR 标题沿用 `type(scope): 摘要`。
- **独占范围**：只在表中"独占的改动范围"内写；需要改别人范围内的文件，先在对方 issue 下留言。
- **共享文件只追加**：`docs/CURRENT_STATUS.md`、`docs/experiments/EXPERIMENT_LOG.md`、`docs/reports/REPORT_INDEX.md`（由 `scripts/build_report_index.py` 生成）、`scripts/README.md`、`runs/post_recall/README.md` 只在 PR 最后一个提交里追加自己的一行或一段，冲突由负责人合并时解决。
- **共享输入只读**：`runs/post_recall/nevir-ltr-validation-20260907/`、`items-stage1-top20/`、`baseline/`、人审文件不改写；新实验新建目录并附 README。
- **禁区**：不读官方 Test 逐题（#19 只做入库与聚合统计，#20 只跑一次）；不改召回、切块、BM25；提示词 `judge_prompt_v1` 不改，改提示词另开 issue。
- **合并门槛**：`LINKRAG_EVAL_REQUIRE_RAG=1 .venv/bin/python -m pytest -m "not integration" -q`、新文件 Ruff、`build_report_index.py --check`、`git diff --check` 全部通过。
- **结果登记**：每个实验在 `docs/experiments/EXPERIMENT_LOG.md` 追加一行，编号从 N10 起按合并顺序分配；报告写进 `docs/reports/`。

## 5. 原时间安排（按实际完成度推进）

下表保留最初按 9 月 20 日安排的排期，不覆盖当前状态。先按[研究计划 §8](post-recall-research-plan.md#8-已明确的决策与执行顺序)接齐已完成结果，再完成开源对照／统计、错误解释和 Test。开源开发 L2 缓存是 #17 二期的实际缺口；#17 无须通过触发收益门槛才允许固定 K=20 主方法终评。

| 时段 | 并行进行 |
| --- | --- |
| 9-11 至 9-13 | #14、#19、#18、#17 一期、#21、#25 骨架、#27 |
| 9-13 至 9-15 | #15、#22、#23 第一部分、#24 |
| 9-15 至 9-16 | #16、#17 二期 |
| 9-17 | #20 终评（配置冻结） |
| 9-17 至 9-19 | #25 正文数字替换与图表、#26 |
| 9-20 | 提交前检查与投稿 |

若截止日期不同，按同一顺序压缩或放宽；可选任务（#23 第二部分、#24）最先让路。

> 2026-09-10 补充：#23／#24 的前置产物与接手步骤见[交接说明](handover-issues-23-24-2026-09-10.md)。
