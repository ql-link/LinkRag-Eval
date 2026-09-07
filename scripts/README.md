# 脚本与命令入口

先按任务选入口。实际数据路径见[数据入口](../data/README.md)，模型路径见[中文／英文基线](../models/README.md)，已有结果见[实验目录](../runs/post_recall/README.md)。本页说明接口，不替代[当前状态](../docs/CURRENT_STATUS.md)中的工作范围。

命令从仓库根目录执行：Python 脚本用 `.venv/bin/python scripts/<文件名> --help`，统一 CLI 用 `.venv/bin/linkrag-eval --help`。仅下列主要入口验收过帮助命令；历史 Shell 脚本不能按此方式试跑。

## 1. 优先查这些入口

| 任务 | 入口 | 必要输入 → 输出 | 实际动作 |
| --- | --- | --- | --- |
| 检查基线模型包 | `linkrag-eval ltr validate-bundle --model-dir <目录>` | 中文／英文基线 → 契约检查结果 | 读取模型，校验及本地预测 |
| 诊断中文／英文基线 | [nevir_english_diagnostics.py](nevir_english_diagnostics.py) | 开发快照＋两模型＋英文训练产物＋旧 A/B 诊断 → 新诊断目录 | 写本地统计、追踪与盲审材料；不训练、不召回 |
| 重现两种特征版本的训练比较 | [nevir_compare_feature_versions.py](nevir_compare_feature_versions.py) | [比较配置](../runs/post_recall/nevir-english-features-20260907/comparison-config.json)＋已有 Train／开发输入 → 新比较目录 | 实际训练 legacy／英文各一组；历史对照复现 |
| 检查／更新报告索引 | [build_report_index.py](build_report_index.py) | 现有报告 → `docs/reports/REPORT_INDEX.md` | `--check` 只校验；无此参数会更新索引 |
| 查通用评测命令 | [linkrag-eval CLI](../src/linkrag_eval/cli.py) | 按子命令指定 | 入库、生成、检索和评价的动作不同，先查子命令帮助 |

比较脚本原名 `nevir_feature_compare.py`，现已改名；参数与行为不变，历史运行记录仍可能记旧名。它不是“只比较已有分数”的工具，也不是每次诊断的前置步骤。

## 2. 当前诊断的依赖

[nevir_english_diagnostics.py](nevir_english_diagnostics.py) 的六个必填参数对应：

| 参数 | 取什么 |
| --- | --- |
| `--experiment-dir` | [保存快照的 experiment 目录](../runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment/)；读取其中开发 queries／supervision／inputs 和段落映射 |
| `--model-a` | `models/chinese-baseline/` |
| `--model-english` | `models/english-baseline/` |
| `--saved-english-predictions` | [英文 dev-predictions.jsonl](../runs/post_recall/nevir-english-features-20260907/comparison/english/dev-predictions.jsonl)；同目录还需 `selection.json` 和英文开发 NPZ |
| `--previous-diagnostic` | [旧 A/B 诊断目录](../runs/post_recall/nevir-offline-diagnostic-20260907/)，含旧分数、矩阵、追踪和公共盲审材料 |
| `--out` | 本次全新的诊断输出目录 |

这些是**已有产物依赖**，不要求重新采集或训练。该入口复用 `nevir_evaluation` 的输入处理、`diagnostic_features`／`diagnostic_trees` 的追踪和 `nevir_diagnostics` 的汇总／材料生成；不要把旧 A/B 诊断模块当作英文入口。详细产物说明见[英文诊断目录](../runs/post_recall/nevir-english-diagnostic-20260907/README.md)。

## 3. 数据准备与历史复现入口

| 任务 | 入口 | 输入 → 输出／动作 |
| --- | --- | --- |
| 准备原 NevIR 划分 | [nevir_ltr_prepare.py](nevir_ltr_prepare.py) | 官方 Train／Validation＋既定分组建议 → prepared 语料、查询与监督；本地写文件，涉及原确认划分 |
| 原 NevIR 入库／采集 | [nevir_ltr_collect.py](nevir_ltr_collect.py) | prepared 语料或查询 → 存储／三路候选；远端编码与检索，按 `--stage` 分阶段 |
| 部分标签训练 | [pairwise_training 模块](../src/linkrag_eval/retrieval/learning_to_rank/pairwise_training.py) | 显式 Train／开发 queries、supervision、inputs＋策略模型 → 新模型和开发分数；实际训练 |
| 历史 legacy A/B 评价 | [nevir_evaluation 模块](../src/linkrag_eval/retrieval/learning_to_rank/nevir_evaluation.py) | 指定角色的保存候选＋A/B → 新评价目录；角色须显式指定 |
| 历史 legacy A/B 诊断 | [nevir_diagnostics 模块](../src/linkrag_eval/retrieval/learning_to_rank/nevir_diagnostics.py) | 开发快照＋A/B＋旧 B 分数＋执行说明 → 新机械诊断；不自动适用于英文特征 |

模块调用方式：`.venv/bin/python -m linkrag_eval.retrieval.learning_to_rank.<模块名> --help`。准备／采集脚本有原实验默认路径和固定参数；读取已有材料不需要运行它们。模型特征默认仍为 legacy，英文版本须显式选择，绑定方式见[模型入口](../models/README.md)。

T2 接入目前暂停，已有 CLI 保留：

| CLI | 输入 → 输出／动作 |
| --- | --- |
| `linkrag-eval exploration ingest` | T2 collection＋独立存储参数 → SQLite／Qdrant 语料；远端编码、写存储 |
| `linkrag-eval exploration candidates` | 查询＋已有语料＋显式抽样规模／种子 → 保存三路候选；远端检索 |
| `linkrag-eval exploration coverage` | 保存候选＋原查询／四级 qrels → 标签覆盖报告；本地计算，不代表排序效果 |

必填参数见对应 `--help`；来源绑定、完整正文、长度策略和续跑口径见[接入说明](../docs/plans/post-recall-research-plan.md#33-探索输入准备与交接)及[实现](../src/linkrag_eval/runners/t2_workflow.py)。不能根据历史目录存在就认定其已完成入库。

## 4. 其余脚本按历史用途查找

下表按现有名称分组，`*` 是文件名匹配模式，覆盖其余脚本。它们未逐个做本轮运行验收；部分会调用 LLM、检索或写数据，尤其 `run_*.sh` 常固化原实验参数。所属实验见[历史 LTR 说明](../docs/experiments/ltr-fusion-v1.md)和[历史导航](../docs/archive/robust-fusion/README.md)，不串接为当前英文流程。

| 历史用途 | 文件名／模式 |
| --- | --- |
| 语料与 Blind 准备 | `audit_cmedqa_corpus_provenance.py`、`prepare_blind_v4_t2retrieval.py`、`prepare_structured_blind_v4_corpus.py`、`build_blind_v4_bundle.py`、`build_balanced_final_golden.py`、`build_ltr_blind_exposure_manifest.py`、`write_scale_scoped_golden.py` |
| Grounded 样本准备与验证 | `prepare_grounded_*.py`、`finalize_grounded_validation.py`、`inject_grounded_validation_targets.py` |
| 查询扩充与配对准备 | `prepare_ltr_*.py`、`prepare_balanced_query_extension.py`、`prepare_query_rewrite_benchmark.py`、`merge_ltr_query_rounds.py`、`split_pending_ltr_validation.py`、`finalize_ltr_query_expansion_2000.py` |
| 标签合并与复核 | `finalize_ltr_blind_v2.py`、`repair_ltr_golden_quality.py`、`review_pooled_top50.py` |
| 候选、路由与融合分析 | `analyze_*.py`、`optimize_*.py`、`tune_hybrid_weights.py`、`freeze_ltr_tune_config.py`、`export_ltr_candidate_contents.py` |
| 报告呈现 | `render_*.py` |
| 样本生成与验证编排 | `run_balanced_*.sh`、`run_grounded_*.sh` |
| 历史 LTR 查询扩充编排 | `run_ltr_*.sh` |
| 历史规模与 realistic 编排 | `run_scale_*.sh`、`run_overnight_*.sh`、`run_realistic_tune.sh`、`run_final_expanded_realistic.sh` |

`scripts/` 放实验编排，复用计算在 `src/linkrag_eval/`；入口测试在 `tests/unit/`。实验目录中的 `*.py` 可能是当时工具或源码副本，身份以该实验 README 为准。新增脚本按实际职责命名并补到本页，参数细节留给 CLI 帮助，不另建重复使用手册。
