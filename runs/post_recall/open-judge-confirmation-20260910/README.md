# N11：开源判断器确认集执行与恢复记录

2026-09-10，分支 `feat/open-judge-confirmation`，判断／评价实现保持 `da46a43`。原 L2 进程已完成，接手没有重启整批。L1 首次 211/371、失败项重试后 212/371；L2 K=20 两次级排序 280/371、287/371，低于 GPT-6 的 311/371、312/371。完整解释见[报告 §10.4](../../../docs/reports/llm_judge_pilot_2026_09_10.md#104-确认集开源口径与执行偏差n1116-接续)。

原任务未在运行前保存 `frozen-config.json`，且 L1／L2 都进行了缓存失败项的第二次调用；这与 #16 的事前冻结、一次性运行要求存在偏差。参数可从执行前交接命令恢复，但 `execution-config.json` 明确是事后补记，不伪称事前冻结。主表保留首次运行，重试单列；没有据确认结果再选择模型、提示词或 K。本次完成执行与评价收尾，不宣称 #16 的严格验收全部满足，也不自动关闭该 issue。

## 输入与配置

validation 的确认角色：374 查询、371 可评价方向、185 完整双向对、96 来源组。L1 指定两段共 742 项，L2 固定融合前 20 共 7,480 项。未读取官方 Test，未改人工标签、召回或提示词。

RTX 4090，vLLM 0.29.0，`Qwen/Qwen3-14B-AWQ`（served name `qwen3-14b-awq`，awq_marlin）；`--think --max-tokens 6144 --num-ctx 8192 --workers 8`，batch_size=1、seed=20260910、temperature=0、`judge_prompt_v1`。模型 revision、软件版本的事后核查值、原始命令来源和全部输入路径见 [execution-config.json](execution-config.json)。合法缓存按 prompt/model/effort 复用，可能来自较早且 token 上限不同的运行，不把所有缓存都称为本次新生成。

## 实际运行与失败

| 实际调用 | 条目 / 唯一键 | 命中缓存 / 待判键 | 实际批次（含内部重试） | 不可用条目 | 墙钟秒 |
| --- | --- | --- | ---: | ---: | ---: |
| L1 首次 | 742 / 739 | 0 / 739 | 746 | 3 | 597.629 |
| L1 失败项重试 | 742 / 739 | 736 / 3 | 7 | 2 | 216.188 |
| L2 首次 | 7480 / 7420 | 707 / 6713 | 6721 | 4 | 3436.495 |
| L2 失败项重试 | 7480 / 7420 | 7416 / 4 | 12 | 4 | 239.460 |

四次 judge 调用共 **4489.772 秒（74.83 分钟）**、7486 个实际单条批次／请求尝试，含内部重试及缓存读取，不含部署、下载、离线评价或人类工时；旧缓存的历史推理成本未重复计入。本次接续只重试 L2 的 4 个失败键（12 次尝试、239.460 秒），没有新增有效分数，也没有覆盖已有有效分数。

L1 重试后剩 2 项不可用；L2 重试后仍为 4。两种 K 各有 4 条查询整体回退融合，因此最终排名可评价不等于判断无失败。L2 的 7,480 行分数／可用状态与首次完全相同。失败记录为 `ValueError: judge content must be a string`；服务端 finish_reason 未保存，不能把这批空 content 独立确证为 token 截断。没有据确认结果提高上限或改提示词，也不继续盲目重试。

## 产物

| 目录／文件 | 用途 |
| --- | --- |
| `l1-first-pass/results.json`、`l1-retry/results.json` | L1 首次与重试后，后者精确重放旧 pilot 评价 |
| `l2-first-pass-k10/results.json`、`l2-first-pass-k20/results.json` | L2 首次四排序器与列表评价 |
| `l2-retry-k10/results.json`、`l2-retry-k20/results.json` | L2 重试后，两种 K 的全部指标精确等于首次 |
| [comparison.json](comparison.json) | 全部对照表、GPT-6 参考、四次摘要及一致性检查 |
| [execution-config.json](execution-config.json) | 实际参数、输入位置、代码版本、模型 revision、协议偏差 |
| [validation.json](validation.json) | 复验、测试与剩余不可用项 |

Git 只保存上表聚合产物与 README。逐条分数、批次日志与缓存仍在 `../llm-judge-pilot-20260910/` 的 `l1-confirmation-judge-qwen3-14b-awq-think{,-retry}/` 和 `l2s-confirmation-judge-qwen3-14b-awq-think{,-retry}/`。共享复现输入时需要这些被忽略目录及配置文件所列 baseline、stage1、prepared 标签输入，不能只发聚合 JSON 后声称可重跑全部流程。

离线复算示例（仓库根目录，输出目录须不存在，不触发新判断）：

```bash
P=runs/post_recall/llm-judge-pilot-20260910
.venv/bin/python scripts/llm_judge_pilot.py evaluate-l1 --role confirmation \
  --baseline "$P/baseline/confirmation/scores.jsonl" \
  --scores "$P/l1-confirmation-judge-qwen3-14b-awq-think/scores.jsonl" \
  --out /tmp/open-judge-l1-new
.venv/bin/python scripts/llm_judge_pilot.py evaluate-l2 --role confirmation \
  --baseline "$P/baseline/confirmation/scores.jsonl" \
  --stage1 "$P/items-stage1-top20/confirmation/stage1-confirmation.jsonl" \
  --scores "$P/l2s-confirmation-judge-qwen3-14b-awq-think/scores.jsonl" \
  --top-k 20 --out /tmp/open-judge-l2-k20-new
```

K=10 只改离线参数与输出目录；重试敏感性分析用 `-retry/scores.jsonl`。这不是启动新确认实验的指令。#17 开源二期仍缺开发角色 L2 缓存，不能用 L1 开发分数代替。

## 验证

两套基线精确复现、已有有效分数全部保留、L1 旧评价精确重放、L2 两种 K 的首次／重试全指标一致。独立工作树完整非 integration：**1,244 passed、23 skipped、3 deselected、6 warnings**；跳过项均因真实 parser 环境缺失，不称作 parser 验证通过。应用代码无修改。
