# 脚本与命令入口

先按任务选入口。实际数据路径见[数据入口](../data/README.md)，模型路径见[中文／英文基线](../models/README.md)，已有结果见[实验目录](../runs/post_recall/README.md)。本页说明接口，不替代[当前状态](../docs/CURRENT_STATUS.md)中的工作范围。

命令从仓库根目录执行：Python 脚本用 `.venv/bin/python scripts/<文件名> --help`，统一 CLI 用 `.venv/bin/linkrag-eval --help`。仅下列主要入口验收过帮助命令；历史 Shell 脚本不能按此方式试跑。

## 1. 优先查这些入口

| 任务 | 入口 | 必要输入 → 输出 | 实际动作 |
| --- | --- | --- | --- |
| 固定候选 LLM 判断器试点 | [llm_judge_pilot.py](llm_judge_pilot.py) | 保存查询／候选／英文分数 → 基线与融合分数、条目、判断日志、L1/L2 评价或 L3 离线模型目录 | `judge` 支持本机 `codex exec`、Ollama 和 OpenAI 兼容服务；`agreement` 比较已有判断目录；`stage1-scores` 提取固定融合 `baseline_score`，L2/L3 按前 K（默认 20）选择；子命令拒绝覆盖已有输出。结果、命令与限制见[运行目录](../runs/post_recall/llm-judge-pilot-20260910/README.md)与[正式报告](../docs/reports/llm_judge_pilot_2026_09_10.md) |
| OOD 探针条目转换 | `llm_judge_pilot.py probe-items --fixture <fixture.json> --output <新items.jsonl>` | 默认读取 `runs/post_recall/ood-probe-20260910/fixture.json` → L1 格式条目；英文全池、中文双向均展开，保留 `expected/probe_set/kind`，模型元数据暂为 null | 沿用 `judge` 与缓存，标签不进入提示词；拒绝覆盖输出 |
| OOD 探针评分评价 | `llm_judge_pilot.py probe-evaluate --items <items.jsonl> --scores <judge-dir>/scores.jsonl --output <新结果.json>` | 逐查询目标竞争排名及含平局的最差排名、strict/reverse/tie、中文双向全对，按 probe_set 与 kind 汇总 | 严格核对条目与评分范围；不可用查询排名为 null，计入准确率分母但不计正确；拒绝覆盖输出 |
| 检查基线模型包 | `linkrag-eval ltr validate-bundle --model-dir <目录>` | 中文／英文基线 → 契约检查结果 | 读取模型，校验及本地预测 |
| 诊断中文／英文基线 | [nevir_english_diagnostics.py](nevir_english_diagnostics.py) | 开发快照＋两模型＋英文训练产物＋旧 A/B 诊断 → 新诊断目录 | 写本地统计、追踪与盲审材料；不训练、不召回 |
| 重现两种特征版本的训练比较 | [nevir_compare_feature_versions.py](nevir_compare_feature_versions.py) | [比较配置](../runs/post_recall/nevir-english-features-20260907/comparison-config.json)＋已有 Train／开发输入 → 新比较目录 | 实际训练 legacy／英文各一组；历史对照复现 |
| 检查／更新报告索引 | [build_report_index.py](build_report_index.py) | 现有报告 → `docs/reports/REPORT_INDEX.md` | `--check` 只校验；无此参数会更新索引 |
| 查通用评测命令 | [linkrag-eval CLI](../src/linkrag_eval/cli.py) | 按子命令指定 | 入库、生成、检索和评价的动作不同，先查子命令帮助 |

比较脚本原名 `nevir_feature_compare.py`，现已改名；参数与行为不变，历史运行记录仍可能记旧名。它不是“只比较已有分数”的工具，也不是每次诊断的前置步骤。

`llm_judge_pilot.py judge --runner {codex,ollama,openai}` 默认使用 codex；本地服务必须传 `--endpoint`（服务根 URL，不含 API 路径）和 `--model`。`--num-ctx` 默认 8192，分别设置 Ollama 上下文大小和 OpenAI 兼容服务的生成 token 上限；后者的服务端上下文容量需自行配置。OpenAI 兼容服务可用 `--api-key-env EVAL_JUDGE_API_KEY` 指定已有密钥环境变量名，密钥不写日志。`--batch-size` 未指定时 codex 为 40、本地为 1；`--workers` 默认 4，可按 vLLM 容量设为 8–16。本地 effort 固定为 `none`，与 codex 缓存区分；原提示词、`--cache`、`--seed`、`--smoke` 及分数目录结构沿用。

`llm_judge_pilot.py agreement --a <judge-dir> --b <judge-dir> --output <新文件.json>` 读取两边 `scores.jsonl`，按查询 ID＋chunk ID 对齐。报告包含共享／双方可用条目数、精确及相差不超过 1 分的一致率、平均秩 Spearman、Kendall tau-b、5×5 混淆矩阵（行 A、列 B，均为 0–4 分）及成对方向一致率。成对比较使用相同查询和 pair ID 内共享候选的所有无序组合，平局单独作为一种关系；不可用分数不进入一致率分母，无有效样本或相关性无定义时写 `null`。拒绝覆盖已有输出文件。

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

## N08 离线原型与人类收件

当前设计／边界见[研究计划 §2.7](../docs/plans/post-recall-research-plan.md#27-同一自动事实上的条件聚合对照2026-09-08)，结果与继续决定见[正式报告](../docs/reports/nevir_subject_binding_pilot_2026_09_08.md)。这些入口显式选择文件和新输出目录，不自动重跑或遍历其他划分。

| 入口 | 职责与主要参数 |
| --- | --- |
| [nevir_review_handoff.py](nevir_review_handoff.py) | `--experiment-dir --source-review --out`；验证并复制原 N05 公共包，拒绝已存在输出，不重新抽样 |
| [结构化审阅包升级模块](../src/linkrag_eval/retrieval/learning_to_rank/review_structured.py) | `.venv/bin/python -m linkrag_eval.retrieval.learning_to_rank.review_structured --source-manifest ... --out ...`；只升级核对后的公共表单和教程，新目录输出，原 cases 字节与映射不变 |
| [nevir_review_receive.py](nevir_review_receive.py) | `--manifest ... receive --reviewer --submission --out` 保存原始收件；`disagreements --reviewer-1-intake --reviewer-2-intake --out` 只生成待人类裁定材料 |
| [subject_binding_parse.py](subject_binding_parse.py) | 独立 parser 环境运行，`--texts --cache --out`；只收原文和文本角色，无 ID／标签，固定版本且完整解析 |
| [subject_binding_controls.py](subject_binding_controls.py) | `--scenes --cache --spec --out`；复算原 12 探针，人工预期未核验，不加入训练 |
| [subject_binding_development.py](subject_binding_development.py) | `prepare` 精确重放 B／英文并导出开发文本；`analyze` 按显式 `rules_version` 计算覆盖及同查询数值／聚合准入。均需 `--config --out`，后者还需 `--cache` |
| [subject_binding_training.py](subject_binding_training.py) | 固定对照入口；`prepare-texts` 导出原 Train 文本，`train` 在任何拟合前重新检查开发全池与 Train 合法监督行信号。`experiment_purpose=basic_matching` 只执行 E0/EM/E1，默认 `binding` 额外要求聚合差异并沿用五臂；旧版或不同目的准入摘要拒绝。均需 `--config --development-summary --out`，训练还需 `--cache` |

2026-09-09 的工程修复通过配置 `rules_version=subject_binding_nominal_quotes_v2` 显式启用；省略仍为 v1。使用本轮新配置与执行 spec，不能直接修改历史 spec 的源码摘要来假装重放旧实现。原始 token 缓存按已核实的冻结 parser 契约共享，只复用 token，新的事实／分数带 v2 身份并写新目录，旧分数不能充当 v2 缓存。离线模型的规则与 41 列契约必须同时相符，两个在线基线未改。一次性同输入比较入口是 [compare.py](../runs/post_recall/subject-binding-pilot-20260908/repair-20260909/compare.py)，使用 `--out-name 新目录名`，预算最多为固定 E3 控制／修复两臂，实际因准入未通过而零拟合；不执行原五臂或打乱扩展。产物与验收见[报告 §3.4](../docs/reports/nevir_subject_binding_pilot_2026_09_08.md#34-名词性引号与训练准入工程修复2026-09-09)。

最新工程修复显式选择 `rules_version=subject_binding_evidence_records_v3`，查询／正文类型对称并保留未知主体事件，参数与证据记录由 `subject_binding_records.py` 处理，`subject_binding_matching.py` 提供可替换三态接口及严格匹配对照。v3 模型契约包含规则、记录 schema、有序列及 matcher；原 token 缓存只供重新提取，分数／矩阵不能跨版本复用。当前可复现配置为 [config-v3-final.json](../runs/post_recall/subject-binding-pilot-20260908/representation-v3-20260909/config-v3-final.json)，使用新输出目录；拟合时源码及证据字段最终校正分别留档。基础三臂已完成，绑定门槛未过，命令、产物和技术验收见[报告 §3.5](../docs/reports/nevir_subject_binding_pilot_2026_09_08.md#35-版本覆盖类型对称与事件保留的-v3-修复2026-09-09)。

配置与输出在[运行目录](../runs/post_recall/subject-binding-pilot-20260908/)。parser Python 位于其 `environment/parser/bin/python`，使用 `PYTHONPATH=src`；其余脚本使用原 `.venv/bin/python`。新 41 列模型仅用于本地离线研究，不替换在线两模型。人工输入未到时不调用收件，也不生成替代人类意见；人类锁定前不关联模型。

当前人类收件使用 `runs/post_recall/subject-binding-pilot-20260908/handoff-structured-v2/handoff-manifest.json`，分发文件保留在同目录的 reviewer 子目录；原最终两份 ZIP 当前缺失（报告 §2.4），现有 JSON 收件不依赖 ZIP 重建。schema 2 新增段落 `reason_types` 与 `pair_reason_code`，后端按条件检查证据／补充；原因类型差异单独交人类查看，不推断偏好或裁定。旧草稿可在新版页导入补填，旧 schema 1 不能直接作为新版完整提交；只有对应旧 manifest 保留旧收件口径。每次收件用新的版本目录，原始文件只读保留。具体打开／填写／导出及待审状态见[同一份报告 §2.3](../docs/reports/nevir_subject_binding_pilot_2026_09_08.md#23-结构化原因选择当前分发与收件契约)。

完整性校验现使用 `query_ambiguity_abstention_v1`：查询歧义为 `yes/uncertain`、本段无法裁定且本段说明非空时，允许本段类别为空；其余字段和摘录校验不变。答案 schema、词表与存储键未升级，旧 schema 2 JSON 直接接收，无需重新导出；后端重算完整性，不采用旧页面 `completion` 或提交自报策略。原分发包和旧收件不覆盖，新的校验记录另存。详见[报告 §2.4](../docs/reports/nevir_subject_binding_pilot_2026_09_08.md#24-查询歧义的完整性例外与原提交兼容验收2026-09-09)。

指定补写版已通过收件；最初的人类讨论材料为[裁定清单](../runs/post_recall/subject-binding-pilot-20260908/human/20260909-intake-v2/adjudication/review-checklist.md)。该原清单保留原题号、左右对应和当时空白裁定栏；已完成的最终接收结果使用下方汇总，不再要求重新填写原清单。机器标记可重叠，既不等同语义错误，也不代表选项一致即金标。具体范围见[报告 §2.5](../docs/reports/nevir_subject_binding_pilot_2026_09_08.md#25-指定补写版本接收与人类裁定清单2026-09-09)。

分批通过对话提交的讨论集中维护在[最终结果](../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/current-results.md)。`batches/` 保留五批原话与字段来源，最新固定输入为 `history/results-v5-frozen.json`；第五批明确第 60 题 X 不足/Y 不满足/偏好 X，其余 75 题未改，原 v4 保留。一次性 [evaluate_saved.py](../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/evaluate_saved.py) 只读取人工固定输入、原映射和已有开发分数；默认政策重放 v4，显式 `--policy .../human/adjudication/analysis-policy-v2.json` 选择 v5，`--out` 必须指向新目录。最新产物见 [analysis-v2](../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/analysis-v2/)，口径与实际执行见[报告 §2.8](../docs/reports/nevir_subject_binding_pilot_2026_09_08.md#28-第-60-题收尾与-v5-更新2026-09-09)。
