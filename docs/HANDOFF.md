# LinkRag-Eval 下一对话交接

> 更新时间：2026-07-28
> 当前分支：`codex/ltr-eval-quality-suite`  
> 目标：让新的对话在不重做历史实验、不破坏隔离边界的前提下继续完成剩余工作。

## 1. 开始前必须知道

- 本仓库是独立评测项目，只写本地 `runs/linkrag_eval.sqlite3` 和 `eval*` Qdrant collection，绝不写生产库或旧 eval MySQL。
- 当前工作区有大量未提交改动和未跟踪文件。先运行 `git status --short`，不得 reset、checkout 或删除不属于当前任务的文件。
- `runs/` 被 Git 忽略，但所有阶段报告必须保留；新报告必须使用新目录或时间戳，禁止覆盖历史产物。
- 当前没有提交或推送。`.github/workflows/ci.yml` 仍是未跟踪文件。
- 项目级进度只以 [CURRENT_STATUS.md](CURRENT_STATUS.md) 为准；历史报告只能证明对应数据和参数下的结果。

## 2. 已冻结决策

1. 主指标使用 chunk 粒度；doc 粒度单独报告，不能混成 headline recall。
2. 当前规模固定在 20k 背景语料，10万扩容暂缓，不是阻塞项。
3. 默认候选来自 Dense、Sparse、SQLite FTS5 BM25 三路，融合与候选深度按冻结配置评测。
4. 活动 LambdaMART 固定为生产可用的 `candidate_difference_v3`：38 个特征只依赖 Query、三路候选和候选正文，不依赖 Rerank、Golden scenario 或 qrels。
5. Alias 已从活动候选缓存、模型训练和生产模型包移除；历史 v2 Alias 产物只作追溯。
6. 直接 Rerank、Cross Encoder 特征和 qwen3-vl-rerank 路线均已终止；不要重新启用或补跑 Top80。
7. Query重写实验没有稳定收益，不进入默认链路。
8. Blind v3 已揭盲，只能用于回归观察，不能再用于选参或最终验收。
9. Blind v4 与 Blind v5 均已唯一运行并封存，不得再用于选参或重跑。

## 3. 已完成的主要结果

- Golden V2 的 chunk qrels、候选池、双判官/QC、Tune/Blind拆分和20k链路已完成。
- LTR训练集为2,000条；Tune OOF：Hybrid 35.75%，LambdaMART 44.90%。
- 未曝光 Blind v3 共150条；Hybrid Recall@10 22.67%，LambdaMART 30.67%，提升8.00pp。
- 候选分流后 Tune候选覆盖98.55%，Blind v3候选覆盖92.67%。
- Rerank直接排序和作为LambdaMART特征均未通过Blind门禁，相关报告保留但路线关闭。
- 全量本地测试最近一次为 `328 passed, 3 skipped`，其中 16 个生产 contract 真实执行通过；import-lint 与 import boundary 通过。
- SQLite FTS5 最终验收已完成：同一 116 条冻结集上 OFF/ON 均 clean，chunk Recall@10 `31.32%→36.74%`（`+5.42pp`），MRR `16.58%→17.03%`（`+0.45pp`）。
- Blind v4 数据真实性与覆盖缺口已关闭：450 Tune、750 Blind、10,300 chunks；800 条开源 Query 与 400 条显式 synthetic Query 均保留 provenance；结构语料覆盖多 Chunk、跨段落、编号、日期和版本号。
- 300 条 Tune pooled Top50 的 15,000 个候选已完成独立复核与第三方仲裁，未解决 0；最终 1,782 个正 qrels，270/300 为多正例。
- 无 Alias `candidate_difference_v3`、短词低置信度回退和生产模型包均已冻结；序列化版本、完整超参、特征签名、超时/预算降级、Shadow、监控、测试向量和 weighted score 回滚已验证。
- Blind v4 唯一一次结果：Hit@10 `98.53%→98.93%`（+0.40pp），MRR `90.41%→98.02%`（+7.62pp）；95% CI 跨 0，因此只能判定工程门禁通过、效果方向为正，不能宣称 Hit@10 显著提升。
- 旧 `tolink_rag_eval_db` 已从 `100.86.10.52` 停机前备份完整迁到本地 `runs/linkrag_eval.sqlite3`；六表计数和内容摘要校验通过，后续禁止恢复远端 MySQL 运行依赖。
- Blind v5 唯一一次结果：Hit@10 `98.80%→99.07%`、MRR `92.16%→95.64%`，2 gained / 0 lost，p95 83.71ms；但 500 条真实搜索 MRR -0.70pp，因此只批准生产 Shadow，不批准直接全量切换。

## 4. 审查发现的关键缺口

### 已关闭：可复现快照与SQLite BM25验收

- `Snapshot`、文件报告和 DB 台账已记录 `bm25_mode`、sidecar identity、`computer_fingerprint`、feature version、Git SHA、dirty 状态与工作区内容指纹。
- 20k sidecar 从 eval MySQL 权威语料重建，992000–992003 各 5,000 chunks。
- 最终 v2 OFF/ON 两轮均 `failed_sources=0`、`zero_ranked=0`；验收报告位于 `runs/golden_v2/scale_100k_991004/scale_20k_overnight/bm25_sqlite_final_acceptance_20260724/`。

### P0：CI远端证据待形成

- `.github/workflows/ci.yml` 已 checkout/安装固定 SHA `6bf3237941657f40fd48ce8c0edec5af127c8f0a` 的公开 `ql-link/LinkRag`。
- CI 设置 `LINKRAG_EVAL_REQUIRE_RAG=1`；缺少 `src.core` 会在测试收集前失败，不能再静默跳过。
- contract 文件已统一标记，workflow 独立执行 16 个真实生产契约测试；本地等价门禁通过。
- workflow 尚未提交、推送，因此还需形成真实 GitHub Actions 全绿证据。

### 已关闭：评测数据真实性与在线化

- Query provenance、多正例 qrels、多 Chunk/跨段落与编号类语料均已补齐。
- 短词回退与 Alias 规则只在 Tune 上选择，随后与模型、特征代码一起哈希冻结。
- 在线模型支持版本化加载、特征签名、预算/超时/错误降级、非阻塞 Shadow、监控和回滚。
- Blind v4 750 条只运行一次并 seal；详细结果见 [Blind v4 最终一次性验收](reports/blind_v4_final_acceptance_2026_07_24.md)。

完整清单与完成标准见 [CURRENT_STATUS.md](CURRENT_STATUS.md#尚未关闭的工作)。

## 5. 推荐执行顺序

1. 将已修复依赖安装和假跳过问题的 workflow 纳入版本控制，推送后确认 GitHub Actions 全绿。
2. Blind v4、Blind v5 均已封存，禁止二次运行或据此调参。
3. 上游生产项目使用 `models/candidate-difference-v3-20260728-final33/` 模型包适配，先以 Shadow 观察真实业务延迟、回退率和 Top10 变化；weighted score 必须保留为启动/异常/主动回滚路径。
4. 下一次效果研究必须新建 Tune/Blind v6，优先增加脱敏真实业务 Query，并预注册验收标准。

## 6. 新对话必读文档

按顺序阅读：

1. [AGENTS.md](../AGENTS.md)：最高优先级实现与安全规则。
2. [本交接文档](HANDOFF.md)：冻结决策、代码审查发现和执行顺序。
3. [当前开发状态](CURRENT_STATUS.md)：项目级完成度和验收标准唯一入口。
4. [文档目录](DOCUMENT_CATALOG.md)：所有人工维护文档及其状态。
5. [解耦独立化方案](architecture/decoupling-plan.md)：存储、依赖边界和Step 0-6。
6. [Golden V2真实召回评测](plans/golden-v2-realistic-evaluation.md)：数据来源、候选池、标注、Tune/Blind纪律。
7. [LambdaMART三路融合](experiments/ltr-fusion-v1.md)：模型原理、特征、训练数据和真实实验结果。
8. [Query候选分流](experiments/query-soft-routing-candidates.md)：冻结候选深度及场景结果。
9. [Query重写配对基准](experiments/query-rewrite-benchmark-v1.md)：为什么不把Query重写设为默认方案。
10. [统一报告索引](reports/REPORT_INDEX.md)：所有保留报告的路径和用途。

数据质量任务还必须阅读：

- [池化重标可靠性](reports/label_reliability_pooled_relabel.md)：单正例qrels和漏标风险。
- [Golden V2阶段实证](reports/golden_v2_realistic_991004_run_2026_07_10.md)：候选、判官、随机负例和标注质量。

## 7. 关键报告

- 最终候选分流/LTR验收：`runs/golden_v2/scale_100k_991004/scale_20k_overnight/ltr_query_expansion_2000/final_2000/candidate_routing_ltr_v3_20260720/candidate_routing_ltr_final_acceptance_report.html`
- Blind v3冻结模型结果：`runs/golden_v2/scale_100k_991004/scale_20k_overnight/ltr_query_expansion_2000/final_2000/candidate_routing_ltr_v3_20260720/blind_v3/evaluation/model_frozen_once/ltr_external_evaluation.html`
- 2,000条训练集完成报告：`runs/golden_v2/scale_100k_991004/scale_20k_overnight/ltr_query_expansion_2000/final_2000/training_set_2000_completion_report.html`
- 20k总体验收：`runs/golden_v2/scale_100k_991004/scale_20k_overnight/scale20k_acceptance_report.html`
- SQLite FTS5最终A/B验收：`runs/golden_v2/scale_100k_991004/scale_20k_overnight/bm25_sqlite_final_acceptance_20260724/bm25_sqlite_fts5_ab_acceptance_report.html`
- Blind v4 最终一次性验收：[blind_v4_final_acceptance_2026_07_24.md](reports/blind_v4_final_acceptance_2026_07_24.md)
- Blind v5 无 Alias 生产契约验收：[blind_v5_production_contract_acceptance_2026_07_28.md](reports/blind_v5_production_contract_acceptance_2026_07_28.md)
- Rerank失败历史：`runs/golden_v2/scale_100k_991004/scale_20k_overnight/ltr_query_expansion_2000/final_2000/candidate_routing_ltr_v3_20260720/cross_encoder_feature_v1/cross_encoder_ltr_experiment_report.html`
- qwen3-vl-rerank 150条对照：`runs/golden_v2/scale_100k_991004/scale_20k_overnight/ltr_query_expansion_2000/final_2000/candidate_routing_ltr_v3_20260720/qwen3_vl_rerank_batch_150_20260721/batch_comparison.html`

## 8. 关键实现入口

- 运行快照：`src/linkrag_eval/models.py`、`src/linkrag_eval/app.py`
- DB结果台账：`src/linkrag_eval/store/db_result_store.py`
- SQLite BM25：`src/linkrag_eval/store/sqlite_bm25.py`
- 召回装配：`src/linkrag_eval/retrieval/recall_factory.py`
- LambdaMART：`src/linkrag_eval/retrieval/learning_to_rank/experiment.py`
- LambdaMART 在线运行：`src/linkrag_eval/retrieval/learning_to_rank/online.py`
- 历史 Alias（活动 v3 不使用）：`src/linkrag_eval/retrieval/aliases.py`、`configs/aliases/general_web_search.v1.json`
- 候选分流：`src/linkrag_eval/retrieval/candidate_routing.py`
- CI：`.github/workflows/ci.yml`、`tests/contract/`、`tests/test_import_boundary.py`

## 9. 每轮收口命令

```bash
PYTHONPATH=src pytest -q
lint-imports
PYTHONPATH=src pytest -q tests/test_import_boundary.py
python3 scripts/build_report_index.py --check
git diff --check
git status --short
```

如果生成了新报告，先运行`python3 scripts/build_report_index.py`更新索引，再执行`--check`。
