# Qwen3-8B 开发 L2 补充比较（#15，2026-09-11）

本轮补齐既有 8B 候选的开发 L2，沿用固定候选、`judge_prompt_v1` 和原评价函数。Qwen14B 主方案已经固定；本轮结果按补充对照记录，不回填为原确认前已完成的选型依据。

[execution-config.json](execution-config.json) 在新推理前写入：Qwen3-8B revision `b968826d9c46dd6066d109eabc6255188de91218`、bf16、思考模式、temperature=0、max_tokens=6144、8192 上下文、单项批次、8 并发。服务器使用明确的 seed=0；分批种子为 20260910，模型请求没有另传 seed。软件版本、失败策略、原 L1 来源与完整输入位置均在配置中。

输入为既有 development 的 76 查询×20 段，共 1,520 个唯一查询／正文输入。只判断这一批一次，再离线评价 K10／K20。原 `judge_items` 最多执行三次 runner 尝试，每次原 HTTP 运行器可能在 schema 不支持时作一次 fallback；这不等于最多三次 HTTP 请求。不加载任何旧缓存，不追加第二轮失败项重试。失败继续计入分母，按原 L2 规则使对应查询回退融合。

原 8B 开发 L1 为 41/74、人审 38/52，4 项不可用；来源为 `../llm-judge-pilot-20260910/l1-development-eval-qwen3-8b-think/results.json`。它使用较早的 token 上限且没有记录当时权重 revision，不伪称本次新推理或与本轮完全相同的运行配置。

在仓库根目录使用[共同执行脚本](../open-judge-selection-20260911/run_frozen.py)：

```bash
.venv/bin/python runs/post_recall/open-judge-selection-20260911/run_frozen.py \
  --config runs/post_recall/open-judge-qwen3-8b-development-20260911/execution-config.json
```

输出 `judge/` 必须不存在；执行进程和结束时间记录由脚本生成。完成后的评分供原 `scripts/llm_judge_pilot.py evaluate-l2` 消费，分数和评价分别保存。服务器启动命令见 [serve.sh](serve.sh)，它只启动对应固定模型，不停止其他进程。

本轮不读取 Test、不修改召回或人工标签、不训练模型。原始分数、批次输出、日志和工程 smoke 留在本目录并保持 Git 忽略；轻量配置、聚合结果和复现入口入库。结果状态见[当前状态](../../../docs/CURRENT_STATUS.md)，所有旧数据保持。

## 已完成结果

2026-09-11 04:22:55–04:54:26 UTC 完成正式判断，墙钟 **1,889.991 秒**。1,520 个输入最终 1,518 有效、2 不可用，空缓存；共 1,536 次 runner 尝试，其中 18 次失败。连同独立合成 smoke 的 3 次请求，服务器日志共有 **1,539 次 HTTP 200**，没有观察到 schema fallback；HTTP 成功不等于评分有效。错误仍为缺少合法 content，原 HTTP 运行器未保存 provider finish_reason，不能据此确证截断原因。

| K | 官方严格／74 | 双向全对／37 | 人审严格／52 | 首选段@1 | 全池回退查询／76 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 10 | 54 | 21 | 46 | 0.4730 | 2 |
| 20 | 55 | 22 | 47 | 0.4865 | 2 |

主表仍用融合分破同分。E0 分破同分的辅助结果为 K10 官方／人审 58／48，K20 为 59／49，完整四排序器与列表指标见 [K10](l2-k10/results.json)、[K20](l2-k20/results.json) 和 [comparison.json](comparison.json)。[l1/results.json](l1/results.json) 只是前述历史 L1 聚合表的副本；原 L1 分数及逐题评价仍在原目录。

**本轮 8B 的开发 L2 略高于已有 14B**：K20 官方多 1、人审多 2；14B 的原 L1 则较高。它说明不能宣称 14B 在开发 L2 上最佳或全面优于 8B。样本较小且历史缓存／参数不完全相同，不推断显著差异；既有 14B 继续作为事先固定的确认复验对象，不据本轮重新选择确认配置。

[validation.json](validation.json) 保存原评价 CLI 命令与范围检查；[independent-verification.json](independent-verification.json) 从原始分数独立复算 L1、两种 K 的逐题状态、全部 76 条候选顺序、官方／人审分母、双向及列表指标，全部通过，不调用生产排序器。运行器 11 项、独立验收 10 项检查通过；本轮非 integration 回归为 1,262 passed、23 skipped、3 deselected。

[resource-summary.json](resource-summary.json) 记录实际请求与成本。每 5 秒采样的 378 个正式运行样本中，最大 GPU 总占用为 21,256 MiB，含 vLLM 预留；这是本轮采样最大值，不是连续峰值、单请求显存或最低显存需求，不补填 #14 缺失的历史峰值。冷启动与下载不计入上述正式判断墙钟。
