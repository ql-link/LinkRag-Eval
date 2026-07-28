# 当前开发状态

> 更新时间：2026-07-28
> 本页是项目级进度的唯一维护入口。专题文档中的历史状态和实验结论不得覆盖本页。

## 总体结论

评测研发主链路、SQLite FTS5 BM25、真实来源元数据、多正例 qrels、结构化多 Chunk 语料和
无 Alias LambdaMART 生产契约均已完成。旧 v2 的离线元数据依赖已由生产可用的
`candidate_difference_v3` 关闭。全新 750 条 Blind v5 在参数冻结后只运行一次：Hit@10
`98.80%→99.07%`、MRR `92.16%→95.64%`，0 条 Top10 退化，p95 83.71ms。工程门禁通过，
但 500 条真实搜索 MRR 下降 0.70pp，故当前结论是“可交付生产 Shadow”，不是“可直接全量切换”。

| 范围 | 状态 | 说明 |
| --- | --- | --- |
| 项目解耦 Step 0-4 | 完成 | 本地 SQLite、eval Qdrant、ProductComputer、SQLite FTS5 BM25 已落地 |
| 项目解耦 Step 5 | 完成 | 代码、CLI、报告、结果台账和 import 边界已迁入；最终 A/B 快照已固化 backend、sidecar/computer fingerprint、Git SHA 与工作区指纹 |
| 项目解耦 Step 6 | 完成 | SQLite FTS5 已在同一冻结 116 条、20k 语料上完成 OFF/ON clean A/B；Recall@10 提升 5.42pp |
| Golden V2 | 主链路完成 | chunk 粒度、候选池、标注、QC、仲裁、tune/blind、20k 评测已落地 |
| 2000 条 LTR 数据 | 完成 | 420 条基集加 1580 条严格新增样本 |
| LambdaMART 实验 | 完成独立 Blind v3 验证 | Blind v3 Recall@10 从 22.67% 提升到 30.67%，净增 8.00pp |
| 候选深度优化 | 完成 | 2,000 条 Tune 分流候选覆盖率 98.55%；Blind v3 候选覆盖率 92.67% |
| Rerank / Cross Encoder | 已终止 | 新链路不依赖远端 Rerank；活动 LambdaMART v3 不含重排分数 |
| LambdaMART 在线化 | 完成 | v3 仅使用线上字段；无 Alias；序列化、特征签名、预算/超时降级、Shadow、监控、回滚和测试向量均已验证 |
| Blind v4 最终验收 | 完成一次性验收 | 750 条，Hit@10 +0.40pp、MRR +7.62pp；结果已 seal，禁止复用调参 |
| Blind v5 生产契约验收 | 完成一次性验收 | 750 条，Hit@10 +0.27pp、MRR +3.48pp；0 lost、无降级、p95 83.71ms；仅批准生产 Shadow |
| 10 万背景语料 | 暂缓 | 当前先完善 20k；不属于本轮阻塞项 |

## 已固化结果

- 2000 条训练候选并集覆盖率基线为 95.25%；Tune-only 分流深度优化后为 98.55%。
- 185 条无有效编号/日期/版本号文本的 Tune 场景标签已修正；Blind v2 已改写 4 条无证据条件 Query，并修正 33 条场景标签；严格 `exact_identifier` 门禁已接入构建脚本。
- Tune OOF：分流 Hybrid Recall@10 为 35.75%，冻结 LambdaMART 为 44.90%，提升 9.15pp；候选并集覆盖率 98.55%。
- 全新 Blind v2 共 210 条，Query 和正标签与历史集合隔离。
- Blind v2：固定 Hybrid Recall@10 为 20.95%，1050/2000 模型均为 27.62%。
- 2000 模型相对 1050 模型没有提高 Blind v2 Top10 命中数，但 MRR@10 从 7.13% 提升到 8.46%。
- Blind v2 原三路候选并集覆盖率为 89.05%；冻结候选分流回归为 98.10%，但它不再是无偏 Blind。
- 原 23 条候选缺失中，22 条可在 `300/150/300` 深度内找回，1 条三路仍未找回。
- Blind v3 共 150 条、五类各 30 条，Query 和正证据与历史集合重叠均为 0；候选缓存 150/150 成功。
- Blind v3：分流 Hybrid Recall@10 22.67%，LambdaMART 30.67%，提升 8.00pp；候选覆盖率 92.67%。
- Blind v3 分场景：相似文档 +23.33pp、多条件 +13.33pp、别名 +6.67pp、自然语言持平、短关键词 -3.33pp。
- `qwen3-rerank` Top50 已作为 LambdaMART 四项附加特征完成全链路验证：Tune 44.90%→45.60%，Blind v3 30.67%→30.00%，不进入默认链路。
- `qwen3-vl-rerank` 在 Blind v3 固定 Top50 的 150 条批量对照中为 24.00%，仅比 `qwen3-rerank` 的 22.67% 多 2 条命中（配对检验 `p=0.856`），仍低于 LambdaMART 的 30.67%。
- 2026-07-21 的历史决策停止直接 Rerank 和 Cross Encoder 特征路线；当时冻结的 `candidate_difference_v2` 已被 2026-07-28 的生产安全 v3 取代。
- 2026-07-14 的 `scale20k-scoped-final-top10` 已达到 116/116 无单路失败、无零结果，但其 BM25 权重为 `0.0`，且运行快照未记录 `bm25_mode`/`computer_fingerprint`；它只能证明三路调用 clean，不能作为 SQLite FTS5 或 BM25 增量验收证据。
- 当前 20k 语料没有可用于严格编号/日期/版本号 Blind 题目的未曝光证据，因此 Blind v3 未伪造这两个场景，已作为语料缺口记录。
- 2026-07-24 已从 eval MySQL 权威语料重建纯 20k SQLite FTS5 sidecar：992000–992003 各 5,000 chunks，逻辑 SHA-256 为 `aa475796be62bede59b11fc6d116d4edf19bd770c4f64eb9127397f14ac6114f`。
- SQLite FTS5 最终 A/B 使用同一 116 条冻结集与同一工作区/sidecar 指纹：OFF/ON 均 `failed_sources=0`、`zero_ranked=0`；chunk Recall@10 `31.32%→36.74%`（`+5.42pp`），MRR `16.58%→17.03%`（`+0.45pp`）。延迟 delta 受外部编码冷启动与网络抖动影响，只作观测，不作 BM25 因果结论。
- `Snapshot` 与 DB 台账现已记录 `bm25_mode`、sidecar identity、`computer_fingerprint`、feature version、Git SHA、dirty 状态和工作区内容指纹；两条 v2 run 已写入 `eval_run` / `eval_metric_result`。
- Blind v4 数据包包含 450 Tune、750 Blind 和 10,300 chunks；Query 来源为 800 条开源 T2Retrieval 与 400 条明确标记的 eval-only 合成构造题，全部带来源、版本、业务域、canonical query 和场景元数据。
- 300 条开源 Tune 的 pooled Top50 共 15,000 对完成独立复核：1,384 个分歧全部仲裁，未解决 0；正 qrels 从 1,385 增至 1,782，多正例 Query 为 270/300。
- 新增 100 个三段文档、300 chunks，覆盖跨 Chunk、跨段落、编号、日期、版本号和同文档干扰；最终 Tune/Blind 多正例分别为 306/490。
- 历史 Blind v4 曾冻结 Alias `general_web_search.2026-07-24.v1`；因无法直接复用到生产，它不再进入活动 v3 候选、训练或推理链路。
- Blind v4 历史短词门禁仅由当时 Tune 选择：长度 `<=10` 且 `ltr_top12_margin < 0.3` 时回退 Hybrid；活动 v3 不沿用该阈值。
- Blind v4 历史在线模型为 `candidate-difference-v2-20260724-final50`，仅保留追溯；活动生产候选是下述 v3 模型。
- Blind v4 唯一运行 `blind-v4-final-once-20260724`：750/750 clean；Hit@10 `98.5333%→98.9333%`（+0.4000pp），MRR `90.4054%→98.0213%`（+7.6158pp）；4 gained / 1 lost，95% CI `[-0.1333pp,+1.0667pp]`，McNemar `p=0.375`。
- 2026-07-25 已从 `100.86.10.52` 停机前备份中的 `tolink_rag_eval_db` 只读迁移到本地 `runs/linkrag_eval.sqlite3`：20 datasets、39,474 chunks、51 runs、2,884 metric rows；源库的 query/qrel 均为 0。六表计数和内容摘要一致，正常运行不再依赖远端 MySQL。
- 2026-07-26 PR #1 的 GitHub Actions run `30191660556` 已全绿：330 项非集成测试、import-lint、16 项真实 contract 和 Alembic heads 门禁全部通过；同时修复了 `golden` 数据忽略规则误伤源码包的问题。
- `candidate_difference_v3` 已删除 8 个 Golden scenario 特征，线上构造只接收 Query、三路候选和候选正文；qrels 只用于训练标签。Alias 已从冻结 CLI 和模型包移除。
- 无 Alias Tune OOF 450 条：Hit@10 `97.33%→99.33%`、MRR `84.93%→96.59%`，9 gained / 0 lost；仅据 Tune 冻结 33 轮和短词阈值 0.1。
- Blind v5 包含 500 条排除历史曝光 Query 的 T2Retrieval 与 250 条新结构化题；475/750 为多正例。唯一运行 Hit@10 `98.80%→99.07%`、MRR `92.16%→95.64%`，2 gained / 0 lost。
- Blind v5 真实搜索子集 Hit@10 持平、MRR `95.80%→95.10%`；跨 Chunk/编号/版本号 MRR 明显提升。该差异决定生产只能先 Shadow，不得把整体合成结构收益外推为真实业务收益。
- 最终模型 `candidate-difference-v3-20260728-final33` 使用 `lightgbm_text_v1`，特征签名 `52a69c3b...b8782d7b`；版本化包位于 `models/candidate-difference-v3-20260728-final33/`，内含完整超参、5 个文件哈希、3 个测试向量和 weighted score 基线回滚。

不同报告的数据分布、Query 数量和候选参数不同，只能在同一报告内比较变化量。
历史四域 `recall@10 ~= 0.901` 等价门槛不能与 Hard Blind v2 的绝对值直接比较。

## 尚未关闭的工作

| 优先级 | 工作 | 当前缺口 | 完成标准 |
| --- | --- | --- | --- |
| P1 | 生产 Shadow | 离线工程契约通过，但真实搜索 MRR -0.70pp，且不等于真实业务流量 | 生产端接入 v3 模型包，保留 weighted score 回滚；观测延迟、回退率、Top10 变化和业务反馈后再决定默认切换 |
| P2 | 真实业务效果增强 | 当前真实 Query 来源仍是开源检索，不是脱敏生产 Query | 如继续优化，建立全新 Tune/Blind v6；禁止复用 Blind v5 调参 |

### 推荐执行顺序

1. 保持 PR #1 已全绿的固定 SHA 依赖、源码跟踪和 contract 强制门禁，后续变更不得绕过。
2. Blind v4、Blind v5 均已封存，禁止二次运行或据此调参。
3. 生产项目先接入 v3 制品并 Shadow，weighted score 始终作为启动、超时、错误和主动回滚降级路径。
4. 若需提高真实搜索 MRR，创建全新 Tune/Blind v6，优先补脱敏业务 Query并预注册门禁。

## 非阻塞增强项

- 将第三判官自动仲裁扩展到后续新数据版本。
- 数十万或百万规模时将 Alt Embedding sidecar 升级为 ANN/HNSW。
- 10 万背景语料分批扩容。
- 趋势看板和定时回归任务；不阻塞当前离线收口。

## 相关文档

- [解耦架构](architecture/decoupling-plan.md)
- [Golden V2 计划](plans/golden-v2-realistic-evaluation.md)
- [LambdaMART 实验](experiments/ltr-fusion-v1.md)
- [Query 候选分流](experiments/query-soft-routing-candidates.md)
- [统一报告索引](reports/REPORT_INDEX.md)
- [Blind v4 最终一次性验收](reports/blind_v4_final_acceptance_2026_07_24.md)
- [Blind v5 无 Alias 生产契约验收](reports/blind_v5_production_contract_acceptance_2026_07_28.md)
