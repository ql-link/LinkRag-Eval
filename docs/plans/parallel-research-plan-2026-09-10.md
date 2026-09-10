# 并行研究计划（2026-09-10 起）

> 本页是多人并行阶段的唯一任务分解入口。每项任务对应一个 GitHub issue（里程碑 [IEEE BigData 2026 投稿准备](https://github.com/ql-link/LinkRag-Eval/milestone/1)，截止 2026-09-20 AoE，赛道待负责人确认）。研究背景与已得结论见 [N09 报告](../reports/llm_judge_pilot_2026_09_10.md)，当前进度见 [CURRENT_STATUS](../CURRENT_STATUS.md)。本页只维护分工、依赖与协作规则，不复制实验结果。

## 1. 研究主线与已完成部分

主线是三步：错误存在且可复现 → 错误来自输入表示，且成对重训毁了列表顺序 → 补上读文本的信号后在留出集修复。前两步与第三步的 GPT-6 试点（N09）已完成；剩余工作是把第三步换成开源判断器、补统计与成本证据、在官方 Test 上做一次终评，然后成文。GPT-6 结果作为探路与参照，正式数字以开源判断器为准。

## 2. 任务分解

| 编号 | 任务 | 标签 | 依赖 | 预估 | 独占的改动范围 |
| --- | --- | --- | --- | --- | --- |
| [#14](https://github.com/ql-link/LinkRag-Eval/issues/14) | 开源判断器本地运行器 | judge／must | 无 | 2–3 天 | `llm_judge_local.py`、`llm_judge_pilot.py` 的 judge 参数、`runs/post_recall/open-judge-*` |
| [#15](https://github.com/ql-link/LinkRag-Eval/issues/15) | 开源判断器候选比较（开发集选模） | judge／must | #14 | 2 天 | `runs/post_recall/open-judge-*`、`docs/reports/open_judge_selection_*` |
| [#16](https://github.com/ql-link/LinkRag-Eval/issues/16) | 开源判断器确认集一次性评价 | eval／must | #15 | 1 天 | `runs/post_recall/open-judge-confirmation-*` |
| [#17](https://github.com/ql-link/LinkRag-Eval/issues/17) | 成本与准确率曲线、触发条件 | eval／must | 一期无；二期 #16 | 1 天 | `scripts/llm_judge_cost_curve.py`、`runs/post_recall/judge-cost-curve-*` |
| [#18](https://github.com/ql-link/LinkRag-Eval/issues/18) | 置信区间与配对检验 | eval／must | 无 | 1 天 | `pair_statistics.py`、`scripts/llm_judge_statistics.py`、`runs/post_recall/judge-statistics-*` |
| [#19](https://github.com/ql-link/LinkRag-Eval/issues/19) | 官方 Test 入库与候选快照（不评分） | data／must | 无 | 1–2 天 | Test 准备脚本、`runs/post_recall/nevir-test-candidates-*` |
| [#20](https://github.com/ql-link/LinkRag-Eval/issues/20) | 官方 Test 一次性终评 | eval／must | #16 #17 #19 | 1 天 | `runs/post_recall/nevir-test-final-*` |
| [#21](https://github.com/ql-link/LinkRag-Eval/issues/21) | 错误类型双人标注 | analysis／must | 无 | 人工半天 | `runs/post_recall/error-taxonomy-*`、`docs/reports/error_taxonomy_*` |
| [#22](https://github.com/ql-link/LinkRag-Eval/issues/22) | 污染声明与改写探针 | analysis／must | 开源部分 #14 | 1 天 | `runs/post_recall/paraphrase-probe-*` |
| [#23](https://github.com/ql-link/LinkRag-Eval/issues/23) | 列表塌陷的受控证据与背景负例重训 | analysis／optional | 无 | 0.5 + 2–3 天 | `pairwise_training.py`（唯一允许改它的任务）、`runs/post_recall/list-collapse-*` |
| [#24](https://github.com/ql-link/LinkRag-Eval/issues/24) | 跨分布小探针 | analysis／optional | #14 | 1 天 | `runs/post_recall/ood-probe-*` |
| [#25](https://github.com/ql-link/LinkRag-Eval/issues/25) | 论文骨架与图表 | paper／must | 骨架无；数字 #16 #17 #18 #20 | 4–5 天 | `docs/papers/manuscript/` |
| [#26](https://github.com/ql-link/LinkRag-Eval/issues/26) | 复现包 | paper／must | #16 #20 | 1 天 | `docs/papers/artifacts/` |
| [#27](https://github.com/ql-link/LinkRag-Eval/issues/27) | 清理审批 | infra／must | 无 | 决定即可 | 由负责人执行 |

可以立刻并行开工、互不阻塞的：#14、#17（一期）、#18、#19、#21、#23（第一部分）、#25（骨架）、#27。

## 3. 依赖关系

```
#14 → #15 → #16 → #17(二期) ─┐
#19 ───────────────────────→ #20 → #26
#14 → #22(开源部分), #24            │
#18 ──────────────────────→ #25 ←──┘
#21, #23 ──────────────────→ #25
```

## 4. 协作规则（防止分支冲突）

- **分支**：从 `master` 切 `feat/<slug>`；一个 issue 一个分支一个 PR；PR 标题沿用 `type(scope): 摘要`。
- **独占范围**：只在表中"独占的改动范围"内写；需要改别人范围内的文件，先在对方 issue 下留言。
- **共享文件只追加**：`docs/CURRENT_STATUS.md`、`docs/experiments/EXPERIMENT_LOG.md`、`docs/reports/REPORT_INDEX.md`（由 `scripts/build_report_index.py` 生成）、`scripts/README.md`、`runs/post_recall/README.md` 只在 PR 最后一个提交里追加自己的一行或一段，冲突由负责人合并时解决。
- **共享输入只读**：`runs/post_recall/nevir-ltr-validation-20260907/`、`items-stage1-top20/`、`baseline/`、人审文件不改写；新实验新建目录并附 README。
- **禁区**：不读官方 Test 逐题（#19 只做入库与聚合统计，#20 只跑一次）；不改召回、切块、BM25；提示词 `judge_prompt_v1` 不改，改提示词另开 issue。
- **合并门槛**：`LINKRAG_EVAL_REQUIRE_RAG=1 .venv/bin/python -m pytest -m "not integration" -q`、新文件 Ruff、`build_report_index.py --check`、`git diff --check` 全部通过。
- **结果登记**：每个实验在 `docs/experiments/EXPERIMENT_LOG.md` 追加一行，编号从 N10 起按合并顺序分配；报告写进 `docs/reports/`。

## 5. 时间安排（以 9 月 20 日为限）

| 时段 | 并行进行 |
| --- | --- |
| 9-11 至 9-13 | #14、#19、#18、#17 一期、#21、#25 骨架、#27 |
| 9-13 至 9-15 | #15、#22、#23 第一部分、#24 |
| 9-15 至 9-16 | #16、#17 二期 |
| 9-17 | #20 终评（配置冻结） |
| 9-17 至 9-19 | #25 正文数字替换与图表、#26 |
| 9-20 | 提交前检查与投稿 |

若截止日期不同，按同一顺序压缩或放宽；可选任务（#23 第二部分、#24）最先让路。
