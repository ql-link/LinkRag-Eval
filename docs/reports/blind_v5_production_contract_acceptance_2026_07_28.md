# Blind v5 无 Alias 生产契约最终验收

> 验收日期：2026-07-28
> 结论：评测项目工程门禁通过，可向生产端交付模型包并进入 Shadow；不支持直接全量切换的效果结论。

## 1. 本轮关闭的问题

旧 `candidate_difference_v2` 使用了 Golden `scenario` 等线上不可得字段，且模型包绑定了
评测生成的 Alias 词表。本轮将活动特征升级为 `candidate_difference_v3`：38 个特征只依赖
Query、Dense/Sparse/BM25 有序候选和批量读取的候选正文；qrels 仅在训练时生成标签。
Alias 完全关闭，manifest 明确记录 `alias_enabled=false`。

线上控制面同时补齐：

- `lightgbm_text_v1` 序列化格式、LightGBM 版本、完整训练参数和模型 SHA-256；
- 特征版本、顺序与签名校验；
- 250 ms 延迟预算、350 ms 推理超时和加权融合降级；
- 首次发布即可回滚到 `weighted-score-baseline`，且重复回滚不会重新激活坏模型；
- 非阻塞 Shadow、监控计数和主动回滚策略；
- `feature_contract.json`、3 个合成测试向量、`SHA256SUMS` 与 `ltr validate-bundle`。

## 2. 数据与冻结纪律

Tune 使用 450 条既有 Tune，重新在无 Alias 条件下缓存候选；没有使用 Blind 选参。
Blind v5 在运行前冻结为 750 条：

| 子集 | Query | 说明 |
| --- | ---: | --- |
| T2Retrieval 真实搜索 | 500 | 排除此前曝光的 811 个 source record；2,307 个官方正例，419 条多正例 |
| 结构化构造题 | 250 | 新 serial offset；覆盖跨 Chunk、编号、日期、版本号 |

最终 Blind 中 475/750 为多正例。候选缓存 750/750 成功，三路失败为 0；10,299 个候选
`chunk_id` 全部存在正文。Blind 指标只运行一次，结果文件为
`runs/golden_v2/blind_v5_20260728/blind/final_result.json`。

关键冻结值：

- 模型：`candidate-difference-v3-20260728-final33`；
- 特征签名：`52a69c3b8ae5e6a5988f62e0a87a775137a4f16ea769bc66829ec664b8782d7b`；
- 迭代数：33，仅取 Tune 五折最佳迭代数中位数；
- 短词回退：Query 长度 `<=15` 且 `ltr_top12_margin < 0.1` 时使用 Hybrid；
- 候选缓存 SHA-256：`8c097e0c335b2039da4eed7f495ac7e71019ec4a63fe5aae76a2fcde5fcf95f7`；
- 候选正文 SHA-256：`8a04f3f52ee2b5faa8ca306a2edd31c94fe54de351be0b95c273393f166e54da`。
- 最终结果 SHA-256：`e98d98b9f24ffdabd14b3d8abf6dc5f6c53fc582ce41e160e58d5412e3c92d3b`。

生产交付模型包已版本化到
`models/candidate-difference-v3-20260728-final33/`，共 88KB；本地训练原始产物仍保留在
`runs/golden_v2/blind_v5_20260728/models/`。生产仓库接入前必须对版本化目录运行
`ltr validate-bundle --model-dir models/candidate-difference-v3-20260728-final33`。

## 3. Tune 证据

无 Alias 五折 OOF Tune：

| 指标 | weighted score | LambdaMART v3 | 变化 |
| --- | ---: | ---: | ---: |
| Hit@10 | 97.33% | 99.33% | +2.00pp |
| MRR | 84.93% | 96.59% | +11.66pp |

Hit@10 为 9 gained / 0 lost，bootstrap 95% CI `[+0.89pp, +3.33pp]`，McNemar
`p=0.00390625`。

## 4. Blind v5 唯一一次结果

| 指标 | weighted score | LambdaMART v3 + 短词回退 | 变化 |
| --- | ---: | ---: | ---: |
| Hit@10 | 98.80% | 99.07% | +0.27pp |
| MRR | 92.16% | 95.64% | +3.48pp |

Hit@10 为 2 gained / 0 lost；bootstrap 95% CI `[0.00pp, +0.67pp]`，McNemar
`p=0.5`。因此不能宣称 Hit@10 显著提升。

| 场景 | n | Hit@10 变化 | MRR 变化 |
| --- | ---: | ---: | ---: |
| 真实搜索 keyword | 500 | 98.60% → 98.60% | 95.80% → 95.10%（-0.70pp） |
| 跨 Chunk | 56 | 100% → 100% | 89.79% → 97.32%（+7.53pp） |
| 精确编号 | 62 | 98.39% → 100% | 76.64% → 97.10%（+20.46pp） |
| 日期 | 67 | 100% → 100% | 100% → 98.51%（-1.49pp） |
| 版本号 | 65 | 98.46% → 100% | 72.94% → 94.03%（+21.09pp） |

短词低置信度回退触发 355/750，其余 395 次使用 LambdaMART。没有 timeout、error 或
budget exceeded：p50 61.49 ms、p95 83.71 ms、p99 92.07 ms、最大 103.25 ms，均低于
250 ms 预算。

## 5. 验收判断

工程门禁通过：模型不依赖 Alias、Golden 元数据或远端 Rerank，制品可独立校验，异常和
回滚路径完整，Blind 无 Top10 净退化且延迟合格。

效果证据是“整体排序改善，结构化精确检索改善明显”，不是“真实搜索全面提升”。500 条
真实搜索的 Hit@10 持平、MRR 下降 0.70pp，整体 Hit 增益也未达到统计显著。因此生产端可
开始适配和 Shadow，但默认切换必须由真实业务流量继续验证；至少监控 Hit 代理指标、Top10
变化、短词回退率、fallback/error 率和 p95 延迟，并保留 weighted score 一键回滚。

Blind v5 已揭盲并封存，后续不得用它调参或重跑。若要继续提高真实搜索 MRR，必须建立新的
Tune 与 Blind v6，优先使用脱敏真实业务 Query。
