# 文档目录与完成状态

> 更新时间：2026-07-21
> 本目录回答“有哪些文档”和“文档对应的工作是否完成”。项目实时进度仍以
> [CURRENT_STATUS.md](CURRENT_STATUS.md) 为准。

## 状态定义

| 状态 | 含义 |
| --- | --- |
| 完成 | 文档内容完整，对应阶段已经形成可复现结果或稳定规则 |
| 部分完成 | 文档完整，但对应工程、验收或生产接入仍有未完成项 |
| 待验证 | 候选方案已记录，但尚未通过独立数据验证，不是默认方案 |
| 持续维护 | 文档已经可用，但需要随项目状态或报告产物持续更新 |
| 已归档 | 历史设计已被替代，仅供追溯，不再按其内容继续实施 |

## 一、项目入口与规则

| 文档 | 文档状态 | 对应工作状态 | 作用 |
| --- | --- | --- | --- |
| [项目 README](../README.md) | 完成 | 持续维护 | 项目介绍、启动方式和顶层导航 |
| [实现约定](../AGENTS.md) | 完成 | 持续维护 | 依赖边界、存储隔离、配置、测试和安全规则 |
| [下一对话交接](HANDOFF.md) | 完成 | 持续维护 | 冻结决策、关键缺口、执行顺序、必读文档和工作区注意事项 |
| [文档中心](README.md) | 完成 | 持续维护 | 文档分类和推荐阅读顺序 |
| [当前开发状态](CURRENT_STATUS.md) | 完成 | 持续维护 | 项目级完成度、验收缺口和下一步的唯一入口 |
| 本文档 | 完成 | 持续维护 | 全部人工维护文档的目录和完成状态 |

## 二、权威架构

| 文档 | 文档状态 | 对应工作状态 | 未完成内容 |
| --- | --- | --- | --- |
| [解耦独立化方案](architecture/decoupling-plan.md) | 完成 | 部分完成 | Step 0-4 完成；Step 5-6 仍需可识别 SQLite backend/fingerprint 的 A/B clean run、BM25 delta 和最终验收固化 |

## 三、当前实施方案

| 文档 | 文档状态 | 对应工作状态 | 未完成内容 |
| --- | --- | --- | --- |
| [Golden V2 真实召回评测](plans/golden-v2-realistic-evaluation.md) | 完成 | 完成当前 20k 验收 | 问题标注修正、exact identifier 门禁、2,000 Tune 重训和未曝光 Blind v3 已完成；编号类语料补充和 10 万扩容属于后续阶段 |

## 四、实验与候选方案

| 文档 | 文档状态 | 实验状态 | 结论或剩余工作 |
| --- | --- | --- | --- |
| [LambdaMART 三路融合](experiments/ltr-fusion-v1.md) | 完成 | 部分完成 | Blind v3 相对 Hybrid 提升 8.00pp；Rerank 和 Cross Encoder 特征路线已终止，LambdaMART 固定为不含重排分数的 v2；生产在线推理、短词回退、降级、Shadow 和回滚未完成 |
| [Query 重写配对基准](experiments/query-rewrite-benchmark-v1.md) | 完成 | 完成 | 当前数据上 Recall 无提升、MRR 下降，不进入默认链路；保留作对照实验 |
| [Query 软分流候选](experiments/query-soft-routing-candidates.md) | 完成 | 完成离线验收 | 候选深度已在 2,000 条 Tune 冻结，完整 Top10 与 Blind v3 已验收；动态权重仍未成为默认方案 |

## 五、说明文档

| 文档 | 文档状态 | 对应工作状态 | 说明 |
| --- | --- | --- | --- |
| [质检模块全解](reports/LinkRag-Eval-质检模块全解.md) | 完成 | 持续维护 | 面向开发者解释系统；历史上位于报告目录，因此保留原路径 |

## 六、人工汇总报告

以下报告均已完成并保留原路径。这里的“完成”表示该轮报告已经形成，不代表报告提出的后续优化全部完成。

| 报告 | 状态 | 作用 |
| --- | --- | --- |
| [统一报告索引](reports/REPORT_INDEX.md) | 持续维护 | 收录全部保留的 HTML、Markdown、JSON、CSV 阶段产物 |
| [800 vs 2000 语料规模对照](reports/corpus_scale_800_vs_2000.md) | 完成 | 说明背景语料规模对召回区分度的影响 |
| [Doubao 稀疏检索 500 题评测](reports/doubao_retrieval_eval_500.md) | 完成 | 记录稀疏模型扩样本评测结果 |
| [RRF 与 weighted score 对比](reports/fusion_strategy_comparison_2026_07_02.md) | 完成 | 对比两种融合策略；另有同名 HTML 版本 |
| [Golden V2 Realistic 991004](reports/golden_v2_realistic_991004_run_2026_07_10.md) | 完成 | 记录候选、标注、仲裁和 chunk 粒度构建结果 |
| [池化重标可靠性](reports/label_reliability_pooled_relabel.md) | 完成 | 量化单正例标注漏标风险 |
| [活栈 Smoke](reports/live_smoke_2026_07_02.md) | 完成 | 证明 eval MySQL/Qdrant 隔离链路和两路 clean 基线可用 |
| [多路召回对比](reports/multi_route_recall_comparison_2026_07_05.md) | 完成 | 比较 Dense、Dense+BM25 和三路召回；另有同名 HTML 版本 |
| [Recall 参数搜索](reports/recall_parameter_tuning_2026_07_02.md) | 完成 | 记录阈值和 TopK 搜索；另有同名 HTML 版本 |
| [两路与三路召回](reports/recall_routes_2way_vs_3way.md) | 完成 | 对比增加第三路后的指标变化 |
| [BGE-M3 与 Doubao 稀疏模型](reports/sparse_model_comparison_bge_vs_doubao.md) | 完成 | 对比稀疏编码模型表现 |
| [weighted score 参数搜索](reports/weighted_score_parameter_tuning_2026_07_02.md) | 完成 | 记录融合权重搜索；另有同名 HTML 版本 |

运行目录下的阶段产物不在本文逐项重复，完整清单、格式和用途见
[REPORT_INDEX.md](reports/REPORT_INDEX.md)。历史报告只追加，不覆盖、不删除。

## 七、历史归档

归档目录中的文档均为“文档已归档、原方案不再实施”。当前替代关系见
[归档说明](archive/README.md)。

| 文档 | 状态 | 历史主题 |
| --- | --- | --- |
| [历史设计总览](archive/design-v1/overview.md) | 已归档 | monorepo 时期文档入口 |
| [框架设计](archive/design-v1/framework_design.md) | 已归档 | 早期模块拆分和实现顺序 |
| [技术设计](archive/design-v1/technical_design.md) | 已归档 | 早期五层指标口径 |
| [存储合并稿](archive/design-v1/eval_storage_design.md) | 已归档 | 旧存储、灌库和数据模型 |
| [存储隔离方案](archive/design-v1/eval_storage_isolation_design.md) | 已归档 | 已废弃的方案甲 |
| [冻结语料与租户](archive/design-v1/frozen_corpus_tenant.md) | 已归档 | 旧租户和号段方案 |
| [MinIO 产物桶](archive/design-v1/minio_eval_bucket_design.md) | 已归档 | 旧对象存储方案 |
| [Phase 0 地基](archive/design-v1/phase0_design.md) | 已归档 | 早期协议和数据模型 |
| [Phase 0.5 清洗质检](archive/design-v1/phase0_5_cleaning_quality_design.md) | 已归档 | 早期清洗质量设计 |
| [Phase 1 检索层](archive/design-v1/phase1_design.md) | 已归档 | 早期检索评测闭环 |
| [Phase 1.5 黄金集合成](archive/design-v1/phase1_5_golden_gen_design.md) | 已归档 | 已被 Golden V2 替代的 doc 粒度方案 |
| [Track B LLM 合成语料](archive/design-v1/phase1_5_trackB_llm_corpus_design.md) | 已归档 | 旧合成语料埋点方案 |
| [Phase 2 重排层](archive/design-v1/phase2_rerank_design.md) | 已归档 | 早期 Rerank 设计 |
| [Phase 3 生成与正确性](archive/design-v1/phase3_generation_design.md) | 已归档 | 早期生成评测设计 |
| [趋势与回归看板](archive/design-v1/trend_dashboard_design.md) | 已归档 | 旧趋势台账方案 |

## 八、未完成工作汇总

当前真正未完成的工作统一汇总如下：

1. **解耦架构验收**：先补 `Snapshot`/DB 台账中的 BM25 backend、sidecar 和 computer fingerprint，再在同一冻结集完成 SQLite FTS5 关闭/启用 A/B clean run，输出 BM25 Recall/MRR/延迟 delta，关闭 Step 5-6。
2. **CI**：本地 workflow 尚未跟踪，也没有安装固定 SHA 的 toLink-Rag；必须阻止契约测试因缺包静默跳过，再形成远端 pytest、contract、import-lint、Alembic heads 门禁证据。
3. **Golden V2 后续扩展**：补充真实编号、日期、版本号 eval-only 语料，并建立相应 chunk 粒度 Tune/Blind 子集。
4. **LambdaMART 短词门禁**：使用新的 Tune 数据定义低置信度回退 Hybrid 规则，不能用已揭盲 Blind v3 选参。
5. **业务别名/同义词词表**：建立版本化、业务域隔离且带歧义保护的 canonical→aliases 词表，在 BM25/Sparse 前保留原 Query 做受限扩展，并把词表版本写入运行快照。
6. **真实 Query 与来源元数据**：Blind v4 引入脱敏日志、客服/业务问题和开源 Query，保留来源、生成器、canonical query 和场景字段并分来源报告。
7. **多正例 pooled qrels**：Top50 多路候选独立复核，允许多个 `expected_chunk_ids`，统计新增正例率、未解决率和随机负例误判率。
8. **多 Chunk / 跨段落语料**：增加真实长文档结构、同文档 Chunk 和 `cross_chunk` Query，修复当前一文档一Chunk导致的评测缺口。
9. **LambdaMART 生产化**：固定 `candidate_difference_v2`，实现模型产物、在线特征、版本校验、延迟、降级、Shadow、监控和回滚，不再引入 Rerank。
10. **最终验收**：所有参数冻结后生成证据和 Query 均隔离的 Blind v4，建议至少 500 条并报告置信区间/配对显著性，只运行一次形成最终报告。

本轮黄金标注修正、Query 候选分流、2,000 Tune 全量缓存、Tune OOF 重训、未曝光 Blind v3
和最终验收报告六步已经完成。

第三判官、趋势看板、ANN/HNSW sidecar 和 10 万背景语料扩容属于非阻塞增强项。
