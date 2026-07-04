# RRF vs weighted_score 融合策略对比(2026-07-02)

## 结论

在相同候选、相同参数、无 rerank 的口径下,`weighted_score` 优于 `RRF`。

| fusion | recall@10 | hit_rate@10 | MAP | MRR | failed_source_samples |
| --- | ---: | ---: | ---: | ---: | ---: |
| RRF | 0.9715 | 0.9873 | 0.8782 | 0.9045 | 0 |
| weighted_score | 0.9745 | 0.9898 | 0.8894 | 0.9123 | 0 |
| weighted - RRF | +0.0030 | +0.0025 | +0.0112 | +0.0078 | 0 |

本轮建议:在当前四域 3200 chunk、394 条 clean golden 的评测集上,优先继续验证 `weighted_score`。它不仅 recall@10 略高,MAP/MRR 也更高,说明排序位置也改善了。

## 测试口径

- 数据集:`combined_4domain_clean`
- Golden:394 条 query
- Query 长度:平均 17.73 字符,中位数 9 字符,p90 48.7 字符,最短 3 字符,最长 120 字符;按空白切分平均 1.03 token。口径为 JSONL `query` 字段原始字符数。
- 语料规模:四域各 800 chunk,合计 3200 chunk
- Qdrant 前缀:`eval_doubao_v2_kb_bucket`
- 分路参数:
  - dense_top_k=20
  - sparse_top_k=5
  - dense_threshold=0.30
  - sparse_threshold=0.40
  - final_top_k=10
- rerank:未启用
- 对比方式:先缓存同一批 dense/sparse 分路候选,再本地分别复算 RRF 与 weighted_score。两种融合算法使用完全相同的候选输入。

## weighted_score 公式来源

生产 RAG 当前工作树实现了 `weighted_score`,但 `claude/sleepy-margulis-9143dc` worktree 仍只有 RRF 版本。实际实现位置:

- `/Users/jixu/Project/Agent/toLink-Rag/src/core/pipeline/recall/fusion.py`
- `/Users/jixu/Project/Agent/toLink-Rag/src/core/pipeline/recall/pipeline.py`

生产公式:

- BM25 / sparse:对 raw score 做 `log1p(raw_score)`。
- dense:直接使用 raw score。
- 每一路独立做 min-max 归一化。
- 某一路只有一个命中或 `max == min` 时,该路命中项 normalized score 为 1.0。
- 权重按 active sources 归一;chunk 未命中某一路时,该路贡献为 0。
- 当前 eval 只装 dense+sparse 两路,因此默认权重 `dense=0.5 / sparse=0.3 / bm25=0.2` 在 active sources 上归一后为:
  - dense=0.625
  - sparse=0.375

## 解释

RRF 只看各路排名,不看原始分数强弱。它的稳定性好,但在这批样本里,只要 sparse 有一个高排名但弱相关候选,仍可能通过排名贡献影响最终 top10。

weighted_score 会把每一路原始分做变换与归一化后再融合。当前参数已经把 sparse 候选收窄到 top5 且 sparse_threshold=0.40,低分 sparse 噪声被过滤后,weighted_score 能利用 dense/sparse 的分数强弱信息,因此排序质量提升更明显。

结合 query 长度看,这批 golden 以短 query 为主,平均只有 17.73 字符、中位数 9 字符。短 query 的词面信息少,sparse 更容易把少量词面重合但语义偏离的候选推到高位。因此本轮结论不是"sparse 无价值",而是"sparse 在短 query 下不适合作为强权重、大候选池信号"。

后续优化方向:可以在 RAG 侧增加 LLM query rewrite,先将短 query 改写成更完整、可检索性更强的 query,补充意图、实体别名、约束条件或上下文描述,再送入 sparse 匹配。这样可以让 sparse 从"少量词面重合"转向"更完整词面表达"的匹配,再与 dense 结果融合验证收益。

## 产物

原始 JSON:

- `runs/tuning/fusion_compare_combined_4domain_clean_20260702.json`

注意:这是离线融合复算结果。正式 `linkrag-eval run` 目前还没有接入 weighted_score 与分路 topK 参数;若要把该结论固化进 `eval_run` / `eval_metric_result`,下一步需要把 production 的 `fusion_strategy`、`dense_top_k`、`sparse_top_k` 接入 eval 正式 run 路径。
