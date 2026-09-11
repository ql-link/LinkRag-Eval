# #23 前置输入：确认集四排序器全池分数（2026-09-10）

本目录为 GitHub issue #23（列表塌陷的受控证据）准备输入，只抽取与登记，不含新训练。成员返回的结果及本地核验见[正式结果入口](../list-collapse-20260910/README.md)；本目录继续保留为只读来源。2026-09-11 已向交接包补入确认集监督与查询，并同步本说明。

所有展示的路径均相对于项目根目录 `LinkRag-Eval/`，命令从该目录执行。接收者从负责人取得 `runs/post_recall/_handover/handover-23-24-20260910.tar.gz` 后执行：

```sh
mkdir -p runs/post_recall
tar -xzf runs/post_recall/_handover/handover-23-24-20260910.tar.gz -C runs/post_recall
```

包内路径以 `runs/post_recall/` 为基准；下表列的是解压后的项目路径。Git 只提供代码与说明，不会自动提供这些评分、查询或监督文件。

| 输入 | 项目相对路径 | 用途与数量 |
| --- | --- | --- |
| A 中文基线 | `runs/post_recall/list-collapse-inputs-20260910/A-confirmation-scores.jsonl` | 原中文基线在同一批英文查询上的全池评分，374 行 |
| B 历史重训 | `runs/post_recall/list-collapse-inputs-20260910/B-confirmation-scores.jsonl` | 使用原 38 维特征、在 NevIR 上重训的历史模型，全池评分 374 行 |
| E0 英文基线 | `runs/post_recall/llm-judge-pilot-20260910/baseline/confirmation/scores.jsonl` | 英文适配基线的全池评分，374 行 |
| 固定融合 | `runs/post_recall/llm-judge-pilot-20260910/items-stage1-top20/confirmation/stage1-confirmation.jsonl` | 英文特征 `baseline_score` 列，全池评分 374 行；不是仅前 20 |
| 官方监督 | `runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment/prepared/confirmation/supervision.jsonl` | 每题指定两段、偏好方向与来源分组，374 行；指标计算必需 |
| 英文查询 | `runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment/prepared/confirmation/queries.jsonl` | 查询 ID 与正文，374 行，供逐题关联与解释 |
| 参考结果 | `runs/post_recall/list-collapse-inputs-20260910/confirmation-list-metrics-reference.json` | 已有 371 条有效查询的聚合参考；正式报告需独立复算 |

四份评分的公共字段为每行 `{"source_query_id", "scores": [{"chunk_id", "score"}, ...]}`；E0 另含运行元数据。它们的查询 ID 与每题候选 ID 集合相同，每题有 100–246 个候选，文件中的候选顺序为池内原顺序。

按 `source_query_id` 关联监督与评分。监督的 `preferred_chunk_id` 为首选段，`other_chunk_id` 为另一指定段；保留 `official_label_available=true` 且两段均在候选池中的查询。当前 374 条的官方标签均可用，其中 3 条未共同覆盖两个指定段，因此最终评价为 371 条；排除名单和原因应随结果保留。

列表位置按 `(-score, chunk_id)` 排序，从 1 起；成对严格正确直接比较两段的原始分数，同分不算正确。复用函数位于 `src/linkrag_eval/retrieval/learning_to_rank/llm_judge.py`：`score_maps` 读取评分映射，`baseline_order` 生成列表次序，`evaluate_pairs` 确定可评价查询，`list_metrics` 计算首选段@1／@3／MRR及两段各自平均排名。参考结果另含指定段中位排名与两段均进 top-10 数。

A／B 的历史抽取来源为 `runs/post_recall/nevir-ltr-validation-20260907/evaluation-preparation/confirmation/queries.jsonl` 中的 `models.A.raw.scores`／`models.B.raw.scores`；该历史文件不是本次复算的额外必需输入，本包已提供抽取后的分数。

以上七份输入覆盖 #23 第一部分的离线指标复算。第二部分是可选训练扩展，另需 Train／开发数据和 `runs/post_recall/subject-binding-pilot-20260908/representation-v3-20260909/config-v3-final.json`，本包不包含这些训练输入。完整分工见 [docs/plans/handover-issues-23-24-2026-09-10.md](../../../docs/plans/handover-issues-23-24-2026-09-10.md)。
