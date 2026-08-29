# LinkRag-Eval 测试报告索引

> 本索引覆盖 `runs/golden_v2/` 与 `docs/reports/` 下的阶段报告。
> 历史报告必须保留原路径；新一轮测试使用新的 run/batch 目录或带时间戳文件名，禁止覆盖旧报告。

当前共收录 **30** 个报告及机器可读配套产物：HTML 4，MD 25，JSON 1，CSV 0。

更新索引：`python3 scripts/build_report_index.py`
校验索引：`python3 scripts/build_report_index.py --check`

## 阶段导航

- [00 历史实证与人工汇总](#00-历史实证与人工汇总)：30 个产物

## 00 历史实证与人工汇总

| 报告 | 格式 | 作用 |
| --- | --- | --- |
| [docs/reports/LinkRag-Eval-质检模块全解.md](<LinkRag-Eval-质检模块全解.md>) | `md` | 阶段说明或人读版结果摘要，保留口径、结论和决策依据。 |
| [docs/reports/blind_v4_final_acceptance_2026_07_24.md](<blind_v4_final_acceptance_2026_07_24.md>) | `md` | 阶段说明或人读版结果摘要，保留口径、结论和决策依据。 |
| [docs/reports/blind_v5_production_contract_acceptance_2026_07_28.md](<blind_v5_production_contract_acceptance_2026_07_28.md>) | `md` | 阶段说明或人读版结果摘要，保留口径、结论和决策依据。 |
| [docs/reports/corpus_scale_800_vs_2000.md](<corpus_scale_800_vs_2000.md>) | `md` | 阶段说明或人读版结果摘要，保留口径、结论和决策依据。 |
| [docs/reports/doubao_retrieval_eval_500.md](<doubao_retrieval_eval_500.md>) | `md` | 阶段说明或人读版结果摘要，保留口径、结论和决策依据。 |
| [docs/reports/fusion_strategy_comparison_2026_07_02.html](<fusion_strategy_comparison_2026_07_02.html>) | `html` | 人读版测试报告，展示聚合指标、逐题诊断和阶段结论。 |
| [docs/reports/fusion_strategy_comparison_2026_07_02.md](<fusion_strategy_comparison_2026_07_02.md>) | `md` | 阶段说明或人读版结果摘要，保留口径、结论和决策依据。 |
| [docs/reports/golden_v2_realistic_991004_run_2026_07_10.md](<golden_v2_realistic_991004_run_2026_07_10.md>) | `md` | 阶段说明或人读版结果摘要，保留口径、结论和决策依据。 |
| [docs/reports/internal_v6_dev_route_evidence_v5_verification_2026_08_29.md](<internal_v6_dev_route_evidence_v5_verification_2026_08_29.md>) | `md` | 阶段说明或人读版结果摘要，保留口径、结论和决策依据。 |
| [docs/reports/label_reliability_pooled_relabel.md](<label_reliability_pooled_relabel.md>) | `md` | 阶段说明或人读版结果摘要，保留口径、结论和决策依据。 |
| [docs/reports/live_smoke_2026_07_02.md](<live_smoke_2026_07_02.md>) | `md` | 阶段说明或人读版结果摘要，保留口径、结论和决策依据。 |
| [docs/reports/multi_route_recall_comparison_2026_07_05.html](<multi_route_recall_comparison_2026_07_05.html>) | `html` | 人读版测试报告，展示聚合指标、逐题诊断和阶段结论。 |
| [docs/reports/multi_route_recall_comparison_2026_07_05.md](<multi_route_recall_comparison_2026_07_05.md>) | `md` | 阶段说明或人读版结果摘要，保留口径、结论和决策依据。 |
| [docs/reports/recall_parameter_tuning_2026_07_02.html](<recall_parameter_tuning_2026_07_02.html>) | `html` | 人读版测试报告，展示聚合指标、逐题诊断和阶段结论。 |
| [docs/reports/recall_parameter_tuning_2026_07_02.md](<recall_parameter_tuning_2026_07_02.md>) | `md` | 阶段说明或人读版结果摘要，保留口径、结论和决策依据。 |
| [docs/reports/recall_routes_2way_vs_3way.md](<recall_routes_2way_vs_3way.md>) | `md` | 阶段说明或人读版结果摘要，保留口径、结论和决策依据。 |
| [docs/reports/robust_fusion_candidate_snapshot_field_gap_audit_2026_08_28.md](<robust_fusion_candidate_snapshot_field_gap_audit_2026_08_28.md>) | `md` | 阶段说明或人读版结果摘要，保留口径、结论和决策依据。 |
| [docs/reports/robust_fusion_gate_a_data_coverage_audit_2026_08_28.md](<robust_fusion_gate_a_data_coverage_audit_2026_08_28.md>) | `md` | 记录正确 Chunk 在各召回通道和候选深度中的覆盖情况。 |
| [docs/reports/robust_fusion_human_annotation_verification_2026_08_29.json](<robust_fusion_human_annotation_verification_2026_08_29.json>) | `json` | 机器可读阶段产物，保留测试参数、统计结果和复现依据。 |
| [docs/reports/robust_fusion_r2_human_review_pre_adjudication_2026_08_29.md](<robust_fusion_r2_human_review_pre_adjudication_2026_08_29.md>) | `md` | 记录四份提交的先锁后验、机械预审和 relation 7 / similarity 96 待仲裁清单。 |
| [docs/reports/robust_fusion_r2_preregistration_and_eligibility_2026_08_29.md](<robust_fusion_r2_preregistration_and_eligibility_2026_08_29.md>) | `md` | 阶段说明或人读版结果摘要，保留口径、结论和决策依据。 |
| [docs/reports/robust_fusion_r2_similarity_failure_diagnostic_2026_08_29.md](<robust_fusion_r2_similarity_failure_diagnostic_2026_08_29.md>) | `md` | 阶段说明或人读版结果摘要，保留口径、结论和决策依据。 |
| [docs/reports/robust_fusion_r2_source_v7_automatic_handoff_2026_08_29.md](<robust_fusion_r2_source_v7_automatic_handoff_2026_08_29.md>) | `md` | 阶段说明或人读版结果摘要，保留口径、结论和决策依据。 |
| [docs/reports/robust_fusion_similarity_dev_calibration_2026_08_29.md](<robust_fusion_similarity_dev_calibration_2026_08_29.md>) | `md` | 阶段说明或人读版结果摘要，保留口径、结论和决策依据。 |
| [docs/reports/robust_fusion_similarity_human_review_2026_08_29.md](<robust_fusion_similarity_human_review_2026_08_29.md>) | `md` | 阶段说明或人读版结果摘要，保留口径、结论和决策依据。 |
| [docs/reports/robust_fusion_similarity_support_supplement_2026_08_29.md](<robust_fusion_similarity_support_supplement_2026_08_29.md>) | `md` | 阶段说明或人读版结果摘要，保留口径、结论和决策依据。 |
| [docs/reports/sparse_model_comparison_bge_vs_doubao.md](<sparse_model_comparison_bge_vs_doubao.md>) | `md` | 阶段说明或人读版结果摘要，保留口径、结论和决策依据。 |
| [docs/reports/sqlite_share_restore_and_asset_reconciliation_2026_08_28.md](<sqlite_share_restore_and_asset_reconciliation_2026_08_28.md>) | `md` | 阶段说明或人读版结果摘要，保留口径、结论和决策依据。 |
| [docs/reports/weighted_score_parameter_tuning_2026_07_02.html](<weighted_score_parameter_tuning_2026_07_02.html>) | `html` | 记录召回阈值、TopK、权重或融合参数搜索结果。 |
| [docs/reports/weighted_score_parameter_tuning_2026_07_02.md](<weighted_score_parameter_tuning_2026_07_02.md>) | `md` | 记录召回阈值、TopK、权重或融合参数搜索结果。 |
