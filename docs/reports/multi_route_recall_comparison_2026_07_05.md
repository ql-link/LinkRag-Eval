# 多路召回对比报告(稠密 / 稠密+BM25 / 稠密+稀疏+BM25)

## 范围

- 时间:2026-07-04 晚至 2026-07-05 00:07(Asia/Shanghai)。
- 数据:四域 clean golden,394 条 doc 粒度 query。
- 语料:四域各 800 chunk,共 3200 chunk。
- Qdrant:
  - dense/sparse collection:`eval_doubao_v2_kb_bucket_9`
  - BM25 collection:`eval_bm25`,已写入 3200 points
- MySQL:`tolink_rag_eval_db`,四域 `bm25_indexed=800/800`。
- 运行质量:三组 run 均为 clean,即 `failed_sources=0` 且 `zero_ranked=0`。

## 召回口径

三组均走正式 `linkrag-eval run --precheck` 路径,融合算法为 `weighted_score`,`final_top_k=10`。本轮是路由对比,不是权重搜索;权重只用于给 BM25 一个保守辅助占比:

| 组别 | enabled_sources | dense_top_k | sparse_top_k | bm25_top_k | dense_weight | sparse_weight | bm25_weight |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 稠密 | `dense` | 150 | 50 | 50 | 1.0 | 0.0 | 0.0 |
| 稠密+BM25 | `dense,bm25` | 150 | 50 | 50 | 0.9 | 0.0 | 0.1 |
| 稠密+稀疏+BM25 | `dense,sparse,bm25` | 150 | 50 | 50 | 0.8 | 0.1 | 0.1 |

阈值沿用当前 eval 默认:`dense_threshold=0.30`,`sparse_threshold=0.40`。BM25 使用 Qdrant sparse collection + IDF modifier,文档侧由生产 `Bm25SparseEncoder` 编码,查询侧由生产 `RagFlowTokenizer` 分词。

## 指标总览

| 组别 | run_id | quality | recall@10 | hit_rate@10 | MAP | MRR | nDCG@10 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 稠密 | `route-dense-only-20260704-top10` | clean | 0.9745 | 0.9898 | 0.8954 | 0.9178 | 0.9224 |
| 稠密+BM25 | `route-dense-bm25-20260704-top10` | clean | **0.9750** | 0.9898 | **0.8986** | 0.9214 | **0.9249** |
| 稠密+稀疏+BM25 | `route-dense-sparse-bm25-20260704-top10` | clean | 0.9725 | 0.9873 | 0.8984 | **0.9216** | 0.9243 |

## 分段指标

| 组别 | recall@1 | recall@3 | recall@5 | recall@10 | precision@10 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 稠密 | 0.6393 | 0.8448 | **0.9199** | 0.9745 | 0.2114 |
| 稠密+BM25 | 0.6482 | 0.8384 | 0.9175 | **0.9750** | **0.2117** |
| 稠密+稀疏+BM25 | **0.6507** | 0.8321 | 0.9170 | 0.9725 | 0.2114 |

## 相对变化

相对稠密-only:

| 组别 | Δ recall@10 | Δ MAP | Δ MRR | 观察 |
| --- | ---: | ---: | ---: | --- |
| 稠密+BM25 | +0.0005 | +0.0032 | +0.0036 | BM25 对 top10 查全增益很小,但对排序质量有稳定小幅提升。 |
| 稠密+稀疏+BM25 | -0.0020 | +0.0030 | +0.0039 | 三路下 rank 1/MRR 更好,但 top10 查全略降。当前权重未调参,低分 sparse/BM25 候选仍可能挤压 dense 命中。 |

相对稠密+BM25:

| 组别 | Δ recall@10 | Δ MAP | Δ MRR | 观察 |
| --- | ---: | ---: | ---: | --- |
| 稠密+稀疏+BM25 | -0.0025 | -0.0002 | +0.0002 | 加 sparse 后 top10 查全下降,但首位排序略改善。 |

## 来源重叠

| 组别 | all_sources | dense_only | sparse_only | bm25_only |
| --- | ---: | ---: | ---: | ---: |
| 稠密 | - | 1.0000 | - | - |
| 稠密+BM25 | 0.4530 | 0.5497 | - | 0.0090 |
| 稠密+稀疏+BM25 | 0.2624 | 0.5330 | 0.0070 | 0.0066 |

BM25 与 dense 有较高重叠,纯 BM25-only 命中占比低,说明本轮 BM25 更像排序辅助信号,而不是显著增加候选覆盖的主召回信号。Sparse-only 与 BM25-only 占比都很低,三路增益主要来自融合排序而非新增大量独占候选。

## 结论

1. 当前三组 clean run 中,`稠密+BM25` 是最稳的默认候选:它保持 dense-only 的 hit_rate@10,并把 recall@10 从 0.9745 小幅提高到 0.9750,同时 MAP/MRR 均提升。
2. `稠密+稀疏+BM25` 在未调参权重下不应直接作为新标准基线:recall@10 低于 `稠密+BM25`,但 MRR 略高。若目标是答案排得更靠前,三路有继续调权重的价值;若目标是 top10 查全,当前权重不如 `稠密+BM25`。
3. 下一步建议对三路做小网格搜索,重点搜索 `sparse_weight` 和 `bm25_weight`。当前结果已经证明 BM25 backend 可用,但三路最优融合权重尚未固化。

## 产物

- BM25 backfill:四域 3200 chunk 写入 `eval_bm25`,DB `eval_corpus_chunk.bm25_indexed=True`。
- 稠密结果:`runs/results/route-dense-only-20260704-top10.json`
- 稠密+BM25 结果:`runs/results/route-dense-bm25-20260704-top10.json`
- 稠密+稀疏+BM25 结果:`runs/results/route-dense-sparse-bm25-20260704-top10.json`
- HTML 报告:
  - `runs/route-dense-only-20260704-top10.html`
  - `runs/route-dense-bm25-20260704-top10.html`
  - `runs/route-dense-sparse-bm25-20260704-top10.html`
