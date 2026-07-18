# 文档导航

## 权威架构(docs/architecture/)

随项目演进维护,是当前设计的唯一权威。

- [decoupling-plan.md](architecture/decoupling-plan.md) — 解耦独立化总方案(已批准基线):依赖边界、组件、迁移路径、风险。

## 历史设计(docs/design/)

迁移自源仓库 `.specs/rag-quality-eval/`,记录 monorepo 时期的设计。**存储/灌库部分已被 decoupling-plan 取代**,引用时以 architecture/ 为准。

- 总览:[overview.md](design/overview.md)、[framework_design.md](design/framework_design.md)、[technical_design.md](design/technical_design.md)
- 存储/隔离:[eval_storage_design.md](design/eval_storage_design.md)、[eval_storage_isolation_design.md](design/eval_storage_isolation_design.md)、[eval_data_schema.md](design/eval_data_schema.md)、[eval_ingest_decoupled_design.md](design/eval_ingest_decoupled_design.md)、[minio_eval_bucket_design.md](design/minio_eval_bucket_design.md)、[frozen_corpus_tenant.md](design/frozen_corpus_tenant.md)
- 阶段设计:[phase0_design.md](design/phase0_design.md)、[phase0_5_cleaning_quality_design.md](design/phase0_5_cleaning_quality_design.md)、[phase1_design.md](design/phase1_design.md)、[phase1_5_golden_gen_design.md](design/phase1_5_golden_gen_design.md)、[golden_v2_realistic_eval_design.md](design/golden_v2_realistic_eval_design.md)、[phase1_5_trackB_llm_corpus_design.md](design/phase1_5_trackB_llm_corpus_design.md)、[phase2_rerank_design.md](design/phase2_rerank_design.md)、[phase3_generation_design.md](design/phase3_generation_design.md)
- 召回融合:[ltr-fusion-experiment-v1.md](design/ltr-fusion-experiment-v1.md) — Rerank、Query 重写与 LambdaMART 的真实测试对比、选型依据、训练验证和生产落地建议
- 趋势看板:[trend_dashboard_design.md](design/trend_dashboard_design.md)

## 历史实证报告(docs/reports/)

- [REPORT_INDEX.md](reports/REPORT_INDEX.md) — 当前与历史所有阶段报告的统一索引及用途说明

- [corpus_scale_800_vs_2000.md](reports/corpus_scale_800_vs_2000.md) — 语料规模对召回区分度的影响
- [recall_routes_2way_vs_3way.md](reports/recall_routes_2way_vs_3way.md) — 两路 vs 三路召回
- [sparse_model_comparison_bge_vs_doubao.md](reports/sparse_model_comparison_bge_vs_doubao.md) — 稀疏模型对比
- [doubao_retrieval_eval_500.md](reports/doubao_retrieval_eval_500.md) — doubao 召回评测
- [label_reliability_pooled_relabel.md](reports/label_reliability_pooled_relabel.md) — 池化重标的标注可靠性
