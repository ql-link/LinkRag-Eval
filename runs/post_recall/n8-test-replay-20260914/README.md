# #49：固定 N=8 模型的官方 Test 本地重放

目的：在 #19 已验收快照上，用 #23 已恢复的 N=8 模型生成本地逐题分数，核对成员 Test 聚合。原模型、输入、冻结配置、成员结果和历史报告正文保持；Test 已曝光，本次不是新的选模或调参实验。

## 输入与固定口径

- 数据根目录通过 `--data-root` 显式指定。快照为其 `runs/post_recall/nevir-test-candidates-20260910/snapshot/`；使用已有查询、官方监督和完整候选，不读取原文补信息，不连接召回或编码服务。
- 唯一新评分模型：`runs/post_recall/list-collapse-20260910/background-n8-training/model-b/`，版本 `issue23-background-n8-20260910`，69 棵树、38 个英文特征。调用 `baseline_scores`，LightGBM 单线程；没有在线短查询回退、训练、候选截断或模型选择。
- 对照使用 #20 保存的 `baseline/scores.jsonl` 和 `inputs/stage1-test.jsonl`，验证三个排序器的查询与候选集合一致。
- 复用成员原 `evaluate_official_test.py` 的纯评价函数，不调用会写原目录的 `main()`。主口径为 2,736 方向／1,363 完整配对；含结构冲突敏感性为 2,738／1,364。严格胜负按原始分数差，位置按 `(-score, chunk_id)`，MRR 取指定优选段的完整列表排名。
- 验收比较原 `results.json` 的完整 coverage、三排序器两个人群聚合及 McNemar；整数精确一致，浮点绝对容差 `1e-12`。一致或不一致均保留本次结果，不择优覆盖原件。

## 执行

在代码工作区根目录执行；Python 需安装项目和 LightGBM：

```bash
PYTHONPATH=src python runs/post_recall/n8-test-replay-20260914/replay.py \
  --data-root /绝对路径/包含已验收数据与模型的仓库 \
  --out runs/post_recall/n8-test-replay-20260914
```

已有 `run.json`、`scores.jsonl` 或 `results.json` 时拒绝重放。终端只打印阶段与聚合，逐题分数不显示。合成回归位于 `tests/unit/test_n8_test_replay.py`，由默认单元测试收集。

保存分数的独立核验使用标准库实现，不再评分：

```bash
python runs/post_recall/n8-test-replay-20260914/verify.py \
  --data-root /绝对路径/包含已验收数据与模型的仓库 \
  --run-dir runs/post_recall/n8-test-replay-20260914
```

已有 `verification.json` 时拒绝覆盖。实际执行的数据根目录与命令参数见 `run.json`，核验输入见 `verification.json`。

## 2026-09-14 实际结果

单次成功，`completed_match`；N=8 主口径严格正确 **1,492/2,736**、同分 70、双向全对 **205/1,363**、优选段 MRR **0.585884**、两段同进 Top10 **2,609**。三排序器主／敏感性口径、覆盖与 McNemar 全部匹配成员聚合。独立实现从保存分数复算，分别对本次／成员结果各核对 111 项数值，均为 0 差异，状态 `verified_match`。

处理 2,766 查询／421,953 候选，特征与预测 72.738 秒，主流程总计 75.547 秒；独立核验另用 0.911 秒。LightGBM 4.7.0，NumPy 2.4.6，Python 3.11.15，单线程 CPU；无评分失败或重试。代码基于 `489180f` 加本次重放、核验脚本与 26 项合成测试，评分核心未改。原数字无需替换，新增证据与仍有缺口见[报告追加记录](../../../docs/reports/list_collapse_2026_09_11.md#n8-test-replay-20260914)。

PR 交付前回归：非 integration 测试 1,397 passed／23 skipped／3 deselected；CI 另收集的错误分类与改写探针脚本共 60 passed；相关 Ruff、报告索引和 diff-check 通过。没有再次评分 Test。

## 产物与证据边界

- `scores.jsonl`：本次 N=8 全候选数值分数，仅本地保存。
- `results.json`：重建聚合及与成员原件的逐指标对照。
- `run.json`：实际输入／模型位置、代码版本、依赖、参数、运行状态与耗时。
- `verification.json`：本地保存分数的独立聚合核对。过程日志只保留本地。

原冻结配置把融合版本写作 `candidate_difference_v3_english_v1`，实际脚本与模型契约为 `candidate_difference_v3_en_v1`；按实际契约重放，不改写原配置或添加别名。成员原逐题分数与原运行日志仍缺失，聚合一致不证明原运行的逐题身份、事前冻结时间或一次性执行历史。旧 Wilson／McNemar 的逐方向统计未校正配对／来源依赖，本次不扩展统计推断。

**本地保存位置与 worktree 清理。** PR 交付前，已将本目录的分数、日志、脚本和轻量结果复制到主数据工作区 `/Users/kawauso/Documents/Projects/LinkRag-Eval/runs/post_recall/n8-test-replay-20260914/`，逐文件核对字节一致，再清理临时 worktree。`run.json` 与 `verification.json` 中的 `LinkRag-Eval-issue49` 路径保留实际执行时的位置；清理后读取产物应使用上述主数据工作区同名目录。逐题分数和日志仍仅本地保存。

完整结果与解释登记到[原报告](../../../docs/reports/list_collapse_2026_09_11.md)和[实验台账](../../../docs/experiments/EXPERIMENT_LOG.md)。稿件题注和限制说明仅在独立本地论文目录同步，不纳入公开提交。
