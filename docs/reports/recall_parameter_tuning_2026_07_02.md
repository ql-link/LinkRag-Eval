# Recall 参数搜索报告(2026-07-02)

## 结论

在正式 eval 前缀 `eval_doubao_v2_kb_bucket`、四域 394 条 clean golden 上,本轮 720 组网格搜索的推荐配置为:

| 参数 | 推荐值 | 说明 |
| --- | ---: | --- |
| `EVAL_RECALL_DENSE_SCORE_THRESHOLD` | 0.30 | dense 阈值在 0.0-0.3 指标持平,0.4 后 recall 下降;取 0.30 是同分下更严格的过滤选择 |
| `EVAL_RECALL_SPARSE_SCORE_THRESHOLD` | 0.40 | 主要收益来源,用于过滤低分 sparse 噪声 |
| dense 分路 topK | 20 | 本轮搜索中的最优候选池规模 |
| sparse 分路 topK | 5 | 明显优于更大的 sparse 候选池,说明低分 sparse 候选参与 RRF 会伤害排序 |
| final topK / RRF k | 10 / 60 | 与现有 recall@10 评测口径一致 |

最佳指标:

| recall@10 | hit_rate@10 | MAP | MRR | 样本数 | 分路失败样本 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.9715 | 0.9873 | 0.8782 | 0.9045 | 394 | 0 |

## 测试范围

- Golden: `combined_4domain_clean.jsonl`
- 样本数: 394
- Query 长度: 平均 17.73 字符,中位数 9 字符,p90 48.7 字符,最短 3 字符,最长 120 字符;按空白切分平均 1.03 token。口径为 JSONL `query` 字段的原始字符数。
- 语料: 四域各 800 chunk,合计 3200 chunk
- Qdrant: 正式 eval 前缀 `eval_doubao_v2_kb_bucket`
- MySQL: eval 独立库 `tolink_rag_eval_db`
- RRF: `rrf_k=60`,最终截断 `top_k=10`

Query 长度分布说明:这批 golden 以短 query 为主,典型样本接近实体/短语检索。这个分布解释了为什么 sparse 在本轮更适合高阈值、小 topK 参与 RRF:短 query 的词面信号少,低分 sparse 候选更容易成为排序噪声。

短 query 结论:在当前 query 长度分布下,稀疏向量对召回/排序的直接帮助比较差,大 topK 或低阈值 sparse 反而会把 dense 已命中的正确结果挤出 top10。后续可以在 RAG 链路中引入 LLM query rewrite:先把短 query 改写成更完整、包含意图/实体/约束的检索 query,再进入 sparse 匹配,让 sparse 获得更充分的词面信号。

## 搜索方法

新增 `linkrag-eval tune-recall` 命令:

```bash
PYTHONPATH=src python3 -m linkrag_eval.cli tune-recall \
  --golden /Users/jixu/Project/Agent/toLink-Rag/.claude/worktrees/sleepy-margulis-9143dc/.specs/rag-quality-eval/golden/combined_4domain_clean.jsonl \
  --dataset combined_4domain_clean \
  --out-dir runs/tuning \
  --corpus-chunks 3200 \
  --dense-top-ks 20,50,100,200 \
  --sparse-top-ks 5,10,20,50,100 \
  --dense-thresholds 0,0.1,0.2,0.3,0.4,0.5 \
  --sparse-thresholds 0,0.2,0.25,0.3,0.35,0.4 \
  --concurrency 4
```

执行过程先分别拉取 dense/sparse 最大候选池,再在本地按生产 RRF 公式复算不同 topK 和阈值组合。这样可以避免每组参数都重复请求远端 Qdrant/embedding 服务。

## 搜索空间

| 维度 | 取值 |
| --- | --- |
| dense_top_k | 20, 50, 100, 200 |
| sparse_top_k | 5, 10, 20, 50, 100 |
| dense_threshold | 0.0, 0.1, 0.2, 0.3, 0.4, 0.5 |
| sparse_threshold | 0.0, 0.2, 0.25, 0.3, 0.35, 0.4 |

合计 `4 * 5 * 6 * 6 = 720` 组配置。

## Top 10

| rank | dense_top_k | sparse_top_k | dense_th | sparse_th | recall@10 | hit_rate@10 | MAP | MRR |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 20 | 5 | 0.300 | 0.400 | 0.9715 | 0.9873 | 0.8782 | 0.9045 |
| 2 | 20 | 5 | 0.200 | 0.400 | 0.9715 | 0.9873 | 0.8782 | 0.9045 |
| 3 | 20 | 5 | 0.100 | 0.400 | 0.9715 | 0.9873 | 0.8782 | 0.9045 |
| 4 | 20 | 5 | 0.000 | 0.400 | 0.9715 | 0.9873 | 0.8782 | 0.9045 |
| 5 | 20 | 10 | 0.300 | 0.400 | 0.9715 | 0.9873 | 0.8773 | 0.9037 |
| 6 | 20 | 50 | 0.300 | 0.400 | 0.9715 | 0.9873 | 0.8772 | 0.9035 |
| 7 | 20 | 100 | 0.300 | 0.400 | 0.9715 | 0.9873 | 0.8772 | 0.9035 |
| 8 | 20 | 20 | 0.300 | 0.400 | 0.9715 | 0.9873 | 0.8770 | 0.9033 |
| 9 | 20 | 10 | 0.200 | 0.400 | 0.9715 | 0.9873 | 0.8761 | 0.9024 |
| 10 | 20 | 10 | 0.100 | 0.400 | 0.9715 | 0.9873 | 0.8761 | 0.9024 |

## 敏感性分析

固定 `dense_top_k=20`、`sparse_top_k=5` 时:

| sparse_threshold | 最佳 dense_threshold | recall@10 | MAP | MRR |
| ---: | ---: | ---: | ---: | ---: |
| 0.00 | 0.30 | 0.9589 | 0.8348 | 0.8827 |
| 0.20 | 0.30 | 0.9620 | 0.8361 | 0.8830 |
| 0.25 | 0.30 | 0.9646 | 0.8371 | 0.8834 |
| 0.30 | 0.30 | 0.9665 | 0.8430 | 0.8830 |
| 0.35 | 0.30 | 0.9699 | 0.8699 | 0.8988 |
| 0.40 | 0.30 | 0.9715 | 0.8782 | 0.9045 |

主要结论:

- sparse 阈值越高,低分 sparse 噪声越少,本轮在 0.40 达到最佳。
- dense 阈值 0.0-0.3 基本不影响最高指标;0.4 和 0.5 开始损伤 recall。
- sparse_top_k 越大不一定越好。RRF 会奖励多路命中的候选,当 sparse 低分候选语义噪声较高时,更大的 sparse 候选池反而会把 dense 第 1 的正确文档挤出最终 top10。

## 落地状态

已落地:

- `EVAL_RECALL_DENSE_SCORE_THRESHOLD` 默认值更新为 0.30。
- `EVAL_RECALL_SPARSE_SCORE_THRESHOLD` 默认值更新为 0.40。
- 新增 `tune-recall` 命令,可复跑参数搜索并生成 CSV/JSON/Markdown 结果。

尚未落地:

- 正式 `linkrag-eval run` 仍通过生产 `RecallPipeline.execute(RecallRequest(top_k=...))` 执行,目前只有一个融合口径 `top_k`,没有 dense/sparse 分路独立 topK。
- 因此 `dense_top_k=20`、`sparse_top_k=5` 目前是 tuning harness 的推荐值,还需要后续在正式 run 路径中增加分路 topK 支持,再生成可入台账的标准结果。

原始产物:

- `runs/tuning/recall_tuning_combined_4domain_clean_20260702_195607.md`
- `runs/tuning/recall_tuning_combined_4domain_clean_20260702_195607.csv`
- `runs/tuning/recall_tuning_combined_4domain_clean_20260702_195607.json`
