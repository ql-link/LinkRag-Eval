# 固定 BGE 文本重排参照（2026-09-11，N14／#15）

已完成 `BAAI/bge-reranker-v2-m3` 的固定参照运行，revision 为 `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`。开发与确认均是此前已曝光的 validation 子集；没有 Test 输入。两个集合的配置均在首次 BGE 推理前写入 [execution-config.json](execution-config.json)，本次不重新选择 Qwen 主模型；选择记录的身份和旧协议缺口见 [selection.json](selection.json)。

使用官方 [Transformers 调用方式](https://huggingface.co/BAAI/bge-reranker-v2-m3)：查询与单段为输入，直接读取原始连续 logit，不映射为 0–4 或写入 LLM 缓存。fp16、eval／inference_mode、SDPA、batch=1、seed=20260910；模型支持 8192 输入上限。实际 9,034 个唯一“角色、查询、段落”输入（开发 1,524、确认 7,510），长度 33–336 tokens，全部完整输入，截断 0、不可用 0。L1 与 L2 的重叠项只计算一次。

推理在 Qwen 批次结束后使用同一 Runpod RTX 4090，未停止原 Qwen 服务。GPU 推理与逐条写出合计 102.804 秒；含输入加载、分词、模型加载的本进程主体为 116.273 秒，不含 import、下载和 SSH 传输。BGE 峰值分配约 1.15 GB，完整环境与计时边界见 [summary.json](summary.json)。不同模型的条数、并发和缓存使用不同，不能直接用总墙钟之比解释同负载加速倍数。

| 集合 | 方法 | 严格正确 | 双向全对 | 人审严格／52 |
| --- | --- | ---: | ---: | ---: |
| development | l1 | 47/74 | 13/37 | 39 |
| development | l2-k10 | 45/74 | 11/37 | 38 |
| development | l2-k20 | 47/74 | 13/37 | 39 |
| confirmation | l1 | 261/371 | 82/185 | — |
| confirmation | l2-k10 | 253/371 | 78/185 | — |
| confirmation | l2-k20 | 257/371 | 79/185 | — |

L2 使用同一候选集合、K=10／20、融合分破同分及窗口外原顺序；E0 分破同分只作为辅助输出。`evaluate.py` 直接复用现有 `evaluation_report`／`l2_rankers`／`listwise_report`，保留连续分数；没有修改主应用或整数判断器 schema。

- [run_bge.py](run_bge.py)：远端推理，读取同目录 items／execution-config；只从指定 revision 本地缓存加载权重，拒绝覆盖已有输出。
- [evaluate.py](evaluate.py)：在项目根目录执行 `.venv/bin/python runs/post_recall/open-judge-bge-reranker-v2-m3-20260911/evaluate.py`，读取本目录评分并重建六组评价；新运行须复制到同层新目录，不能覆盖本轮输出。
- [comparison.json](comparison.json)：两集合 L1／L2 的官方与开发人审聚合。
- [validation.json](validation.json)：分数范围、版本、E0 精确重放与 10 项独立排序／计数检查，全部通过。

原始 `items.jsonl`、`scores.jsonl`、各评价子目录与日志本地保留但被 Git 忽略；配置、脚本和聚合结果入白名单。远端原件为 `/workspace/linkrag-eval/open-judge-bge-reranker-v2-m3-20260911/`，权重为 `/workspace/hf/hub/models--BAAI--bge-reranker-v2-m3/snapshots/953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e/`。从完整原始产物重放需要这些本地文件。

实证与解释统一见[报告 §10.5](../../../docs/reports/llm_judge_pilot_2026_09_10.md#open-reference-20260911)。
