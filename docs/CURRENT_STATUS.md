# 当前开发状态

> 更新时间：2026-08-29
> 本页是项目级进度的唯一维护入口。专题文档中的历史状态和实验结论不得覆盖本页。

## 总体结论

评测研发主链路、SQLite FTS5 BM25、真实来源元数据、多正例 qrels、结构化多 Chunk 语料和
无 Alias LambdaMART 生产契约均已完成。旧 v2 的离线元数据依赖已由生产可用的
`candidate_difference_v3` 关闭。全新 750 条 Blind v5 在参数冻结后只运行一次：Hit@10
`98.80%→99.07%`、MRR `92.16%→95.64%`，0 条 Top10 退化，p95 83.71ms。工程门禁通过，
但 500 条真实搜索 MRR 下降 0.70pp，因此该次 **Eval 验收的科学/工程建议**是“先 Shadow”，不是“该实验已经证明可全量切换”。这是一条历史验收结论。

当前 LinkRag 本地 `.env.development` 的实际排序模式已由负责人配置为 `active`。这只是当前开发环境的运行事实，不等于上述历史建议被新实验推翻，也不证明线上生产已经全量发布。新的鲁棒融合研究尚未进入 Gate A。P4-00 的 Eval 薄适配、精确 LinkRag pin、本地契约/全测和 SSH 隧道真实栈冒烟已经完成。历史正式 v2 三路 preflight 一次通过，Dense/Sparse 均走 exact，BM25=`sqlite_fts5`；旧五项 Dense 容差与 Sparse exact 只保留为历史决策。科研协议现为 v29、工程协议为 v22：provider-managed Dense/Sparse 不再设置数值误差或 exact 重放 Gate，改为每个获授权快照单次生成、结构校验与哈希封存，禁止因数值差异重跑或择优；本地确定性环节仍须 exact。Internal v6 的 30-family Dev 生成、A/B 双审、提交锁和主持人仲裁完成，首批结构产率 24/30，人工接纳 28/30。Dev 三路的 v2/v3 失败与 v4 完整性拒收均原样保留；修复后的独立 v5 已完成 28 Query、112 Chunk、3,056 候选，三路各 28/28 非空，112/112 已标注候选与 28/28 gold target 入候选并集，并通过 manifest/content root、SQLite/FTS5 与真实 Qdrant 112 点核验，无需重跑。P2-01 v1 已封存 28 个目标参照集合、84 个候选分数、A/B 与仲裁；人工效度 PASS，但共同支持 17.86%/57.14%，正式结论永久为 `INCONCLUSIVE`。唯一一次 72-family Dev 共同支持补充已完成四提交先锁后验和零仲裁终审：combined 共同支持 96%/99% PASS，但 supplement-only/combined 人工效度均为 `INCONCLUSIVE`，联合状态 terminal `INCONCLUSIVE`；正式分带未冻结，P2-01/P2-04 未完成，Gate 未授权且不得第三轮。独立研究 ID `ROBUST-FUSION-R2-2026-08-29` 已完成 outcome-aware 只读失败诊断、方案 B 批准、有效功效模拟 v2、结果前本地 seal、R1 hard-exclusion registry 与 outcome-blind 旧 inventory 审计；DeepSeek 正文来源的结果前 implementation、价格快照、128-slot registry、代码快照、授权模板及零网络 dry-run 均已封存。付费调用随后获持续授权；v2、v3 均作为 source implementation diagnostic fail-closed 保留。获批的 v4 三阶段恢复在任何响应前封存，单次正式命令于 1/128 永久接受后因 R2SRC-002/E 相同响应 hash 六次触发冻结 breaker，未自动重跑。只读诊断确认六个 payload hash 不同但唯一差异是 `stage_call`，无上一失败原因或确定性 diversification；六个响应逐字节相同且均因 equivalent normalized 后等于 reference 而机械失败。实际 breaker key 不含 orchestration attempt，最后响应先 fsync 后抛错而缺 `CALL_COMPLETED`，均记为未来恢复所需的实现修正。当前为 `SOURCE_RECOVERY_V4_DIAGNOSTIC_AWAITING_V5_DECISION`；formal 128-family source data lock 未形成，v5 未授权。R2 尚无正式锁定正文、编码器结果或人工包，旧 inventory 因独立 family/provenance/strata 元数据不足暂不合格，readiness/Gate 仍未授权。8 槽 C2 补充仍为 0 正文/0 标签。这些工作不产生 Gate 证据；正式候选快照仍受双仓 `dirty=false`、本轮远端绿色 CI run 和 clean `contract-lock.json` 阻塞。

R2 最新追加状态（覆盖上段 v4/v5 决策时点）：outcome-aware engineering v6 已在任何新响应前封存并单次运行；逐字节继承 R2SRC-001（Flash/v4），其余请求固定 `deepseek-v4-pro`。R2SRC-002 的 R/EP/E/C 最终机械通过并永久接受；R2SRC-003 的 R/EP/E 通过，但 C 的同一 response hash 六次且均 normalized 等于 equivalent candidate，账本先持久化 `CALL_COMPLETED` 再写 `HARD_BLOCK`，命令 fail-closed、未重跑且未回退 Flash。当前为 `SOURCE_RECOVERY_V6_ABORTED_FAIL_CLOSED_AWAITING_COORDINATOR_DECISION`；accepted ledger 为 2/128，formal data lock 未形成，尚无编码器结果或人工包，readiness/Gate 继续未授权。详见 [v6 fail-closed 报告](reports/robust_fusion_r2_source_recovery_v6_failure_2026_08_29.md)。

R2 最新收口状态（覆盖上述 v6 时点）：负责人授权的 Codex source v7 已逐字节 hard-lock 001/002，并以 append-only 首个机械 PASS 完成 003–128；accepted ledger SHA-256 为 `c022a74e…a2ae8`。旧 v7 final lock 因把同一 family 的 numeric/version 配对也纳入 cross-family template 去重而 fail-closed，未创建 data root；独立 v7.1 erratum 在正式数据前封存且只修复最终校验作用域，不改 parser、prereg、accepted rows、配额或门槛。正式 128-family/256-candidate source lock 已完成（families `f41a9f76…84231`）。冻结 E5/DistilUSE 随后单次本地运行成功，automatic manifest 为 `7b6c97e5…723c`；E5 全部不截断，DistilUSE 对 long_zh/long_en 各 96/96 输入按冻结 128-token 右截断。A/B relation 与 similarity 四个物理隔离盲包已生成，每位研究员 512 行，当前状态 `R2_AUTOMATIC_COMPLETE_AWAITING_FOUR_HUMAN_SUBMISSIONS`。尚无人工提交、仲裁或 measurement 决策；readiness/Gate 继续未授权。详见 [R2 source v7 与自动测量交接报告](reports/robust_fusion_r2_source_v7_automatic_handoff_2026_08_29.md)。

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
| Blind v5 生产契约验收 | 完成一次性验收 | 750 条，Hit@10 +0.27pp、MRR +3.48pp；0 lost、无降级、p95 83.71ms；当次验收建议仅批准 Shadow |
| 当前 LinkRag 开发配置 | `active` | `.env.development` 当前启用本地 LambdaMART v3；这是配置事实，不是生产发布证明或新研究结论 |
| 鲁棒融合研究 current-HEAD 契约 | 部分完成 | Eval 已适配 LinkRag `861f2481…` 的显式 collection 与当前候选契约；本地全测、LTR-v3 固定向量、SSH 隧道真实栈和正式 v2 三路 preflight 均通过。工作区仍 dirty，且缺此次版本的远端绿色 CI，因此尚无正式 `contract-lock.json` |
| 本地评测资产工作副本 | 已恢复并对账 | 三份 SQLite 已由 2026-08-27 分享包恢复；当前 Qdrant、BM25、Alt Embedding 已按数据集和 Chunk ID 只读盘点 |
| Gate A 数据资格 | P3-01 完成，P3-02 资格层已制品化但最终分母未冻结 | ID/hash-only manifest 已重放 T2、cMedQA2、DuRetrieval pinned 输入：T2 Dev exposed-only；cMedQA2 排除 80 个跨 split Query family；DuRetrieval 零删减且仅辅助。医学只作分层属性。最终分母仍待扩展 family、构造率、Internal v6 与功效封存，当前没有可直接进入 Gate A 的 cohort |
| Internal Stress v6 | 正式骨架、30-family Dev 双审仲裁与 Dev 三路 v5 核验完成；确认性人口未完成 | 首批机械结构产率 24/30；恢复后的 30 个提案完成 A/B 各 30+90+90 行，最终接纳 28/30 并物化为 28/112/112/28。v2/v3 失败、v4 完整性拒收均保留；v5 形成 3,056 条候选，三路各 28/28 非空，112/112 已标注候选与 28/28 gold target 入并集，独立完整性和真实存储核验通过。C2 8 槽包为 `PLANNED_EMPTY`；GateA/Blind 保持 `NOT_ELIGIBLE` |
| P2-01 Dev 相似度校准 | `P2_TERMINAL_INCONCLUSIVE_GATE_A_UNAUTHORIZED` | v1 永久 `INCONCLUSIVE`；唯一补充四提交已锁定并零仲裁终审。combined 共同支持 96%/99% PASS，但 supplement-only/combined 人工效度均 `INCONCLUSIVE`。无正式数值冻结、无第三轮；P2-01/P2-04 未完成、Gate 未授权 |
| Robust Fusion R2 相似度重设计 | `R2_AUTOMATIC_COMPLETE_AWAITING_FOUR_HUMAN_SUBMISSIONS` | Codex source v7 已完成 128/128，v7.1 正确收口 cross-family final lock；128-family/256-candidate fixed denominator 已锁。冻结 E5/DistilUSE 已单次运行并封存，四个 A/B relation/similarity 盲包各 256 行；尚无真实 submission、仲裁或 measurement 决策 |
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
- 2026-08-28 已从 `linkrag-eval-sqlite-share-20260827` 恢复三份本地工作副本：主 SQLite 现为 22 datasets、49,774 chunks、51 runs、2,884 metric rows；本地 BM25 31,072 条、Alt Embedding 20,772 条、当前 eval Qdrant 44,773 点。三路实际记录均按 Chunk ID 与主 SQLite 对账；历史 collection 的额外记录只作资产分布记录，未删除或重建。详见[恢复与逐数据集对账报告](reports/sqlite_share_restore_and_asset_reconciliation_2026_08_28.md)。
- `.env.eval` 指向的旧 eval MySQL 与分享包的 39,474 个共有 Chunk、51 个 run 和 2,884 个 aggregate metric 已逐项一致；两端 query/qrel 都为 0。`ssh linkcv` 是中间件主机，从未部署 LinkRag-Eval，也未发现可恢复的行级 qrels/candidate。分享包现正式定位为本研究的假设来源、工程可行性/预算证据和 provenance 底座；可复用已验证的 ID/provenance、索引与向量，但不代表每个 dataset 正文都可用，也不授予历史结果确认性资格。
- `990126=dureader_800_v2` 与 `990127=cmedqa_800_v2` 各 800 个官方 ID 均命中，但正文完全一致数均为 0 且内容呈现乱码；正式研究只使用 pinned 官方正文，不修改原 SQLite，也不继承这两集的历史向量/token。
- Gate A 公开数据 P3-01 已完成：原始 T2Ranking、C-MTEB T2、原始 Multi-CPR Medical、C-MTEB Medical、Lo/DRUID，以及独立的 DuRetrieval、上游 cMedQA2/C-MTEB Cmedqa 均已按固定 revision 落盘审计。DuRetrieval 的 pinned C-MTEB compact 实体以 100,001 corpus/2,000 Query/9,839 qrel 完整独立保留，Cmedqa 文本重合不扣除任何记录；它当前只作六单元 Gate 外的辅助稳健性数据。C-MTEB Cmedqa 100,001 个 passage 已逐 ID/hash 剥离为 88,242 Du-only、7,137 cMedQA2-only、2,086 both、2,536 unresolved；全部 unresolved 统一仅审计，不按 qrel 单列或继续处理。该 crosswalk 不含正文，也不替代上游 cMedQA2 原始实体。研究负责人已确认项目属于非商业科研，上游 `cMedQA2@85feb927…` 正式替换 MedicalRetrieval；其医学域只作预注册分层属性，不是独立研究终点或 Gate。
- Internal Stress v6 的 `internal-v6-dev/gatea/blind` 三个目录和 manifest 独立，GateA/Blind 有方法访问锁，Query/文档/证据/family assignment 最小 intake 与来源资格台账已落盘。协议 v13 下已完成只属于 Dev 的 30-family DeepSeek 受控合成先导：首批机械结构产率 24/30，四段恢复链不覆盖失败响应，43 次总调用后形成 30 个结构合格提案，API 估算费用人民币 `0.934791` 元。A/B 六份提交先锁后比，最终人工接纳 28/30（93.33%）；提交锁 SHA-256 为 `72d8b77ca601c925ff3840afc4812ac1395019d1930548cd98836201adefbb00`，最终 manifest SHA-256 为 `654ff9ff1959aeb18895b8a872c34665c9a262510f13d79146aca6183650b99a`。接纳项已物化为 28 Query/112 文档/112 证据标签/28 family assignment；release manifest SHA-256 为 `ad32fbb08a6b076dced1e438ff51060c46073b932cd259ff89beb157e5453bac`，追加 root manifest v9 SHA-256 为 `683e4967097e041a78fd7c5221c462ff4d75243127d8feb761cf7b0d40d7b2ab`。真实三路证据使用隔离 eval collection/SQLite 和双视图的一次性 Dev runner：v1 零尝试 superseded；v2 因缺 SSH 转发在首次 Qdrant probe 超时，v3 因本地 storage 父目录缺失而失败，两者均未发出编码请求且 collection 不存在；v4 完成检索但 manifest 纳入 SQLite 瞬态 sidecar，原制品保持不变并完整性拒收。独立 v5（plan SHA-256 `a7b159cc7f8f2d694e816b820971a8d3bce85c2f1fe392dde5c4c0003df7c03a`）完成 28 Query、112 Chunk、3,056 候选；三路各 28/28 非空，112/112 已标注候选和 28/28 gold target 入并集。manifest SHA-256 为 `a2ee6147a791903fa0aceae3be7f3b6a7f54277a58f5241cb62d1e944974734d`，content root 为 `1bae0b158a16f5d0aab161cff28245283fd487c9a5f41f23a6c4d02305c57550`；SQLite/FTS5 与真实 Qdrant 112 点核验一致。跨 v4/v5 的候选身份、Top-1、Top-10 和已标注候选排名稳定，但在线 Dense 最大绝对分数抖动约 `2.46×10⁻⁴`，不声称全部浮点逐字节一致；该差异按现行规则只作描述，v5 无需重跑。详见[独立核验报告](reports/internal_v6_dev_route_evidence_v5_verification_2026_08_29.md)。接纳的 28 个主冲突全为 `detectable_only`；C2 另建 8 槽空白补充包，manifest SHA-256 为 `ff4e00d857641a2d48e0ece509c29bf357f28918757dc4a1980f9906a681f347`，当前 0 正文/0 标签。GateA/Blind 仍要求独立自然来源锚点、非零自然候选配额和 family 零重合，当前人口为空、`NOT_ELIGIBLE`；历史 Blind v4/v5 不得改名填充。
- cMedQA2 三个上游 split 的 Query ID 虽不重叠，但规范化问题文本存在 80 个跨 split family，涉及 Train/Dev/Test 的 106/35/46 个 Query；它们全部排除出确认性资格母池。去除后 Train/Test 分别剩 99,894/3,954 个 Query 的资格上界，三个 split 的正例 answer ID 两两交集为 0。
- `ROBUST-FUSION-GATE-A-ELIGIBILITY-2026-08-28-v1` 已把上述规则转为可重放 ID/hash-only 制品：T2 258,042 Train/24,831 Dev、cMedQA2 100,000/4,000/4,000 split 和 DuRetrieval 100,001/2,000/9,839 三实体均通过固定文件摘要与结构校验。该制品只给资格上界，不是最终 Gate 分母。
- 历史 T2 曝光恢复得到 Blind v4 的 800 个精确 QID 和覆盖 Blind v5 实际 500 个 QID 的 502 项保守超集，已合并为 1,302 项排除制品。丢失的 11 个 ID 不伪恢复；因所有可审计历史来源都是 C-MTEB/原始 Dev，候选规则改为整个 Dev 只作 exposed-only，GateA/Blind 只从与 Dev QID 交集为 0 的原始 Train 按 family 再分。
- Gate A 的人工关系 schema 已拆为 `relevance_status`、`target_relation`、`adjudicability`，候选对关系另存；标注手册 v2 与相似度 manifest v10 已形成。研究负责人已淘汰 BGE-M3；真实三路仍是 `text-embedding-v4` Dense、Ark/`doubao-embedding-vision-251215` Learned Sparse、SQLite FTS5 BM25。历史 v1/v2 探针、一次 Dense 诊断与正式 v2 manifest 原样保留，用于证明当时的模型/schema/连通性；旧五项 Dense 容差与 Sparse exact 不再是当前 Gate。现行 `ROBUST-FUSION-PROVIDER-ROUTE-SNAPSHOT-POLICY-2026-08-29-v2` 只要求单次生成、结构校验和哈希封存，跨运行数值差异仅描述且不得触发重跑或择优。另在不读取研究数据时预选 `multilingual-e5-base@d1287505…` 为主实验相似度编码器、multilingual DistilUSE `@bfe45d07…` 为独立审计编码器，并确认两者与冻结的 Qwen/Jina Reranker 无制品复用；v1 人工效度通过但共同支持失败，唯一补充共同支持通过但人工效度不确定，正式分带仍未冻结，Gate A 仍未运行。
- P3-05 已在结果不可见时正式冻结 `Qwen3-Reranker-0.6B@e61197ed…` 生成式家族与 `jina-reranker-v2-base-multilingual@9cfeff2d…` 跨编码器家族。Qwen 对应项目真实测评；Jina 的独立学术采用证据包括 FEVER 2025（DOI `10.18653/v1/2025.fever-1.2`），但不据此声称其天然最优。两者精确权重/tokenizer/config/custom code、1024-token 固定合成探针和正逆序分数重放通过；隔离运行固定 ST 5.7.0、Transformers 4.57.6、einops 0.8.1。制品仍明确 `p3_05_complete=false`，尚缺 P2-06 资源契约与 Dev 长度覆盖/正式重放。
- outcome-blind Gate A 准入审计已建立：最近一次 v3 在 P2 人工结果提交前记录 13 项高层检查中 7 项通过、6 项阻塞，状态为 `NOT_READY_FOR_GATE_A`，artifact SHA-256 为 `487ec8162943d859afaf8a1f1ca75b10c0eb217e4fdd662c58f91366c8a61af1`。此后 P2-05 已通过，因此 v3 的 `BLOCKED_HUMAN` 是历史快照，不是当前事实；在生成 v4 outcome-blind 审计前不得擅自重算总体通过项数。其余自动工作、数据人口、clean/CI/封存阻塞仍在，该审计不能解锁 GateA/Blind。
- 过程透明性记录：在 P2 补充人工提交尚未完成时，为诊断 readiness 单元测试及协议版本对齐，曾调用 outcome-blind readiness CLI；其默认行为意外写出 `runs/robust_fusion/gate_a/readiness-preflight-v4.json`。该文件随后移入本机废纸篓，正式 runs 已确认不再保留；未读取任何确认性排序结果，未运行 Gate A/B，科研结论与授权状态均不变。移出前 shell 列表观察到的文件系统修改时间为 `2026-08-29 16:48`（Asia/Shanghai），但精确调用时刻为 `unknown`，原文件 SHA-256 为 `unknown`，不得恢复文件补充取证。后续版本对齐只使用纯 `build_report(...)` 与相关单元测试；当时在 P2 四提交完成正式终审前不得调用会写正式 preflight 的入口。现 P2 已 terminal `INCONCLUSIVE`，没有 readiness 合法入口，仍不得生成 v4 preflight。完整记录见[共同支持补充报告第 6 节](reports/robust_fusion_similarity_support_supplement_2026_08_29.md#6-过程偏差台账未到时点的-outcome-blind-readiness-写入)。
- P4-01 候选字段缺口审计已完成：当前 LinkRag 的 `candidate_hits/route_hits` 足以提供融合截断前候选并集和逐路 score/rank；Eval 通用 `StageOutput/Snapshot`、历史 LTR cache 与 SQLite 不能直接充当确认性快照。Internal v6 的 Dev runner 已实现不透明 ID、双目录视图和禁止字段扫描，作为 P4-02/P4-05 的局部先导；但它缺正式压力链、clean/CI/lock 与通用置换不变性验收，明确不完成 P4-02/P4-05。正式快照仍固定为 Eval 专用双视图文件快照，且不修改生产 LinkRag。
- P2 桌面校准已完成：v1 泄漏包和模型/工具试填保持无资格；v2 首轮真实 A/B 提交、失败审查和锁定快照完整保留，5 个制品缺陷案例由 v3 补包一对一替换。最终合并 12 例、13 条候选、9 条事实冲突和 1 条候选对通过全部冻结准入线，格式与零容忍构念错误为 0；标注手册已升级为 v2。最终机器结论 SHA-256 为 `fe906b9e755135cfe4fe6607297aec5c5a0c2b2c0a0a5118e4c38ada9a01ef1c`，提交锁 SHA-256 为 `9d743fb23d4d88d128229a81d381aab444550e2663e11eacbe296cad0c722f82`。研究负责人已进一步核验 P2 与 Internal v6 的正式提交均由两名研究员独立完成、未使用模型或工具代填；追加的[机器可读核验旁证](reports/robust_fusion_human_annotation_verification_2026_08_29.json) SHA-256 为 `6e4746c0a1b83455d7b62880490a53ebb93b7f03f94f2ede1a30cb5770d80419`，不改写任何原始提交或裁定。主持人预先知道 v3 key 的事实已披露，不声称主持人盲态；Gate A/B 均未运行。
- P2-01 Dev 相似度 v1 的自动校准与人工效度审计已完成：[自动校准报告](reports/robust_fusion_similarity_dev_calibration_2026_08_29.md)与[仲裁后效度报告](reports/robust_fusion_similarity_human_review_2026_08_29.md)记录人工六项门槛全 PASS、共同支持 17.86%/57.14%，正式结论永久为 `INCONCLUSIVE`。唯一一次[共同支持补充](reports/robust_fusion_similarity_support_supplement_2026_08_29.md)在任何新分数前锁定 72-family、每侧 combined 分母 100、missing-as-miss 与无第三轮规则；四提交锁 `7a3ca434…2ae6`。锁后缺失 finalizer 以 implementation manifest `af35908b…499fb` 先封存后单次执行；final manifest `ea40f4f0…f2b35`。combined 共同支持 96%/99% PASS，但 supplement-only/combined E5 overall 0.1775/0.3968 未达 0.50，两个人工效度均 `INCONCLUSIVE`，联合 terminal `INCONCLUSIVE`。不生成正式数值冻结，P2-01/P2-04 和 Gate 均未完成且无第三轮。
- 独立 R2 只读诊断已按 outcome-aware/exploratory 地位先锁计划与输入 hash、后单次运行，manifest SHA-256 为 `872b45bdda7c236d563945814ec96d5ea88bed25da62614024af6f535dfd3bd8`。方案 B 随后获批准；有效功效模拟 v2 在 ρ=.60 的完整门禁通过率为 91.25%，正式 prereg manifest SHA-256 为 `b3c75dee6140c7aa57b865e592054ff5534405872efef4769b9636cccd09c71b`，R1 exclusion registry 为 `f54115330edeabb077d149f09106051a210fb086669208dd5177839989c4fe16`。旧 Gate inventory 审计未解析结果内容，因独立资格元数据不足为 `NOT_ELIGIBLE_METADATA_INSUFFICIENT`。DeepSeek source-generation v2–v5 现场和两份诊断均永久保留；v6 preparation manifest `91685d72…8091` 在任何 Pro 响应前封存，静态 endpoint contract 零 probe。唯一命令以 Pro/v6 永久接受 R2SRC-002，随后 R2SRC-003/C 同一 response hash 六次且均因 normalized 等于 equivalent 机械失败，`CALL_COMPLETED` 后触发 frozen `HARD_BLOCK`；未重跑、未回退 Flash。accepted ledger 2/128，formal data lock 未形成，当前等待协调方决定。详见 [R2 v6 fail-closed 报告](reports/robust_fusion_r2_source_recovery_v6_failure_2026_08_29.md)。
- R2 后续由负责人授权 Codex source v7 收口：001/002 继承不改，003–128 只使用冻结 slot metadata 直接撰写并 append-only 首个机械 PASS 锁定。最终 source lock、单次 E5/DistilUSE 与四个人工盲包均完成；自动分数仅作待人工校准的测量输入，不是真值。当前唯一缺口是两名真实研究员各自独立填写 512 行，之后才能先锁后验、仲裁和唯一 finalizer。
- 2026-07-26 PR #1 的 GitHub Actions run `30191660556` 已全绿：330 项非集成测试、import-lint、16 项真实 contract 和 Alembic heads 门禁全部通过；同时修复了 `golden` 数据忽略规则误伤源码包的问题。
- `candidate_difference_v3` 已删除 8 个 Golden scenario 特征，线上构造只接收 Query、三路候选和候选正文；qrels 只用于训练标签。Alias 已从冻结 CLI 和模型包移除。
- 无 Alias Tune OOF 450 条：Hit@10 `97.33%→99.33%`、MRR `84.93%→96.59%`，9 gained / 0 lost；仅据 Tune 冻结 33 轮和短词阈值 0.1。
- Blind v5 包含 500 条排除历史曝光 Query 的 T2Retrieval 与 250 条新结构化题；475/750 为多正例。唯一运行 Hit@10 `98.80%→99.07%`、MRR `92.16%→95.64%`，2 gained / 0 lost。
- Blind v5 真实搜索子集 Hit@10 持平、MRR `95.80%→95.10%`；跨 Chunk/编号/版本号 MRR 明显提升。该差异决定当次验收只能建议先 Shadow，不得把整体合成结构收益外推为真实业务收益；后续负责人把开发环境改为 `active` 不会反向改变这条历史证据边界。
- 最终模型 `candidate-difference-v3-20260728-final33` 使用 `lightgbm_text_v1`，特征签名 `52a69c3b...b8782d7b`；版本化包位于 `models/candidate-difference-v3-20260728-final33/`，内含完整超参、5 个文件哈希、3 个测试向量和 weighted score 基线回滚。

不同报告的数据分布、Query 数量和候选参数不同，只能在同一报告内比较变化量。
历史四域 `recall@10 ~= 0.901` 等价门槛不能与 Hard Blind v2 的绝对值直接比较。

## 尚未关闭的工作

| 优先级 | 工作 | 当前缺口 | 完成标准 |
| --- | --- | --- | --- |
| P0 | 鲁棒融合研究 current-HEAD 契约复验 | 薄适配、精确 pin、本地全测、LTR 固定向量、真实栈冒烟和正式 v2 三路 preflight 已完成；仍缺 clean 双仓、远端绿色 CI run 和正式 lock | 形成可提交 clean 状态、取得绿色 CI、生成 `contract-lock.json` |
| 研究 P2/P3/P4 | Gate A 构念、数据与测量工具 | R1 P2-01 永久 terminal `INCONCLUSIVE`；R2 128-family source/fixed denominator、单次冻结编码与四个盲包已完成，但尚无四份真实 submission、仲裁或 measurement PASS | 两名真实研究员各独立完成 512 行；随后先锁后验、必要仲裁与唯一 finalizer。当前不得运行 readiness/Gate |
| P1 | 生产模式证据补齐 | 当前开发配置为 `active`，但本页没有新的线上/Shadow 观测能够替代 Blind v5 的历史风险结论 | 保留 weighted score 回滚；以明确的发布范围、延迟、回退率、Top10 变化和业务反馈另行形成运行报告 |
| P2 | 真实业务效果增强 | 当前真实 Query 来源仍是开源检索，不是脱敏生产 Query | 如继续优化，建立全新 Tune/Blind v6；禁止复用 Blind v5 调参 |

### 推荐执行顺序

1. R1 P2-01 已按唯一补充停止规则得到 terminal `INCONCLUSIVE`；R2 方案 B 已正式预注册，DeepSeek v2–v6 历史现场永久保留。Codex source v7、正式 128-family lock、单次冻结编码和 A/B 四盲包已经完成。当前唯一动作是两名真实研究员各独立完成 relation 256 + similarity 256 行；四提交锁定、校验/仲裁和唯一 finalizer 前不得运行 readiness/Gate。
2. P4-00 可独立并行：Dense 重放策略和正式 v2 三路 preflight 已关闭；保留已完成的 Eval 薄适配、精确 LinkRag pin、本地全测和真实栈证据，在双仓 clean 后运行远端 CI 并保存绿色 run/report 与 `contract-lock.json`。正式快照仍须等待 P2/P3 冻结。
3. Blind v4、Blind v5 均已封存，禁止二次运行或据此调参；其 Query 条件化 T2 子池不得进入新研究的确认性候选生成。
4. 将 Blind v5 的“先 Shadow”保留为历史验收建议，将 `.env.development=active` 记录为当前配置事实；在没有新的运行报告时，不把两者合并成“已证明全量可用”。weighted score 始终作为启动、超时、错误和主动回滚降级路径。
5. 若需提高真实搜索 MRR，创建全新 Tune/Blind v6，优先补脱敏业务 Query 并预注册门禁。

## 非阻塞增强项

- 将第三判官自动仲裁扩展到后续新数据版本。
- 数十万或百万规模时将 Alt Embedding sidecar 升级为 ANN/HNSW。
- 10 万背景语料分批扩容。
- 趋势看板和定时回归任务；不阻塞当前离线收口。

## 相关文档

- [鲁棒融合科研协议](plans/robust-fusion-research.md)
- [鲁棒融合工程实施协议](plans/robust-fusion-engineering.md)
- [鲁棒融合研究推进清单](plans/robust-fusion-todo.md)
- [Internal Stress v6 数据协议](plans/robust-fusion-internal-stress-v6.md)
- [C2 三分边界最小补充方案](plans/robust-fusion-c2-boundary-supplement.md)
- [鲁棒融合标注手册](plans/robust-fusion-annotation-handbook.md)
- [鲁棒融合实验相似度 manifest](plans/robust-fusion-similarity-manifest.md)
- [R2 失败诊断报告](reports/robust_fusion_r2_similarity_failure_diagnostic_2026_08_29.md)
- [R2 预注册与资格审计报告](reports/robust_fusion_r2_preregistration_and_eligibility_2026_08_29.md)
- [R2 DeepSeek 正文来源离线准备报告](reports/robust_fusion_r2_source_generation_offline_preparation_2026_08_29.md)
- [R2 DeepSeek 正文来源实现规范](plans/robust-fusion-r2-source-generation-implementation-v1.md)
- [R2 正式研究协议](plans/robust-fusion-r2-research.md)
- [R2 正式相似度 measurement](plans/robust-fusion-r2-similarity-measurement.md)
- [R2 研究协议草案](plans/robust-fusion-r2-research-draft.md)
- [R2 相似度 measurement 草案](plans/robust-fusion-r2-similarity-measurement-draft.md)
- [R1 → R2 继承/排除矩阵](plans/robust-fusion-r1-to-r2-inheritance-matrix.md)
- [R2 到 Gate A Delta Checklist](plans/robust-fusion-r2-gate-a-delta-checklist.md)
- [R2 source v7 与自动测量交接报告](reports/robust_fusion_r2_source_v7_automatic_handoff_2026_08_29.md)
- [R2 source lock v7.1 执行器说明](plans/robust-fusion-r2-source-lock-v7-1.md)
- [R2 自动测量执行规范](plans/robust-fusion-r2-automatic-execution-v1.md)
- [鲁棒融合文献地图](plans/robust-fusion-literature.md)
- [鲁棒融合主张—证据—空缺表](plans/robust-fusion-evidence.md)
- [Gate A 数据覆盖、标签覆盖与研究缺口审计](reports/robust_fusion_gate_a_data_coverage_audit_2026_08_28.md)
- [P2 与 Internal v6 正式人工标注核验旁证](reports/robust_fusion_human_annotation_verification_2026_08_29.json)
- [P2-01 Dev 相似度自动校准与盲审发包](reports/robust_fusion_similarity_dev_calibration_2026_08_29.md)
- [P2-01 Dev 相似度人工审阅与仲裁后效度](reports/robust_fusion_similarity_human_review_2026_08_29.md)
- [解耦架构](architecture/decoupling-plan.md)
- [Golden V2 计划](plans/golden-v2-realistic-evaluation.md)
- [LambdaMART 实验](experiments/ltr-fusion-v1.md)
- [Query 候选分流](experiments/query-soft-routing-candidates.md)
- [统一报告索引](reports/REPORT_INDEX.md)
- [Blind v4 最终一次性验收](reports/blind_v4_final_acceptance_2026_07_24.md)
- [Blind v5 无 Alias 生产契约验收](reports/blind_v5_production_contract_acceptance_2026_07_28.md)
- [SQLite 工作副本恢复与检索资产逐数据集对账](reports/sqlite_share_restore_and_asset_reconciliation_2026_08_28.md)
