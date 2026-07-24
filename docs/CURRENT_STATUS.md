# 当前开发状态

> 更新时间：2026-07-21
> 本页是项目级进度的唯一维护入口。专题文档中的历史状态和实验结论不得覆盖本页。

## 总体结论

评测研发主链路、20k 候选覆盖优化、黄金标注修正和独立 Blind v3 复验已经完成，当前处于
**离线验收收口 + LambdaMART 生产化准备**阶段。LambdaMART 已在完全未曝光 Blind v3 上证明
相对固定 Hybrid 有收益，但绝对 Recall@10 仍低，尚未接入生产默认链路。

| 范围 | 状态 | 说明 |
| --- | --- | --- |
| 项目解耦 Step 0-4 | 完成 | 独立 MySQL、eval Qdrant、ProductComputer、SQLite FTS5 BM25 已落地 |
| 项目解耦 Step 5 | 主体完成、证据待固化 | 代码、CLI、报告、结果台账和 import 边界已迁入；需用可识别 backend/fingerprint 的最终 clean run 固化 |
| 项目解耦 Step 6 | 代码完成、验收未关闭 | 已从 Qdrant BM25 转向 SQLite FTS5；已有三路 clean run 不能证明 BM25 生效，仍缺同口径 BM25 delta |
| Golden V2 | 主链路完成 | chunk 粒度、候选池、标注、QC、仲裁、tune/blind、20k 评测已落地 |
| 2000 条 LTR 数据 | 完成 | 420 条基集加 1580 条严格新增样本 |
| LambdaMART 实验 | 完成独立 Blind v3 验证 | Blind v3 Recall@10 从 22.67% 提升到 30.67%，净增 8.00pp |
| 候选深度优化 | 完成 | 2,000 条 Tune 分流候选覆盖率 98.55%；Blind v3 候选覆盖率 92.67% |
| Rerank / Cross Encoder | 已终止 | 直接重排低于 LambdaMART，作为附加特征的 Top50 Blind 下降；LambdaMART 固定使用不含重排分数的 `candidate_difference_v2` |
| LambdaMART 生产化 | 未完成 | 缺在线特征、模型版本、延迟、降级、Shadow 和回滚验证 |
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
- 2026-07-21 冻结决策：停止直接 Rerank 和 Cross Encoder 特征路线，不再继续 Top80；训练、评测和后续在线实现统一使用 `candidate_difference_v2`，不依赖用户是否配置重排模型。
- 2026-07-14 的 `scale20k-scoped-final-top10` 已达到 116/116 无单路失败、无零结果，但其 BM25 权重为 `0.0`，且运行快照未记录 `bm25_mode`/`computer_fingerprint`；它只能证明三路调用 clean，不能作为 SQLite FTS5 或 BM25 增量验收证据。
- 当前 20k 语料没有可用于严格编号/日期/版本号 Blind 题目的未曝光证据，因此 Blind v3 未伪造这两个场景，已作为语料缺口记录。

不同报告的数据分布、Query 数量和候选参数不同，只能在同一报告内比较变化量。
历史四域 `recall@10 ~= 0.901` 等价门槛不能与 Hard Blind v2 的绝对值直接比较。

## 尚未关闭的工作

| 优先级 | 工作 | 当前缺口 | 完成标准 |
| --- | --- | --- | --- |
| P0 | SQLite FTS5 / Step 5-6 最终验收 | 已有 clean run 的 BM25 权重为 0；`Snapshot` 尚无 BM25 backend/sidecar/computer fingerprint 字段，DB 结果仓储仍固定写 `computer_fingerprint=None` | 先补运行快照和台账写入；再重建 sidecar；同一冻结集分别跑 BM25 关闭/启用；两轮均 `failed_sources=0`、`zero_ranked=0`；快照记录 `bm25_mode=sqlite_fts5`、sidecar/fingerprint、参数和 git SHA；生成 BM25 Recall/MRR/延迟 delta 并写结果台账 |
| P0 | CI 纳入远端 | `.github/workflows/ci.yml` 未被 Git 跟踪，也未安装固定 SHA 的 toLink-Rag；契约测试在缺少 `src` 包时会 `importorskip`，存在干净 Runner “跳过但通过”的风险 | workflow 安装固定 SHA 的 toLink-Rag；CI 模式下缺包必须失败而非跳过；纳入提交并推送；PR/push 上 pytest、真实 contract、import-lint、Alembic heads 全部通过 |
| P1 | 短关键词回退门禁 | Blind v3 中 LambdaMART 比 Hybrid 低 3.33pp；尚无可冻结的置信度定义和阈值 | 新增独立 Tune 数据，仅在 Tune 选择低置信度判定和回退规则；冻结后使用全新 Blind v4 一次性验证，不能复用 Blind v3 调参 |
| P1 | 编号/日期/版本号覆盖 | 当前 20k 没有足够未曝光真实证据，Blind v3 未覆盖 | 增加 eval-only 真实格式语料；构造 chunk 粒度 Tune/Blind；通过证据支持、场景门禁和零泄漏检查 |
| P1 | 业务别名/同义词词表 | 当前只有 `scenario_alias` 和字符 n-gram 覆盖特征，没有可维护词典，也没有在 BM25/Sparse 前做确定性归一化 | 建立版本化、按业务域隔离的 canonical→aliases 词表；保留原 Query 并限制扩展数量；歧义词默认不扩展；词表版本写入运行快照；仅用 Alias Tune 选规则，冻结后在 Blind v4 验证 |
| P1 | 真实 Query 来源与元数据 | 2,000 条训练数据中 1,850 条由 Spark 生成；Blind v3 最终 Golden 没有 `source/query_source/generator_model/scenario` 字段，无法报告真实日志/客服/开源占比 | Blind v4 优先引入脱敏日志、客服/业务问题和开源 Query；保留来源、生成器、canonical query 和场景元数据；报告分来源指标，合成 Query 不能冒充真实 Query |
| P1 | 多正例 pooled qrels | Blind v3 的 150 条全部只有 1 个 `expected_chunk_id`，无法证明相似证据已完整标注 | 对冻结 Top50 多路 pooled 候选做独立相关性复核；允许一个 Query 对应多个相关 Chunk；统计新增正例率、未解决率和随机负例误判率；评测仍以 chunk 粒度为主 |
| P1 | 多 Chunk / 跨段落语料 | 当前 20k 基本是一文档一 Chunk，同文档差异特征恒为 0，不能代表真实长文档、跨段落或多 Chunk 检索 | 增加保留 `doc_id + ordinal` 的多 Chunk 文档族和 hard negatives；补 `cross_chunk`/跨段落 Query；单独报告单 Chunk与多 Chunk场景，不混成一个总指标 |
| P1 | LambdaMART 在线化 | 当前只支持离线训练/评测，没有可部署模型产物和在线排序器 | 固化 `candidate_difference_v2` 特征签名；实现模型序列化/加载、在线候选特征、版本校验、超时降级、延迟预算、Shadow、监控和回滚；不得重新引入 Rerank 特征 |
| P1 | 最终未曝光验收 | Blind v3 已揭盲，且每场景只有 30 条；不能再用于任何选参后的最终结论 | 上述参数和代码全部冻结后，使用证据与 Query 均隔离的 Blind v4 只跑一次；建议总量至少 500 条、主要场景至少 80 条，并报告置信区间/配对显著性；形成最终验收报告 |

### 推荐执行顺序

1. 先完成 SQLite BM25 A/B clean run，关闭解耦 Step 5-6 的证据缺口。
2. 将当前代码和 CI workflow 纳入版本控制，确保后续变更有自动门禁。
3. 补真实 Query 来源、多正例 pooled qrels、多 Chunk 文档族、短关键词 Tune、业务别名词表与编号类语料。
4. 只在 Tune 上冻结回退和词表扩展规则，实现不含 Rerank 的 LambdaMART 在线推理、降级和 Shadow。
5. 最后生成样本量足够的 Blind v4，一次性验收；不得根据 Blind v4 结果继续调参。

## 非阻塞增强项

- 第三判官自动仲裁。
- 数十万或百万规模时将 Alt Embedding sidecar 升级为 ANN/HNSW。
- 10 万背景语料分批扩容。
- 趋势看板和定时回归任务；不阻塞当前离线收口。

## 相关文档

- [解耦架构](architecture/decoupling-plan.md)
- [Golden V2 计划](plans/golden-v2-realistic-evaluation.md)
- [LambdaMART 实验](experiments/ltr-fusion-v1.md)
- [Query 候选分流](experiments/query-soft-routing-candidates.md)
- [统一报告索引](reports/REPORT_INDEX.md)
