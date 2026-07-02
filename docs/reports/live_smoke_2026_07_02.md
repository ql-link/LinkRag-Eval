# 活栈 smoke 与正式 eval 前缀复验(2026-07-01/02)

## 范围

- 环境:本地 `.env.eval`(不入库),eval MySQL 库 `tolink_rag_eval_db`。
- Qdrant 正式前缀:`eval_doubao_v2_kb_bucket`,实际 bucket collection:`eval_doubao_v2_kb_bucket_9`。
- 数据:四域开源子集,`990123/ecom`、`990124/video`、`990126/dureader`、`990127/cmedqa`,每域 800 chunks。
- Golden:`combined_4domain_clean.jsonl`,394 条 doc 粒度样本。

## 已验证

- `alembic upgrade head` 成功,`alembic_version=0001`。
- 小规模 ingest + `run --precheck` 跑通。
- 四域正式重灌完成:MySQL `eval_corpus_chunk` 中四个 dataset 均为 800 行,`dense_indexed=800`,`sparse_indexed=800`,`bm25_indexed=0`。
- Qdrant collection schema 为 named dense vector `dense`(1024, cosine) + sparse vector `sparse_text`;点数为 3201(含 1 条小 smoke)。
- 配置自检确认写入目标为 `tolink_rag_eval_db` 和 `eval_doubao_v2_kb_bucket`。

## 指标

| 时间 | run_id | recall@10 | hit_rate@10 | map | mrr | 备注 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 2026-07-01 | `doubao-v2-4domain-clean-top10` | 0.8966 | 0.9391 | 0.8069 | 0.8606 | 在 `0.901±0.005` 内,但日志有少量 Qdrant 502/单路失败 |
| 2026-07-02 | `doubao-v2-4domain-clean-rerun-top10` | 0.8919 | 0.9340 | 0.8030 | 0.8555 | 日志未见单路失败,但低于等价门槛 |

## 结论

活栈路径已经打通,隔离目标正确:只写 eval MySQL 库与含 `eval` 的 Qdrant collection。当前不能把 `recall@10 ≈ 0.901` 判为已稳定等价,因为 2026-07-02 的干净复跑为 0.8919,低于下界 0.896。后续需要优先分析最新复跑偏差,再把通过门槛的结果设为正式基线。

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

## 后续检查点

- 决策是否把“dense-only 第 1、sparse 未命中、融合后丢失”作为融合策略待优化问题,还是把 dense+sparse 当前行为作为新的真实基线。
- 确认 golden 仍是 doc 粒度样本,`precheck` 只能校验样本数量,无法校验 chunk reference。
- 固定依赖与模型 fingerprint 后再复跑,避免嵌入服务版本或参数漂移影响结论。
