# 03 — Test 固定输入与评价映射(2026-09-18,只读)

以 `runs/post_recall/nevir-test-candidates-20260910/snapshot/` 为主源,结合 02 所列评分文件的输入说明;字段与计数经程序核对,未读 Test 正文。

## 文件类材料

| 用途 | 实际路径 | 相关字段 | 记录数 |
|---|---|---|---|
| 1 计划查询清单(2,766 方向=1,383 对×2) | `snapshot/prepared/test/queries.jsonl` | `source_query_id`,`query` | 2,766 |
| 1 同上(候选采集期口径) | `snapshot/candidates/test/queries.jsonl` | 同上 | 2,766 |
| 2 完整候选池(逐查询全池,非 Top20) | `inputs/stage1-test.jsonl`、`baseline/scores.jsonl`、`n8-test-replay-20260914/scores.jsonl` 的 `scores[]` 键集合 | `source_query_id` + `scores[].chunk_id` | 2,766 / 421,953 |
| 2 候选采集输入(每查询路由与候选行数) | `snapshot/candidates/test/inputs.jsonl` | `source_query_id`,`candidate_rows`,`routes`,`route_status`,`ranking_input_ready` | 2,766 |
| 2 语料段(2,081 去重段)与 ID 映射 | `snapshot/prepared/corpus.jsonl`;`prepared/passage-mapping.jsonl` | `source_passage_id`,`content`;`chunk_id`,`dataset_id`,`doc_id` | 2,081 / 2,081 |
| 3 官方优选段与另一段 | `snapshot/prepared/test/supervision.jsonl` | `preferred_chunk_id`,`other_chunk_id`,`preferred_passage_id`,`other_passage_id`,`official_label_available`,`direction` | 2,766 |
| 4 pair/方向/来源组 | 同上 | `pair_id`,`direction`,`source_group_id`,`role` | 2,766 |
| 4-5 覆盖与标记元数据(口径说明用) | `snapshot/coverage/test.jsonl` | `pair_in_union`,`candidate_count`,`loss_eligible`,`structural_conflict`,`ranking_input_ready`,`role`,`pair_id` | 2,766 |

## 5 纳入/排除规则(在代码,不在字段)

- **人群划分**:`runs/post_recall/nevir-test-main-20260911/workflow.py` `evaluate()` 第 152–155 行——`primary` = supervision 中 `not structural_conflict`;`including_conflict` = 全部。第 192 行断言分母 2,736/2,738。
- **逐方向纳入过滤**:`src/linkrag_eval/retrieval/learning_to_rank/llm_judge.py` `evaluate_pairs()` 第 397–410 行——跳过 `not official_label_available` 或指定两段 `{preferred, other}` 不全在 baseline 分数键内(即共同覆盖);L2 经 `evaluate_rankers()` 第 526 行复用同一过滤。
- **成员原实现(对照)**:`runs/post_recall/nevir-test-final-20260911/evaluate_official_test.py` 第 164–201 行——covered(两段并集)→ official(标签可用)→ primary(无结构冲突)/including_conflict,与上同构。
- 结构冲突来源:`src/linkrag_eval/runners/nevir_ltr_data.py` 第 108–115 行按 `q1 == q2` 判定并写入 supervision。
- 结论链:2,766 计划 → 共同覆盖 2,738 → 排除 2 个结构冲突 = 主口径 2,736(1,363 完整配对)。
