# Blind v4 最终一次性验收

> 验收日期：2026-07-24
> 运行 ID：`blind-v4-final-once-20260724`
> 结论：工程门禁通过；效果方向为正，但 Hit@10 的 95% 置信区间跨 0，不能宣称统计显著提升。

## 1. 最终结果

| 指标 | 固定 Hybrid | 在线 LambdaMART + 短词回退 | 变化 |
| --- | ---: | ---: | ---: |
| Hit@10 | 98.5333% | 98.9333% | +0.4000pp |
| MRR | 90.4054% | 98.0213% | +7.6158pp |

- 配对结果：获益 4 条、退化 1 条、discordant 5 条。
- Hit@10 bootstrap 95% CI：`[-0.1333pp, +1.0667pp]`；McNemar exact `p=0.375`。
- Blind 候选生成 750/750 成功，失败 0；门禁 `run_count=1`，结果已经 seal。
- 在线排序延迟：p50 `140.68ms`、p95 `184.37ms`、p99 `206.37ms`；没有预算超限、超时或异常降级。
- 执行模式：LambdaMART 529 条；短关键词低置信度回退 Hybrid 221 条；Shadow 750 条全部完成。

因此，本轮证明了固定在线链路可以安全运行，且总体排序质量改善；但新增 Hit@10 只有 3 条净收益，统计证据不足以把“显著提升 Hit@10”写成结论。后续若继续优化，必须新建 Tune/Blind 版本，不能复用本次 Blind v4 选参。

## 2. 数据与来源

- 最终数据包：Tune 450 条、Blind 750 条、语料 10,300 chunks。
- Query 来源：T2Retrieval 开源检索 Query 800 条；带明确构造真值的 eval-only 合成 Query 400 条。每条保留 `provenance`、来源版本、业务域、canonical query 和场景。
- 场景：开源真实搜索 Query 800 条；`cross_chunk`、日期、精确编号、版本号各 100 条。
- 多正例：Tune 306 条，Blind 490 条。
- 数据集 993101 包含 10,000 个 T2Retrieval passages；数据集 993102 包含 100 个三段文档、300 chunks，保留 `doc_id + ordinal`，覆盖跨段落、编号、日期、版本号和同文档干扰。
- 当次验收只写 eval 独立存储；2026-07-25 元数据/结果已迁到本地 `runs/linkrag_eval.sqlite3`，Qdrant 仍只写 `eval_doubao_v2_kb_bucket*`。

开源 Query 和 qrels 来自 C-MTEB T2Retrieval；本次固定了数据 revision、qrels revision、许可证和行级来源元数据。合成部分明确标记为 `synthetic`，不冒充真实用户日志。

## 3. Top50 pooled 独立复核

对 300 条开源 Tune Query 的 Dense、Sparse、BM25 三路候选取固定 pooled Top50，共 15,000 个 blinded query-chunk 对：

| 项 | 数量 |
| --- | ---: |
| 双方一致 | 13,616 |
| 分歧并交由第三方仲裁 | 1,384 |
| 未解决 | 0 |
| 最终正 qrels | 1,782 |
| 多正例 Query | 270 / 300 |

Reviewer A 使用官方 qrels，独立 Reviewer 使用 `deepseek-v4-flash`，分歧由 `deepseek-v4-pro` 仲裁。复核后相对官方 Tune qrels 新增 397 个正例（+28.66%）。早期使用无效模型名生成的输出已隔离，不进入最终 qrels。

## 4. 冻结参数

- 模型：`candidate-difference-v2-20260724-final50`，50 trees。
- 特征版本：固定 `candidate_difference_v2`；签名 `ed96f4535bede89b36ef871cacb821725ad46e46e11e29c000846bcc9f2d0231`。
- 模型 SHA-256：`a091d88d2cf173099b224124d422d3d73543d095d6efe6ea45ba42ec90b5bcff`。
- Alias 词表：`general_web_search.2026-07-24.v1`，按业务域隔离；`卡/单/码/号` 等歧义词默认拒绝扩展。Alias 只用于 BM25/Sparse，Dense 保留原 Query。
- 短词回退：Query 长度不超过 10 且 `ltr_top12_margin < 0.3` 时回退固定 Hybrid；参数只由 Tune 选择。
- 延迟预算：Tune 冒烟测得 p99 `205.55ms` 后冻结 budget `250ms`、timeout `350ms`。
- Shadow：`candidate-difference-v2-20260724-shadow35`；支持异步比较、计数和 Top10 变化监控。
- 回滚：active registry 和历史记录均已验证 `activate -> rollback -> activate`；模型/特征签名不符、超时、异常或预算超限时回退 Hybrid。

## 5. 分场景结果

| 场景 | N | Hybrid Hit@10 | 最终 Hit@10 |
| --- | ---: | ---: | ---: |
| 开源短关键词 | 500 | 98.60% | 98.40% |
| 跨 Chunk | 64 | 100.00% | 100.00% |
| 日期 | 59 | 100.00% | 100.00% |
| 精确编号 | 64 | 98.44% | 100.00% |
| 版本号 | 63 | 95.24% | 100.00% |

短关键词仍有 1 条净退化，说明回退门禁降低了风险但没有完全消除该场景波动；编号和版本号场景有明确收益。构造真值场景与开源 Query 的难度不同，只能分别解读，不能用前者的高绝对值替代真实 Query 结论。

## 6. 证据路径

- 冻结门禁：`runs/golden_v2/blind_v4_20260724/blind/frozen/manifest.json`
- 最终机器结果：`runs/golden_v2/blind_v4_20260724/blind/final_result.json`
- Blind 候选缓存：`runs/golden_v2/blind_v4_20260724/blind/ltr_candidates.jsonl`
- 数据包清单：`runs/golden_v2/blind_v4_20260724/bundle/final/bundle_manifest.json`
- pooled 复核报告：`runs/golden_v2/blind_v4_20260724/review/live_tune_v2/pooled_review_report.json`
- Tune CV：`runs/golden_v2/blind_v4_20260724/tune/cv/ltr_cross_validation.json`
- Tune 在线冒烟：`runs/golden_v2/blind_v4_20260724/tune/online_smoke_frozen.json`

Blind 文件 SHA-256 为 `e1ba88a8e3416cbb83dfe4ee51ff0279362adf8d98127b0dfc5568b27dd89520`；最终结果 SHA-256 为 `8a35e292a3f63b964dbb1fc508df23b3e38697c4aaf4933a65565d44db923bae`。
