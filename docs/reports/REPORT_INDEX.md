# 实验报告选读

先按要核对的问题选择。当前工作安排见[当前状态](../CURRENT_STATUS.md)，其他文档见[文档目录](../DOCUMENT_CATALOG.md)。
按次回顾实验（含长报告中的多轮对照、失败与中止）或登记新实验，见[实验台账](../experiments/EXPERIMENT_LOG.md)。
下表说明报告所属实验的口径；历史报告中的下一步不自动成为当前任务。

当前共收录 **29** 个产物，按 **25** 个题目展示：HTML 4，MD 25，JSON 0，CSV 0。
同名 MD／HTML 并列，优先读 MD，需要版式展示时选 HTML。
扫描范围仍为 `docs/reports/`、`runs/golden_v2/`；NevIR 运行产物从[实验目录](../../runs/post_recall/README.md)查找，不在这里重复逐文件列举。

更新：`python3 scripts/build_report_index.py`；校验：`python3 scripts/build_report_index.py --check`。
选读说明维护在生成脚本的 `REPORT_GUIDES`；新增报告自动收录，未填写说明的列入“待补选读说明”。

## 按问题选择

- [英文研究与 NevIR](#英文研究与-nevir)：8 个题目
- [历史排序与召回比较](#历史排序与召回比较)：9 个题目
- [历史数据与标签检查](#历史数据与标签检查)：5 个题目
- [历史工程交付与恢复](#历史工程交付与恢复)：3 个题目

## 英文研究与 NevIR

| 要核对的问题 | 阅读入口 | 口径与边界 |
| --- | --- | --- |
| 读文本的判断器能否补上 38 维缺失的条件信号？ | [MD](<llm_judge_pilot_2026_09_10.md>) | L1 单段判断、固定融合前 K 重排、判断列进 LTR；确认集只跑一次，开发与人审已曝光。 |
| 为什么选 Qwen14B，8B 与 BGE 的开发对照是什么？ | [MD](<open_judge_selection_2026_09_11.md>) | 原开发选模依据和 L1/L2 候选比较；后补结果不充当原确认前的选择证据。 |
| 同一自动事实上的主体聚合是否提供增量？ | [MD](<nevir_subject_binding_pilot_2026_09_08.md>) | 五组开发探索、人审敏感性及 v2/v3 工程修复与固定基础匹配对照；不属于独立确认。 |
| 开发快照中，基线评分与特征响应是什么？ | [MD](<nevir_offline_diagnostic_2026_09_07.md>) | §1–6 为历史 A/B，§7 为中文／英文基线；机械诊断，不是语义归因结论。 |
| 基础英文适配相比同条件 legacy 重训如何？ | [MD](<nevir_english_features_2026_09_07.md>) | 同监督、同配置的开发对照；不属于独立验证。 |
| 保持 38 维规则，只重训权重的结果如何？ | [MD](<nevir_same38_retraining_2026_09_07.md>) | 历史 A/B 确认；不是中文／英文基线对照，确认材料已使用。 |
| 英文链路和 NevIR 错排最初如何复现？ | [MD](<nevir_controlled_retrieval_2026_09_07.md>) | 普通英文能力检查＋20 对 NevIR；不能外推自然错误率。 |
| NevIR 的划分、来源重叠和标签边界是什么？ | [MD](<nevir_suitability_2026_09_07.md>) | 数据与固定样例审计，不是模型效果实验。 |

## 历史排序与召回比较

| 要核对的问题 | 阅读入口 | 口径与边界 |
| --- | --- | --- |
| 旧 Blind v4 如何比较 Hybrid 与 LambdaMART？ | [MD](<blind_v4_final_acceptance_2026_07_24.md>) | 旧数据和旧模型的工程门禁、效果及区间。 |
| 增加语料干扰规模会怎样影响召回？ | [MD](<corpus_scale_800_vs_2000.md>) | 同一 394 查询，800／2000 chunk 每域的历史比较。 |
| 豆包稀疏检索在旧基准上表现怎样？ | [MD](<doubao_retrieval_eval_500.md>) | 旧 500 题、四领域；单一稀疏模型的评测。 |
| RRF 与 weighted_score 怎样比较？ | [MD](<fusion_strategy_comparison_2026_07_02.md>) · [HTML](<fusion_strategy_comparison_2026_07_02.html>) | 同候选、同参数，无 rerank；旧四域基准。 |
| Dense、Dense＋BM25、三路召回怎样比较？ | [MD](<multi_route_recall_comparison_2026_07_05.md>) · [HTML](<multi_route_recall_comparison_2026_07_05.html>) | 旧 394 条 doc 粒度查询；保留当时召回与存储配置。 |
| 召回阈值与 TopK 当时如何调参？ | [MD](<recall_parameter_tuning_2026_07_02.md>) · [HTML](<recall_parameter_tuning_2026_07_02.html>) | 旧四域 394 查询、720 组网格；历史参数不直接沿用。 |
| BM25＋Sparse 增加 Dense 后有什么变化？ | [MD](<recall_routes_2way_vs_3way.md>) | 旧 500 题的两路／三路比较，区别于 394 题实验。 |
| BGE-M3 与豆包稀疏模型怎样比较？ | [MD](<sparse_model_comparison_bge_vs_doubao.md>) | 稀疏编码器对照；其他检索逻辑固定。 |
| 分数融合的权重与候选参数如何选过？ | [MD](<weighted_score_parameter_tuning_2026_07_02.md>) · [HTML](<weighted_score_parameter_tuning_2026_07_02.html>) | 旧 394 题、Dense／Sparse 权重搜索；不是当前三路新结论。 |

## 历史数据与标签检查

| 要核对的问题 | 阅读入口 | 口径与边界 |
| --- | --- | --- |
| 旧 Realistic 标注集如何形成？ | [MD](<golden_v2_realistic_991004_run_2026_07_10.md>) | 50 查询的池化标注与 Tune／Blind 划分记录。 |
| Internal v6-Dev 的三路证据核验了什么？ | [MD](<internal_v6_dev_route_evidence_v5_verification_2026_08_29.md>) | 仅供旧 Dev 测量与流程校准，不是 Gate A/B 验收。 |
| 旧公开数据的漏标如何检查？ | [MD](<label_reliability_pooled_relabel.md>) | 模型辅助池化重标；不能当成人工金标。 |
| 原候选快照缺哪些字段？ | [MD](<robust_fusion_candidate_snapshot_field_gap_audit_2026_08_28.md>) | 当时的契约与字段责任审计，不是当前源码清单。 |
| 旧 Gate A 材料与标签覆盖缺什么？ | [MD](<robust_fusion_gate_a_data_coverage_audit_2026_08_28.md>) | 历史数据审计，不是 Gate A 封存或运行结果。 |

## 历史工程交付与恢复

| 要核对的问题 | 阅读入口 | 口径与边界 |
| --- | --- | --- |
| 中文基线的原生产契约如何验收？ | [MD](<blind_v5_production_contract_acceptance_2026_07_28.md>) | 原 v3 的 38 维、无 Alias 与工程交付；不是英文模型验收。 |
| 旧活栈链路当时是否跑通？ | [MD](<live_smoke_2026_07_02.md>) | 2026-07 的旧 MySQL 环境；当前存储看工程架构。 |
| 旧 SQLite 与检索资产如何恢复和核对？ | [MD](<sqlite_share_restore_and_asset_reconciliation_2026_08_28.md>) | 当时的资产盘点；当前备份位置查恢复说明。 |
