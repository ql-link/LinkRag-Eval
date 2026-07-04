# 活栈 smoke 与正式 eval 前缀复验(2026-07-01/02)

## 范围

- 环境:本地 `.env.eval`(不入库),eval MySQL 库 `tolink_rag_eval_db`。
- Qdrant 正式前缀:`eval_doubao_v2_kb_bucket`,实际 bucket collection:`eval_doubao_v2_kb_bucket_9`。
- 数据:四域开源子集,`990123/ecom`、`990124/video`、`990126/dureader`、`990127/cmedqa`,每域 800 chunks。
- Golden:`combined_4domain_clean.jsonl`,394 条 doc 粒度样本。

## 已验证

- `alembic upgrade head` 成功,`alembic_version=0002`。`0002` 将 `eval_run.sparse_provider` 放宽到 128,避免较长 provider/model 指纹落库失败。
- 小规模 ingest + `run --precheck` 跑通。
- 四域正式重灌完成:MySQL `eval_corpus_chunk` 中四个 dataset 均为 800 行,`dense_indexed=800`,`sparse_indexed=800`,`bm25_indexed=0`。
- Qdrant collection schema 为 named dense vector `dense`(1024, cosine) + sparse vector `sparse_text`;点数为 3201(含 1 条小 smoke)。
- 配置自检确认写入目标为 `tolink_rag_eval_db` 和 `eval_doubao_v2_kb_bucket`。

## 指标

| 时间 | run_id | recall@10 | hit_rate@10 | map | mrr | 备注 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 2026-07-01 | `doubao-v2-4domain-clean-top10` | 0.8966 | 0.9391 | 0.8069 | 0.8606 | 在 `0.901±0.005` 内,但日志有少量 Qdrant 502/单路失败 |
| 2026-07-02 | `doubao-v2-4domain-clean-rerun-top10` | 0.8919 | 0.9340 | 0.8030 | 0.8555 | 日志未见单路失败,但低于等价门槛 |
| 2026-07-02 | `weighted-score-best-top10` | 0.9624 | 0.9797 | 0.8905 | 0.9127 | 正式 CLI 跑 weighted_score 最佳参数;non-clean run,11 条样本有 failed_sources |
| 2026-07-02 | `weighted-score-best-rerun-top10` | 0.9669 | 0.9822 | 0.8909 | 0.9137 | 同参数复跑;non-clean run,29 条样本有 failed_sources |
| 2026-07-04 | `weighted-score-clean-20260704-top10` | 0.9745 | 0.9898 | 0.8984 | 0.9212 | 正式 clean 基线;`failed_sources=0`,`zero_ranked=0` |

## 结论

活栈路径已经打通,隔离目标正确:只写 eval MySQL 库与含 `eval` 的 Qdrant collection。2026-07-04 的 `weighted-score-clean-20260704-top10` 已满足 clean run 条件:`failed_sources=0`、`zero_ranked=0`,并以 `recall@10=0.9745` 高于历史等价门槛。该 run 固化为当前 dense+sparse 两路正式基线。

## 两次 run 差异

- 2026-07-01 run 有 17 条样本出现 `failed_sources`;2026-07-02 复跑为 0 条,说明复跑链路更干净。
- `recall@10` 发生变化的样本共 3 条:2 条变差、1 条变好。
- 变差样本均来自 ecom:`ecom-200045`(`暖气进水管滤网`)和 `ecom-200056`(`名著导读配套阅读`)从 1.0 变为 0.0。
- 变好样本为 `dureader-02293e32393b1db39080ad78b534eaf9`(`怎么找到bt种子`)从 0.8333 变为 1.0。

## 分路诊断

- `ecom-200045` 和 `ecom-200056` 在 2026-07-01 run 中均为 `failed_sources=["sparse"]`,实际按 dense-only 召回,期望 doc 排名均为第 1。
- 2026-07-02 复跑中两条样本均无失败源,`per_source_counts={"dense":100,"sparse":50}`,但 dense+sparse RRF 后期望 doc 均跌出 top10。
- 单路复查结果:
  - `ecom-200045`:dense-only 期望 doc `990400739` 排第 1;sparse-only 未命中;dense+sparse 后 top10 全为 dense 与 sparse 双路命中的非期望商品。
  - `ecom-200056`:dense-only 期望 doc `990400752` 排第 1;sparse-only 未命中;dense+sparse 后 top10 全为 dense 与 sparse 双路命中的非期望商品。
- 结论:0.8919 不是活栈故障或写错库导致,而是完整启用 sparse 后暴露的融合口径差异。当前生产 RRF 对“双路弱相关候选”加分较强,可能把 dense 第 1 但 sparse 未命中的正确项挤出 top10。

## sparse 阈值 A/B

同一正式 eval 前缀、同一 394 条 golden,只调整 query 侧 `sparse_score_threshold`:

| sparse 阈值 | recall@10 | hit_rate@10 | map | mrr | 备注 |
| --- | ---: | ---: | ---: | ---: | --- |
| 0.00 | 0.8919 | 0.9340 | 0.8030 | 0.8555 | 2026-07-02 干净复跑 |
| 0.25 | 0.9246 | 0.9543 | 0.8014 | 0.8544 | 过滤部分 sparse 噪声,`ecom-200045` 修回 |
| 0.30 | 0.9571 | 0.9772 | 0.8196 | 0.8614 | `ecom-200045` / `ecom-200056` 均修回 |

这轮 A/B 先把 eval 默认配置切为 `EVAL_RECALL_SPARSE_SCORE_THRESHOLD=0.30`。该值只影响召回侧 sparse 分路结果过滤,不改变 Qdrant collection 和写入向量。后续完整网格搜索继续把推荐值更新为 0.40,见下节。

## dense/sparse topK + 阈值网格搜索

同一正式 eval 前缀、同一 394 条 golden,先分别缓存 dense/sparse 最大候选池,再在本地按生产 RRF 公式复算 720 组配置:

| 搜索维度 | 取值 |
| --- | --- |
| dense_top_k | 20, 50, 100, 200 |
| sparse_top_k | 5, 10, 20, 50, 100 |
| dense_threshold | 0.0, 0.1, 0.2, 0.3, 0.4, 0.5 |
| sparse_threshold | 0.0, 0.2, 0.25, 0.3, 0.35, 0.4 |
| final_top_k / rrf_k | 10 / 60 |

最优配置:

| dense_top_k | sparse_top_k | dense_threshold | sparse_threshold | recall@10 | hit_rate@10 | map | mrr | 分路失败样本 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | 5 | 0.30 | 0.40 | 0.9715 | 0.9873 | 0.8782 | 0.9045 | 0 |

敏感性观察:

- sparse_threshold 从 0.30 提高到 0.40 后,在 `dense_top_k=20`、`sparse_top_k=5` 下 recall@10 从 0.9665 升到 0.9715,MAP 从 0.8430 升到 0.8782。
- dense_threshold 在 0.0–0.3 区间指标几乎相同;0.4 以后 recall 开始下降。因此推荐 dense_threshold=0.30 是同分下偏向更严格过滤的选择,不是主要增益来源。
- sparse_top_k=5 优于更大的 sparse 候选池,说明低分 sparse 候选参与 RRF 是本轮偏差的主要来源。

结论:RRF 口径推荐值为 `EVAL_RECALL_DENSE_SCORE_THRESHOLD=0.30`、`EVAL_RECALL_SPARSE_SCORE_THRESHOLD=0.40`、`dense_top_k=20`、`sparse_top_k=5`。后续对比 weighted_score 后,正式默认值已切到 weighted_score 口径,见下节。

## weighted_score 正式 CLI 复验

同一正式 eval 前缀、同一 394 条 golden,把调参得到的 weighted_score 最佳参数接入正式 `linkrag-eval run` 路径后复验:

```text
fusion_strategy = weighted_score
dense_top_k = 150
sparse_top_k = 50
dense_threshold = 0.20
sparse_threshold = 0.40
dense_weight = 0.90
sparse_weight = 0.10
bm25_weight = 0.0
final_top_k = 10
rerank = none
```

正式命令已确认下发到生产 `RecallPipeline`:

- `route_top_k={'dense': 150, 'sparse': 50}`
- `fusion=weighted_score`
- `sources=['dense', 'sparse']`
- 写入 collection 为 `eval_doubao_v2_kb_bucket_9`

结果:

| run_id | recall@10 | hit_rate@10 | map | mrr | failed source 样本 | 失败来源 | 零结果样本 |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| `weighted-score-best-top10` | 0.9624 | 0.9797 | 0.8905 | 0.9127 | 11 | dense=8,sparse=3 | 3 |
| `weighted-score-best-rerun-top10` | 0.9669 | 0.9822 | 0.8909 | 0.9137 | 29 | dense=9,sparse=20 | 3 |

产物:

- 结果文件:`runs/results/weighted-score-best-top10.json`
- 快照:`runs/snapshots/weighted-score-best-top10.json`
- HTML 报告:`runs/weighted-score-best-top10.html`
- DB 台账:`eval_run.status=done`,写入 `eval_metric_result` 42 行
- 同参数复跑产物:`runs/results/weighted-score-best-rerun-top10.json`、`runs/weighted-score-best-rerun-top10.html`,DB 台账同样写入成功

说明:两轮正式活栈结果均低于离线调参报告中的 `recall@10=0.9745`,且均为 non-clean run。该结果可证明正式 CLI 参数接入、报告输出与台账落库已经闭环,但不应替代无远端失败的离线最佳值。HTML 报告已增加“运行质量”区块,显式标注 failed source 样本数、失败来源和零结果样本数。

## weighted_score clean 基线固化

为避免远端 Qdrant 偶发单路失败污染指标,`RecallEvaluable` 对返回 `failed_sources` 或零结果的样本执行有限重试。2026-07-04 使用同一正式 eval 前缀、同一 394 条 golden 跑 `run --precheck`,得到 clean run:

```text
run_id = weighted-score-clean-20260704-top10
fusion_strategy = weighted_score
dense_top_k = 150
sparse_top_k = 50
dense_threshold = 0.30
sparse_threshold = 0.40
dense_weight = 0.90
sparse_weight = 0.10
bm25_weight = 0.0
final_top_k = 10
enabled_sources = dense,sparse
```

结果:

| run_id | 样本 | recall@10 | hit_rate@10 | map | mrr | failed source 样本 | 失败来源 | 零结果样本 | run_quality |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- |
| `weighted-score-clean-20260704-top10` | 394 | 0.9745 | 0.9898 | 0.8984 | 0.9212 | 0 | `{}` | 0 | clean |

产物:

- 结果文件:`runs/results/weighted-score-clean-20260704-top10.json`
- 快照:`runs/snapshots/weighted-score-clean-20260704-top10.json`
- HTML 报告:`runs/weighted-score-clean-20260704-top10.html`
- DB 台账:`eval_run.status=done`,`eval_run.run_quality=clean`,`eval_run.failed_samples=0`,`eval_run.zero_ranked=0`,`eval_metric_result` 写入 42 行

结论:该 run 是当前 dense+sparse 两路标准基线。后续比较三路 `qdrant_bm25` 时,应以这条 clean baseline 作为两路对照,而不是 2026-07-02 的 non-clean run。

## 后续检查点

- dense+sparse clean 基线已完成:`weighted-score-clean-20260704-top10`。
- 活栈波动治理已完成第一步:对 failed source / zero-ranked 样本自动有限重试,并把 clean/non-clean 状态写入 DB 可索引列。
- 确认 golden 仍是 doc 粒度样本,`precheck` 只能校验样本数量,无法校验 chunk reference。
- 固定依赖与模型 fingerprint 后再复跑,避免嵌入服务版本或参数漂移影响结论。
- Step 6 仍需用 `EVAL_BM25_MODE=qdrant_bm25` 重灌 eval 语料并跑三路 clean run,固化 BM25 接入后的标准结果。
