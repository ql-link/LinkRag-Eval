# LinkRag-Eval 下一对话交接

> 更新时间：2026-07-21  
> 当前分支：`codex/ltr-eval-quality-suite`  
> 目标：让新的对话在不重做历史实验、不破坏隔离边界的前提下继续完成剩余工作。

## 1. 开始前必须知道

- 本仓库是独立评测项目，只写 `tolink_rag_eval_db` 和 `eval*` Qdrant collection，绝不写生产库。
- 当前工作区有大量未提交改动和未跟踪文件。先运行 `git status --short`，不得 reset、checkout 或删除不属于当前任务的文件。
- `runs/` 被 Git 忽略，但所有阶段报告必须保留；新报告必须使用新目录或时间戳，禁止覆盖历史产物。
- 当前没有提交或推送。`.github/workflows/ci.yml` 仍是未跟踪文件。
- 项目级进度只以 [CURRENT_STATUS.md](CURRENT_STATUS.md) 为准；历史报告只能证明对应数据和参数下的结果。

## 2. 已冻结决策

1. 主指标使用 chunk 粒度；doc 粒度单独报告，不能混成 headline recall。
2. 当前规模固定在 20k 背景语料，10万扩容暂缓，不是阻塞项。
3. 默认候选来自 Dense、Sparse、SQLite FTS5 BM25 三路，融合与候选深度按冻结配置评测。
4. LambdaMART 固定特征版本为 `candidate_difference_v2`，不依赖 Rerank 分数。
5. 直接 Rerank、Cross Encoder 特征和 qwen3-vl-rerank 路线均已终止；不要重新启用或补跑 Top80。
6. Query重写实验没有稳定收益，不进入默认链路。
7. Blind v3 已揭盲，只能用于回归观察，不能再用于选参或最终验收。

## 3. 已完成的主要结果

- Golden V2 的 chunk qrels、候选池、双判官/QC、Tune/Blind拆分和20k链路已完成。
- LTR训练集为2,000条；Tune OOF：Hybrid 35.75%，LambdaMART 44.90%。
- 未曝光 Blind v3 共150条；Hybrid Recall@10 22.67%，LambdaMART 30.67%，提升8.00pp。
- 候选分流后 Tune候选覆盖98.55%，Blind v3候选覆盖92.67%。
- Rerank直接排序和作为LambdaMART特征均未通过Blind门禁，相关报告保留但路线关闭。
- 全量本地测试最近一次为 `321 passed, 3 skipped`，import-lint与import boundary通过。

## 4. 审查发现的关键缺口

### P0：可复现快照与SQLite BM25验收

- `Snapshot` 尚无 `bm25_mode`、sidecar identity和`computer_fingerprint`字段。
- `EvalDbResultStore` 当前固定写入 `computer_fingerprint=None`。
- 2026-07-14 的116条三路run虽然无失败、无零结果，但BM25权重为0，且快照无法证明使用SQLite FTS5。
- 先补快照契约、文件/DB报告和测试，再在同一冻结集跑BM25关闭/启用A/B clean run，输出Recall/MRR/延迟delta。

### P0：CI可能假绿

- `.github/workflows/ci.yml` 没有安装固定SHA的toLink-Rag。
- 契约测试使用 `pytest.importorskip("src")`；干净Runner缺依赖时可能跳过后仍通过。
- CI必须checkout/安装固定SHA的toLink-Rag，并在CI模式下让缺包直接失败，然后再提交、推送并观察真实Actions结果。

### P1：评测数据真实性

- 2,000条训练数据中1,850条由`gpt-5.3-codex-spark`生成。
- Blind v3最终Golden没有来源、生成器、canonical query和scenario字段，无法报告真实日志/客服/开源占比。
- Blind v3的150条全部只有一个`expected_chunk_id`，需要Top50 pooled独立复核来发现多正例漏标。
- 当前20k基本是一文档一Chunk，同文档差异特征恒为0，无法测试真实长文档、跨Chunk和跨段落问题。
- Blind v4应优先使用脱敏日志、客服/业务问题和开源Query，保留来源元数据；增加多Chunk文档族和多正例qrels。

### P1：召回与在线化

- 短关键词需要基于新Tune数据定义低置信度回退Hybrid门禁。
- 业务别名/同义词词表尚未实现；应版本化、按业务域隔离、保留原Query、限制扩展并拒绝歧义别名。
- 编号、日期、版本号场景缺少未曝光eval-only证据语料。
- LambdaMART尚无模型序列化、在线特征、特征签名校验、延迟预算、超时降级、Shadow、监控和回滚。
- 所有参数冻结后再生成Blind v4；建议至少500条、主要场景至少80条，并报告置信区间/配对显著性。

完整清单与完成标准见 [CURRENT_STATUS.md](CURRENT_STATUS.md#尚未关闭的工作)。

## 5. 推荐执行顺序

1. 扩展`Snapshot`和结果台账，真实记录BM25 backend、sidecar/computer fingerprint、git SHA和特征版本。
2. 修复CI依赖安装和契约测试假跳过问题，将workflow纳入版本控制。
3. 重建SQLite sidecar，在同一冻结集完成BM25关闭/启用A/B clean run并生成delta报告。
4. 引入真实Query来源、多正例pooled标注、多Chunk文档族、编号类语料和Alias Tune。
5. 只在Tune上冻结短词回退和同义词扩展规则。
6. 实现固定`candidate_difference_v2`的LambdaMART在线推理、降级和Shadow。
7. 最后生成Blind v4，一次性验收，不能根据Blind v4继续调参。

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
- Rerank失败历史：`runs/golden_v2/scale_100k_991004/scale_20k_overnight/ltr_query_expansion_2000/final_2000/candidate_routing_ltr_v3_20260720/cross_encoder_feature_v1/cross_encoder_ltr_experiment_report.html`
- qwen3-vl-rerank 150条对照：`runs/golden_v2/scale_100k_991004/scale_20k_overnight/ltr_query_expansion_2000/final_2000/candidate_routing_ltr_v3_20260720/qwen3_vl_rerank_batch_150_20260721/batch_comparison.html`

## 8. 关键实现入口

- 运行快照：`src/linkrag_eval/models.py`、`src/linkrag_eval/app.py`
- DB结果台账：`src/linkrag_eval/store/db_result_store.py`
- SQLite BM25：`src/linkrag_eval/store/sqlite_bm25.py`
- 召回装配：`src/linkrag_eval/retrieval/recall_factory.py`
- LambdaMART：`src/linkrag_eval/retrieval/learning_to_rank/experiment.py`
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
