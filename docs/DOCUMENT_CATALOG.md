# 文档目录与完成状态

> 更新时间：2026-07-28
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
| [解耦独立化方案](architecture/decoupling-plan.md) | 完成 | 完成 | Step 0-6 已完成；SQLite backend/fingerprint A/B clean run 与 BM25 delta 已于 2026-07-24 固化 |

## 三、当前实施方案

| 文档 | 文档状态 | 对应工作状态 | 未完成内容 |
| --- | --- | --- | --- |
| [Golden V2 真实召回评测](plans/golden-v2-realistic-evaluation.md) | 完成 | 完成当前 20k 验收 | 问题标注修正、exact identifier 门禁、2,000 Tune 重训和未曝光 Blind v3 已完成；编号类语料补充和 10 万扩容属于后续阶段 |

## 四、实验与候选方案

| 文档 | 文档状态 | 实验状态 | 结论或剩余工作 |
| --- | --- | --- | --- |
| [LambdaMART 三路融合](experiments/ltr-fusion-v1.md) | 完成 | 完成 | 活动 `candidate_difference_v3` 已移除离线场景和 Alias 依赖，生产模型包与 Blind v5 已验收；生产默认切换仍须 Shadow |
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
| [Blind v4 最终一次性验收](reports/blind_v4_final_acceptance_2026_07_24.md) | 完成 | 记录 750 条 Blind v4 的冻结门禁、数据来源、pooled 复核、在线运行指标与统计结论 |
| [Blind v5 无 Alias 生产契约验收](reports/blind_v5_production_contract_acceptance_2026_07_28.md) | 完成 | 记录生产可用 v3 特征、无 Alias 模型包、750 条唯一 Blind 运行及 Shadow 结论 |
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

当前真正未完成的阻塞工作只有一项：

1. **CI 远端证据**：workflow 已固定安装最新 LinkRag SHA `861f24810c3482ec0d86768a24f952b1e08ae675`，并阻止契约测试因缺包静默跳过；远端 pytest、真实 contract、import-lint、Alembic heads 门禁均由 PR CI 验证。

本轮 Query provenance、Top50 pooled 独立复核、多正例 qrels、多 Chunk/编号类语料、Alias、短词回退、
在线 LambdaMART 和 750 条 Blind v4 一次性验收均已完成。Blind v4 已封存，不得复用选参或重跑。

2026-07-25 已把停用的 `tolink_rag_eval_db` 完整迁到本地 `runs/linkrag_eval.sqlite3`，正常运行不再依赖远端 MySQL。

第三判官、趋势看板、ANN/HNSW sidecar 和 10 万背景语料扩容属于非阻塞增强项。
