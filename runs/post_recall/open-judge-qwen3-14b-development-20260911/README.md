# Qwen3-14B-AWQ 开发 L2 补齐（2026-09-11，N14／#15）

已完成现有英文 development 的 76 查询、1,520 条融合前 20 判断，供固定方案开发评价及 #17 开源成本曲线使用。模型选择不变，没有重跑确认集或读取 Test。

`execution-config.json` 在新推理前写入；Qwen revision 为 `31c69efc29464b6bb0aee1398b5a7b50a99340c3`，vLLM 0.29.0／torch 2.13.0／transformers 5.17.0，Runpod RTX 4090。新请求为 thinking、temperature=0、max_tokens=6144、context=8192、单项批次、8 并发，分批 seed=20260910 未传给模型请求。详细运行环境见 [runtime-check.json](runtime-check.json)。

先跑 3 条未缓存输入，3/3 可用，3.431 秒；正式补跑命中 145 条缓存（原有 142＋本次 smoke 3），新增 1,375 个唯一判断，包含重试共 1,380 次批次请求，809.613 秒。连同 smoke 共 1,383 次新请求。原有 142 条有效缓存的分数、理由和元数据均保持不变；它们可能来自更早的 token 上限，不能把本轮结果称为全部使用同一新上限的独立重复推理。

原运行器记录 7 次失败尝试，最终 2 条不可用。错误为 `ValueError: judge content must be a string`；未保存 provider finish_reason，不能确认具体截断原因。K=10／20 分别有 1／2 查询按既定规则回退融合，仍保留全部分母。

| K | 官方严格／74 | 双向全对／37 | 人审 v5 严格／52 | 首选段@1 | 回退查询 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 10 | 53 | 19 | 44 | 0.5000 | 1 |
| 20 | 54 | 20 | 45 | 0.5135 | 2 |

主表为融合分破同分；E0 分破同分的辅助结果见 [comparison.json](comparison.json)，未按其较高数字改主方法。原 L1 开发结果仍是 N10 的 42/74（3 条不可用），本次不把 L2 结果改称新 L1 实验。[l1/results.json](l1/results.json) 是原 `../llm-judge-pilot-20260910/l1-development-eval-qwen3-14b-awq-think/results.json` 的逐字节副本，只集中交付入口；L2 结果见 [K10](l2-k10/results.json)／[K20](l2-k20/results.json)。

实际评价和成本曲线命令见 [validation.json](validation.json)。原始新增判断在 `../llm-judge-pilot-20260910/l2s-development-judge-qwen3-14b-awq-think/`；smoke、日志和 `l2-k10/`、`l2-k20/` 的逐题产物保留在本目录，均不覆盖旧输出。原始缓存与逐题文件为本地忽略产物，Git 仅保留配置、摘要和核验记录。开发 K20 与曲线完整指标一致，确认 K20 与 N11 原结果一致。

一次汇总打印使用了错误的指标键路径，发生在评价文件已保存之后；修正为 `ranker.pairwise` 并复验，未重复模型推理。87 项相关测试与实验脚本 Ruff 通过。

研究记录见[报告 §10.5](../../../docs/reports/llm_judge_pilot_2026_09_10.md#open-reference-20260911)，后续缓存分析见[开源成本曲线](../judge-cost-curve-qwen-20260911/README.md)。
