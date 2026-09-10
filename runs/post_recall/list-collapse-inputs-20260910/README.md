# #23 前置输入：确认集四排序器全池分数（2026-09-10）

本目录为 GitHub issue #23（列表塌陷的受控证据）准备输入，只抽取与登记，不含新训练。

| 排序器 | 文件 | 来源 |
| --- | --- | --- |
| A 中文基线 | `A-confirmation-scores.jsonl` | 从 `nevir-ltr-validation-20260907/evaluation-preparation/confirmation/queries.jsonl` 的 `models.A.raw.scores` 抽取，全池 |
| B 历史重训 | `B-confirmation-scores.jsonl` | 同上 `models.B.raw.scores` |
| E0 英文基线 | `../llm-judge-pilot-20260910/baseline/confirmation/scores.jsonl` | N09 计算，与开发保存分数逐值一致 |
| 固定融合 | `../llm-judge-pilot-20260910/items-stage1-top20/confirmation/stage1-confirmation.jsonl` | 英文特征 `baseline_score` 列 |

格式统一为每行 `{"source_query_id", "scores": [{"chunk_id", "score"}, ...]}`，候选顺序为池内原顺序；列表位置按 `(-score, chunk_id)` 排序，从 1 起。评价函数可直接复用 `linkrag_eval.retrieval.learning_to_rank.llm_judge.list_metrics` 与 `score_maps`。

`confirmation-list-metrics-reference.json` 是本次抽取时顺手算出的参考值（371 题、官方标签），供 #23 第一部分核对；正式报告应重算并引用本目录。第二部分（背景负例重训）不依赖本目录以外的内容。
