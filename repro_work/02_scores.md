# 02 — 主实验评分文件盘点(2026-09-18,只读)

依据 `runs/post_recall/nevir-test-main-20260911/README.md` 与 `n8-test-replay-20260914/README.md` 的引用定位;逐条核对记录数与字段名,未读取 Test 正文、未展开 batch 目录。

| # | 类别 | 实际路径 | 存在 | 记录数 | 查询/段落识别字段 |
|---|---|---|---|---|---|
| 1 | Fusion 完整候选池分数 | `runs/post_recall/nevir-test-main-20260911/inputs/stage1-test.jsonl` | 是 | 2,766 查询 / 421,953 分数 | `source_query_id`;`scores[]` 内 `chunk_id`+`score` |
| 2 | E0 完整候选池分数 | `runs/post_recall/nevir-test-main-20260911/baseline/scores.jsonl` | 是 | 2,766 / 421,953 | 同上 |
| 3 | N=8 Test 重放分数 | `runs/post_recall/n8-test-replay-20260914/scores.jsonl` | 是 | 2,766 / 421,953 | 同上 |
| 4 | Qwen L1 分数 | `runs/post_recall/nevir-test-main-20260911/l1-judge/scores.jsonl` | 是 | 5,476 | `source_query_id`、`pair_id`、`chunk_id`;`level`、`score`、`status` |
| 5 | Qwen L2 分数 | `runs/post_recall/nevir-test-main-20260911/l2-judge/scores.jsonl` | 是 | 55,320 | 同上,另有 `recovery_provenance` 标注续行来源 |
| 6 | BGE 原始 logits | `runs/post_recall/nevir-test-main-20260911/bge/scores.jsonl` | 是 | 55,502 | `source_query_id`、`chunk_id`;`score`(连续 logit)、`dtype`、`levels`、`role`、`status` |

备注:
- 1–3 为逐查询记录,`scores` 是完整候选池的 `{chunk_id, score}` 列表,三路共 421,953 项与 n8 README 口径一致;4–6 为逐输入记录。
- `inputs/l1-test.jsonl`、`l2-test.jsonl` 是模型请求输入,不是评分;snapshot `coverage/test.jsonl`(2,766)是覆盖/监督元数据,不含分数。
- L1/L2 原始逐请求回执在 `l1-judge/batch-*`、`l2-judge/batch-*` 与 `l2-continuation-20260912/batch-*`;上表 4、5 为 README 所述组装后的逻辑评分文件。
- 聚合结果(`paper-summary.json`、`*-evaluation/results.json`、n8 `results.json`)仅作对照,未计入本表。
