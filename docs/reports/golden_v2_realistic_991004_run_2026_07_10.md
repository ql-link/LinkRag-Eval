# Golden V2 Realistic 991004 Run Report

日期: 2026-07-10

## 结论

本轮在 `990901,991002,991003,991004` 四个 eval dataset 上重建 realistic 候选池与 chunk 粒度标注集。最终 `adjudicated` draft 已构建完成:

- query: 50
- judged rows: 634
- relevant chunk judgments: 300
- positive queries: 50/50
- unresolved queries: 0
- split: `realistic_tune=38`, `realistic_blind=12`
- hard split: 0
- QC: `warn`, 无 failure

QC 的 warning 是候选池中没有“纯 random_neighbor”候选,无法估计 judge false positive;不是未召回或标注失败。

## 隔离边界

本轮只使用 eval 侧资源:

- MySQL: eval 独立库 `tolink_rag_eval_db`
- Qdrant: eval 前缀 collection
- BM25: 本地 SQLite FTS5 sidecar `runs/bm25_eval.sqlite3`
- Alt embedding: 本地 SQLite sidecar `runs/alt_embedding_eval.sqlite3`
- 生成产物: `runs/golden_v2/spark_gap_bundle_991004/`

没有写生产数据库表,也没有使用生产库作为结果后端。

## 外部输入

991004 背景语料 spec 由 GPT-5.3-Codex-Spark 子任务生成,不使用当前项目配置的业务模型生成 query/chunk 外部输入。

- spec: `runs/golden_v2/spark_gap_bundle_991004/spark_gap_corpus_spec.json`
- dataset_id: `991004`
- domains: 11
- synthesized chunks: 220
- source type: synthetic eval background

## 候选池

候选池路径:

`runs/golden_v2/spark_gap_bundle_991004/candidates_50_bg652/candidate_pool.jsonl`

报告:

`runs/golden_v2/spark_gap_bundle_991004/candidates_50_bg652/candidate_pool_report.json`

规模:

- queries: 50
- chunks: 652
- candidates: 2420
- missing_chunks: 0
- sources: `bm25_sqlite_fts5`, `current_dense`, `current_sparse`, `alt_embedding:BAAI/bge-m3`, `random_neighbor`

候选来源覆盖:

- alt embedding: 50/50 query
- BM25 SQLite FTS5: 50/50 query
- current dense: 49/50 query
- current sparse: 50/50 query
- random neighbor: 50/50 query

候选 dataset 分布:

- 990901: 91
- 991002: 600
- 991003: 648
- 991004: 1081

991004 成为主要缺口补充来源,覆盖 49/50 query。

## 标注与补标

主标注:

- path: `runs/golden_v2/spark_gap_bundle_991004/candidates_50_bg652/judgments_50x12_timeout20.jsonl`
- queries: 50
- judged: 600
- relevant: 290
- failed: 11
- unresolved: 3

failed retry:

- path: `runs/golden_v2/spark_gap_bundle_991004/candidates_50_bg652/judgments_failed11_retry_timeout20.jsonl`
- judged: 11
- relevant: 6
- failed: 2
- unresolved: 2

unresolved top24 probe:

- path: `runs/golden_v2/spark_gap_bundle_991004/candidates_50_bg652/judgments_unresolved3_top24_timeout20.jsonl`
- queries: 3
- judged: 72
- relevant: 4
- failed: 0
- unresolved: 0

合并后:

- path: `runs/golden_v2/spark_gap_bundle_991004/candidates_50_bg652/judgments_50x12_plus_failed_retry_top24.jsonl`
- input rows: 683
- output rows: 634
- dropped failed rows: 13
- relevant: 300
- positive queries: 50/50
- unresolved: 0

## QC 与复核

QC:

- report: `runs/golden_v2/spark_gap_bundle_991004/candidates_50_bg652/qc_adjudicated_50x12_plus_failed_retry_top24_report.json`
- markdown: `runs/golden_v2/spark_gap_bundle_991004/candidates_50_bg652/qc_adjudicated_50x12_plus_failed_retry_top24_report.md`
- status: `warn`
- failures: none
- warning: no pure random-only candidates

复核队列:

- path: `runs/golden_v2/spark_gap_bundle_991004/candidates_50_bg652/review_queue_50x12_plus_failed_retry_top24.jsonl`
- items: 2
- reason: `no_alt_positive_support`

二次复判:

- reviewer: `deepseek-v4-flash`
- reviewed: 2
- relevant: 1
- limitation: reviewer model 与主 judge model 相同,无法消除同源偏置

仲裁:

- adjudicated: `runs/golden_v2/spark_gap_bundle_991004/candidates_50_bg652/adjudicated_judgments_50x12_plus_failed_retry_top24.jsonl`
- report: `runs/golden_v2/spark_gap_bundle_991004/candidates_50_bg652/adjudicated_judgments_50x12_plus_failed_retry_top24_report.json`
- conflicts: `runs/golden_v2/spark_gap_bundle_991004/candidates_50_bg652/adjudicated_conflicts_50x12_plus_failed_retry_top24.jsonl`
- policy: `manual_on_conflict`
- changed: 0
- kept: 1
- conflicts: 1

冲突项未自动覆盖,需要后续人工或独立 judge model 确认。

## Negative Control

为补齐“纯 random_neighbor false positive”估计,本轮额外构造了两套旁路 control。它们只用于 QC,不进入最终 golden draft。

同候选语料 random control:

- candidate pool: `runs/golden_v2/spark_gap_bundle_991004/candidates_50_bg652/candidate_pool_random_control_50x5.jsonl`
- judgments: `runs/golden_v2/spark_gap_bundle_991004/candidates_50_bg652/judgments_random_control_50x5_timeout20.jsonl`
- valid judgments: 249
- judge failed: 1
- relevant: 23
- random relevant rate: 9.24%
- QC: `fail`
- QC report: `runs/golden_v2/spark_gap_bundle_991004/candidates_50_bg652/qc_adjudicated_plus_random_control_report.json`

跨大域 negative control:

- candidate pool: `runs/golden_v2/spark_gap_bundle_991004/candidates_50_bg652/candidate_pool_cross_domain_negative_control_50x5.jsonl`
- judgments: `runs/golden_v2/spark_gap_bundle_991004/candidates_50_bg652/judgments_cross_domain_negative_control_50x5_timeout20.jsonl`
- valid judgments: 249
- judge failed: 1
- relevant: 20
- random relevant rate: 8.03%
- QC: `fail`
- QC report: `runs/golden_v2/spark_gap_bundle_991004/candidates_50_bg652/qc_adjudicated_plus_cross_domain_negative_control_report.json`

样例显示,control 中被判 relevant 的主要原因不是检索链路命中,而是合成背景语料存在大量通用模板句,例如“同一问题重复提交只保留最近一次有效记录”“状态页展示处理进度”等。这些句子在随机 chunk 中也能部分回答 query,导致 random/cross-domain negative control 被判为 grade 2 甚至 grade 3。

因此,当前主 draft 的 unresolved 已收敛为 0,但 false-positive control 暴露出一个数据质量风险: synthetic background 的通用规则复用过多,negative control 不够干净,judge 的“部分相关”口径也偏宽。下一轮需要引入更干净的独立负例池,或把主 qrels 阈值从 `grade > 0` 调整为更严格口径后重新对比。

干净外部 negative control:

- generator: GPT-5.3-Codex-Spark 子 Agent
- candidate pool: `runs/golden_v2/spark_gap_bundle_991004/candidates_50_bg652/candidate_pool_clean_external_negative_control_50x5.jsonl`
- judgments: `runs/golden_v2/spark_gap_bundle_991004/candidates_50_bg652/judgments_clean_external_negative_control_50x5_timeout20.jsonl`
- report: `runs/golden_v2/spark_gap_bundle_991004/candidates_50_bg652/judgments_clean_external_negative_control_50x5_timeout20_report.json`
- valid judgments: 250
- judge failed: 0
- relevant: 0
- random relevant rate: 0.00%
- QC: `pass`
- QC report: `runs/golden_v2/spark_gap_bundle_991004/candidates_50_bg652/qc_adjudicated_plus_clean_external_negative_control_report.json`

这组负例刻意避开实名、审核、风控、申诉、售后、订单、退货、退款、物流、材料、状态页、重复提交等业务词和近义表达,主题覆盖园艺、烘焙、天文观测、乐器保养、城市徒步、咖啡冲煮、摄影构图、收纳、语言学习、桌游、瑜伽、露营等。它的 false-positive 为 0,说明前两套 random/cross-domain control 的失败主要来自同一合成语料内的通用规则污染,而不是 judge 对明显无关文本普遍误判。

## Golden Draft

最终 draft:

`runs/golden_v2/spark_gap_bundle_991004/golden_draft_adjudicated_50x12_plus_failed_retry_top24/`

构建结果:

- `realistic_tune`: 38
- `realistic_blind`: 12
- `hard_tune`: 0
- `hard_blind`: 0
- unresolved: 0

## 测试

命令:

`pytest`

结果:

- 279 passed
- 3 skipped
- 7 warnings

## 后续建议

1. 用独立 reviewer model 或人工处理 1 条 conflict。
2. 下一轮候选池构造需要保留一批“纯 random_neighbor”候选,并且 random control 应来自干净外部负例池,不能从同一 synthetic background 中直接抽。
3. 将 `hard_reason` 非空的 query 单独扩为 hard set,避免 realistic headline 与 hard case 混报。
4. 若继续扩容,按 70% tune / 30% blind 固定切分,blind eval 不参与调参。
5. 构造独立负例池时避免复用“状态页展示进度”“重复提交覆盖旧单”等通用模板句,否则 random control 会测到语料污染,而不是纯 judge false positive。

## 2026-07-11: Blind 与 Hard 续跑

### Chunk 粒度 realistic blind

对 `realistic_blind.jsonl` 的 12 条 query 执行了活栈 blind run。所有运行都启用 `--precheck --require-chunk-references`,只以 `expected_chunk_ids` 计分。结果不混入 doc 粒度指标。

| 路由 | chunk Recall@10 | Hit@10 | MRR | nDCG@10 |
| --- | ---: | ---: | ---: | ---: |
| dense | 0.7398 | 1.0000 | 0.8438 | 0.7479 |
| SQLite FTS5 BM25 | 0.7077 | 0.9167 | 0.6556 | 0.6246 |
| sparse, threshold=0.0 | 0.6647 | 0.8333 | 0.7188 | 0.6318 |
| dense+sparse+BM25, weights=0.8/0.1/0.1 | 0.8410 | 1.0000 | 0.9444 | 0.8403 |

四条 run 都是 clean:无 failed source、无 zero-ranked query。融合 run 的 `Recall@10` 和排序指标均优于三条单路,但样本仅 12 条,只能作为链路诊断,不能据此冻结模型选择。

默认 sparse threshold=`0.4` 的单路运行得到 0 个候选,所有 chunk 指标为 0。将阈值降至候选池使用的 `0.0` 后恢复正常,说明该阈值不能直接沿用到当前真实/难例 query。详细产物位于 `runs/golden_v2/spark_gap_bundle_991004/blind_runs/`。

另外修复了评测 CLI 的 BM25-only 装配:当 `weighted_score` 仅启用单条路由时,该路由权重自动设为 `1.0`,避免默认 BM25 权重为 0 导致的 `active source fusion weight sum must be > 0` 异常。该行为有单测覆盖。

### Hard Set 首轮

使用既有 Spark 离线 hard seeds。其导入报告的生成器为 `gpt-5.3-codex-spark`,覆盖无关键词、相似文档、多约束、别名、数字时间、跨 chunk 六类。对当前四个 eval dataset 构造了 12 条 query、652 个 chunk、1,071 个去重候选的四源候选池。

- 首轮 top12:144 条判标,7 个 query 有正例,1 条 judge JSON 失败。
- 对 5 个无正例 query 扩到第 13-24 名:60 条判标,新增 1 个正例。
- JSON 失败单项重试成功。
- 有效判标共 204 条,8 个 query 有证据 chunk,4 个 query 在 top24 内仍无正例。
- QC 为 `warn`:unresolved rate=33.33%,且该候选池没有纯 random_neighbor 项,不能估计 false positive。

构建出的 Hard 草案为 `hard_tune=2`,`hard_blind=6`,`unresolved=4`。Hard blind 的融合诊断为 `Recall@10=1.0000`,`Hit@1=0.3333`,`MRR=0.5611`,`nDCG@10=0.6675`。这表明已保留样本主要暴露排序问题;由于 4 条召不回 query 未被写入 qrels,该结果存在选择偏差,不应作为 Hard Set 达标或对外指标。

Hard 产物位于 `runs/golden_v2/spark_gap_bundle_991004/hard_12x12/`。

### 10 万语料扩容计划

已生成 `runs/golden_v2/scale_100k_991004/scale_plan.md`。以现有 220 条 background chunk 为起点,计划补齐 99,780 条,拆为 20 个 eval-only batch,使用 dataset_id `992000` 至 `992019`;每批均包含 Spark bundle 导入、eval ingest、SQLite FTS5 BM25 backfill 与 alt embedding backfill 命令。计划估算 full candidate pool/judge 规模约 80,000 项。

实际执行 10 万扩容前仍需生成新的 Spark 离线 bundle。当前会话可用的子 Agent 模型列表没有 `gpt-5.3-codex-spark`,因此没有用其他模型替代生成外部输入,也没有开始灌入这 20 批数据。

### 验证

`pytest`: 281 passed, 3 skipped, 7 warnings。

### 人工裁决: spark-realistic-0036

人工裁决确认,query `spark-realistic-0036` 的原 grade-2 候选 `c5b547e2-5ba5-5dc4-8b94-8d85272019e5` 为不相关。该 chunk 只说明售后工单的支付凭证要求和风险条件下的补件时限,不能回答“是否可以先补齐材料,再申请退款”的流程顺序。

仲裁结果写入 `runs/golden_v2/spark_gap_bundle_991004/candidates_50_bg652/adjudicated_judgments_human_0036_not_relevant.jsonl`。主集与干净外部 negative control 的联合 QC 仍为 `pass`:299 条相关 judgment、unresolved rate=2.00%、pure random relevant rate=0。

随后扩标了该 query 的第 25-50 名候选。唯一新命中的 grade-2 候选也只给出“退款风险条件下补材料”的部分信息,仍不能支持流程顺序结论,因此按同一人工口径不进入 qrels。`spark-realistic-0036` 最终保留在 `unresolved.jsonl`,不纳入 realistic blind headline 指标;重建后的主集为 `realistic_tune=38`,`realistic_blind=11`,`unresolved=1`。
