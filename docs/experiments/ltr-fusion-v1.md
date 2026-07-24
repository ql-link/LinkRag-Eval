# LambdaMART 三路召回融合方案与实验分析（v1）

> 状态：2000 条训练、候选分流重训和未曝光 Blind v3 一次性验证已完成；Rerank/Cross Encoder 路线已终止，LambdaMART 固定为不含重排分数的 `candidate_difference_v2`；尚未接入生产默认链路。项目级进度见 [CURRENT_STATUS.md](../CURRENT_STATUS.md)。

## 0. 结论摘要

LinkRag-Eval 的检索链路先后验证了三种提升 `Recall@10` 的方案：文本 Rerank、按通道 Query 重写、
LambdaMART 学习融合。核心诊断是——**正确 Chunk 绝大多数已被三路召回，但固定权重融合没有把它排进 Top10**。
因此真正的瓶颈是**候选融合与排序**，而不是"找不到证据"。

三套方案的实测结论：

| 方案 | 直接作用对象 | 关键结果 | 是否进入默认链路 |
| --- | --- | --- | --- |
| qwen3-rerank 文本重排 | 重判文本相关性、覆盖原排序 | Tune Top60 Clean 复测 Recall@10 **-13.99pp**；Blind Top20 Recall 无增益、MRR 下降 | 否 |
| 按通道 Query 重写 | 改写查询文本 | 40 条无失败成对：Recall 持平、MRR **-1.65pp**；消融出现 Recall 退化 | 否 |
| **LambdaMART 学习融合** | 学习三路候选相对顺序 | Blind v3 相对同候选 Hybrid **+8.00pp** | **完成独立实验验证，暂不替换生产 Hybrid** |

LambdaMART 在三套口径上的一致提升：

| 验证集 | 验证方式 | n | 固定 Hybrid Recall@10 | LambdaMART Recall@10 | ΔRecall | ΔMRR |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Balanced Tune | 按证据文档分组 5 折样本外预测 | 420 | 63.33% | 71.90% | **+8.57pp** | +8.73pp |
| 旧 realistic Blind | 420 条模型跨分布一次性评测 | 116 | 44.83% | 50.86% | **+6.03pp** | -2.50pp |
| 扩展严格集 | 5 折样本外预测 | 1050 | 42.57% | 48.38% | **+5.81pp** | +4.03pp |
| 候选分流扩展 Tune | 按证据文档分组 5 折样本外预测 | 2000 | 35.75% | 44.90% | **+9.15pp** | +3.67pp |
| 未曝光 Blind v3 | 冻结参数后一次性评测 | 150 | 22.67% | 30.67% | **+8.00pp** | +2.41pp |

> 当前结论：**LambdaMART 对三路召回融合具有明确价值，但仍不能直接替代生产 Hybrid。**
> 候选覆盖优化和未曝光 Blind v3 已完成；Blind v3 证明整体提升 8.00pp，但绝对 Recall@10 只有 30.67%，且短关键词下降 3.33pp。下一步是短词回退门禁和在线推理、降级、Shadow 测试。

> **口径提示**：不同阶段使用的 Query 数量、数据分布和候选参数不完全一致，因此**不能**跨报告用绝对召回率判断模型优劣。
> 所有"变化量"只在同一份报告、同一批 Query 内计算。

---

## 1. 问题定义：固定权重融合是当前瓶颈

检索系统包含三条召回通道，各有擅长的 Query 类型：

- **Dense**：自然语言语义、同义表达、改写 Query；
- **Sparse**：关键词密集、长描述、稀疏语义 Query；
- **BM25**：编号、日期、版本号、专有名词、精确词匹配。

三路召回后，原系统使用**固定阈值 + 固定权重**融合：

```text
HybridScore = 0.70 * DenseScore + 0.15 * SparseScore + 0.15 * BM25Score
```

| 通道 | 过滤阈值 | 融合权重 |
| --- | ---: | ---: |
| Dense | 0.30 | 0.70 |
| Sparse | 0.20 | 0.15 |
| BM25 | 0 | 0.15 |

该配置隐含一个不成立的假设：**所有 Query 都适用相同的通道贡献比例**。例如：

- 编号 Query 主要依赖 BM25，但固定权重只给 BM25 0.15；
- 长描述 Query 常由 Sparse 命中，但 Sparse 权重不足；
- 自然语言改写更依赖 Dense，此时抬高 BM25 反而引入精确词干扰；
- 同一候选被多路共同召回时，固定加权没有利用"多路一致性"这一强信号。

**关键诊断（Balanced 420 集）：**

| 指标 | 结果 |
| --- | ---: |
| 三路完整候选池正确 Chunk 覆盖率 | 99.05% |
| 固定 Hybrid Recall/Hit@10 | 63.33% |

99.05% 的候选池覆盖率说明正确 Chunk 几乎都已被某一路召回，只是没被排进 Top10。
**瓶颈在排序，不在召回。** 这正是后续方案选型的出发点。

---

## 2. 方案演进：为什么最终选 LambdaMART

Rerank 和 Query 重写在理论上并非无效，但在当前 20k 语料、Chunk 级黄金集和三路候选结构上
没有产生稳定正收益。两者都改写/重判**文本**，而没有直接解决"候选已存在、排序没排上"的问题。

### 2.1 第一阶段：qwen3-rerank 文本重排

流程：固定加权 Hybrid 生成候选 → 融合后 TopK Chunk 正文提交 `qwen3-rerank` → 截取 Top10。
Tune 集 272 条 Query，融合权重 Dense 0.70 / Sparse 0.15 / BM25 0.15。

| Rerank 候选深度 | Hit@10 | Chunk Recall@10 | MRR |
| ---: | ---: | ---: | ---: |
| Top20 | 43.01% | 32.11% | 15.18% |
| Top40 | 38.97% | 27.70% | 13.44% |
| Top60 | 36.40% | 25.83% | 13.27% |
| Top80 | 33.09% | 22.90% | 13.09% |

**Top60 Clean 严格复测（2026-07-17）**：三路候选最终零失败，Hybrid 与 Rerank 共用同一候选池，
排除了此前召回断连的比较干扰。

| 指标 | 固定 Hybrid | Top60 Rerank | 变化 |
| --- | ---: | ---: | ---: |
| Chunk Recall@10 | 39.73% | 25.74% | **-13.99pp** |
| Hit@10 | 51.47% | 36.03% | -15.44pp |
| MRR | 20.68% | 13.31% | -7.37pp |

Blind 辅助对照（116 条 realistic，候选参数与主报告不完全一致，仅作旁证）：

| 指标 | 历史未重排 Hybrid | qwen3-rerank Top20 | 变化 |
| --- | ---: | ---: | ---: |
| Hit@10 | 39.66% | 39.66% | 0.00pp |
| MRR | 15.78% | 14.88% | -0.91pp |

**负增长的结构性原因**（已排除 API 失败 0/272、召回断连 0/272、正文截断等测试数据因素）：

- Rerank 只看 Query 与 Chunk 正文，**完全覆盖**原 Hybrid 顺序，看不到 Dense/Sparse/BM25 原始分数、
  分路排名、多路共同命中、编号精确匹配等信号；
- 通用文本相关性更偏好"主题相似、表述完整"的 Hard Negative，而非黄金集标注的精确证据；
- TopK 越大，引入的同领域相似 Chunk 越多，混淆越重；`Hit@10`（命中任意一个正确 Chunk 即可）
  也下降 15.44pp，说明退化不能仅用"多参考漏标"解释。

**结论**：证明"Top60 全量覆盖式 Rerank 在当前数据不适用"，但不证明 `qwen3-rerank` 在所有组合下无效。
它后续只适合在候选覆盖已满足、高歧义样本被识别后，对**很小的候选集合**做受控实验（如 Hybrid+Rerank 分数融合、
保护 Hybrid Top3），而非替换整条排序。

### 2.2 第二阶段：按召回通道 Query 重写

让推理模型把原 Query 分别改写为 Dense 用的语义表达、Sparse 用的关键词/条件表达、BM25 用的精确词/编号表达，
并测试动态权重、候选保护、仅重写等消融。最可信的是 40 条无失败重试成对结果（原始与重写检索均无请求失败）：

| 方案 | 原始 Recall@10 | 重写后 Recall@10 | ΔRecall | 原始 MRR | 重写后 MRR | ΔMRR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 通道重写 + 动态权重 + 候选保护 | 55.00% | 55.00% | 0.00pp | 19.82% | 18.17% | -1.65pp |

消融给出同方向结果：

| 消融方案 | 可用样本 | ΔRecall@10 | ΔMRR | 命中迁移 |
| --- | ---: | ---: | ---: | --- |
| 仅 Query 重写 | 39 | -2.56pp | -1.50pp | 新增 0，丢失 1 |
| 仅重写 + 原始 Top5 保护 | 39 | 0.00pp | -1.25pp | 新增 0，丢失 0 |

原始 Top5 保护避免了 Recall 退化，但**没有新增命中**，MRR 仍下降。说明 Query 重写主要改变了候选顺序，
没有稳定召回原本缺失的证据。可能原因：重写压缩了否定词/条件/编号/时间约束；三路分别扩写扩大候选并集、引入相似干扰；
且瓶颈本就是"候选已在但没排上"，单纯改 Query 不解决融合排序。

**结论**：不作默认主链路。更合理的用途是识别低置信度 Query 后按需触发，并同时保留原 Query，避免覆盖精确约束。

### 2.3 第三阶段：转向 LambdaMART

前两类方案改写/重判文本，而 LambdaMART 直接针对已确认的核心问题：
**正确 Chunk 已进入三路候选池，固定权重没把它排进 Top10。** 结果见第 5 节，三套验证均取得 Recall 正增长。

---

## 3. 为什么选择 LambdaMART

LambdaMART 是面向搜索排序的 Learning to Rank 模型。当前实现使用 LightGBM 的 `LGBMRanker`，
**不是大语言模型，也不是外部 Rerank API**。

### 3.1 训练目标与检索目标一致

分类模型判断"是否相关"、回归模型预测分数，而 LambdaMART 直接学习同一 Query 下候选 Chunk 的**相对顺序**，
让相关 Chunk 排在不相关 Chunk 前面，更契合 `Recall@10` / `MRR@10` / `NDCG@10`。

### 3.2 能表达固定权重无法表达的非线性规则

多棵决策树可以学习条件组合，例如：

- Query 含编号且 BM25 排名靠前 → 增强 BM25 候选；
- 长 Query 中 Sparse 与 Dense 同时命中 → 提高候选可信度；
- 候选被三路共同召回 → 提高多路一致性贡献；
- 某一路分数高但其他通道完全不支持 → 降低异常候选优先级；
- 不同 Query 类型采用不同的隐式融合策略。

因此它不是学三个固定权重，而是按 Query 和候选特征动态计算排序分数。

### 3.3 适合当前训练数据规模

只有几百条 Tune Query，但每条都带大量候选 Chunk。树模型对这种中小规模结构化排序数据的训练稳定性和
可解释性通常优于直接训练深度神经排序网络。

### 3.4 线上成本低

模型只消费检索阶段已有的分数、排名和 Query 特征——不读 Chunk 正文、不调外部大模型、不按 Token 计费、
不需把数百候选发给 Rerank API，可在候选融合阶段本地执行。

---

## 4. 原理、模型配置与特征

### 4.1 LambdaMART 原理（LambdaRank 目标 + MART 梯度提升树）

1. **按 Query 组织样本**：每条 Query 的三路候选组成一个排序组；标签只用 `expected_chunk_ids`——
   正确证据 Chunk 记 `1`，其余候选记 `0`，**不退化到文档粒度** `expected_doc_ids`。
2. **优化相对顺序**：不只看单点预测是否准，而是看交换两个候选位置会对 `NDCG@10` 造成多大影响；
   把正确 Chunk 从第 30 位挪到第 5 位若显著改善指标，模型对这种排序错误赋予更大优化权重，越靠前影响越大。
3. **梯度提升树学分数**：`LTRScore = Tree1(x) + Tree2(x) + ... + TreeN(x)`，同一 Query 下按 `LTRScore`
   从高到低排序，再取 Top10。

### 4.2 模型配置（对应 `experiment.py`）

| 配置 | 当前值 |
| --- | --- |
| 实现 | LightGBM `LGBMRanker`（4.6.0） |
| 目标函数 | `lambdarank` |
| 验证指标 | `NDCG@10`（`eval_at=[10]`） |
| 最大训练轮数 | 300 |
| 学习率 | 0.03 |
| 叶子数 | 15 |
| 最大深度 | 4 |
| `min_child_samples` | 20 |
| Early Stopping | 30 轮 |
| 随机种子 | 20260716 + Fold 编号（CV）/ 20260716（外部评测） |

### 4.3 候选范围（离线实验口径）

每条 Query 使用以下候选的**去重并集**：

| 通道 | 候选深度 |
| --- | ---: |
| Dense | Top150 |
| Sparse | Top50 |
| BM25 | Top100 |

生产端仍需结合延迟和内存测试确定最终截断深度。

### 4.4 输入特征（26 维，均为结构化检索特征，不含 Chunk 正文）

- Dense 原始分数、Sparse/BM25 对数分数（`log1p`）；
- 三路内部归一化分数（Dense 用原分、Sparse/BM25 用 log 分做 min-max）；
- 三路倒数排名 `1/rank`；
- 三路缺失标记；
- 候选被几路召回（`route_count`）、是否三路共同召回（`all_routes`）；
- 固定 Hybrid 分数与倒数排名；
- Query 字符长度、Query 是否含数字；
- 场景独热标记（短关键词 / 编号日期版本 / 长描述多条件 / 自然语言改写 / 相似文档 / 多约束 / 数字时间 / 别名）。

**特征重要性 Top8（Balanced 420 CV）：**

| 特征 | 重要性 |
| --- | ---: |
| 固定 Hybrid 倒数排名 `baseline_rr` | 242 |
| Sparse 倒数排名 `sparse_rr` | 218 |
| BM25 倒数排名 `bm25_rr` | 179 |
| BM25 归一化分数 `bm25_norm` | 155 |
| Sparse 归一化分数 `sparse_norm` | 96 |
| Dense 倒数排名 `dense_rr` | 96 |
| 固定 Hybrid 分数 `baseline_score` | 93 |
| Dense 原始分数 `dense_score` | 84 |

模型并未抛弃固定 Hybrid（`baseline_rr` 重要性最高），而是在其基础上**重点纠正 Sparse、BM25 和多路排名
信息未被充分利用**的问题。缺失标记、`all_routes`、部分场景独热重要性为 0，说明关键信号已被排名/归一化特征捕获。

---

## 5. 验证结果

### 5.1 训练/测试划分：按证据文档分组的 5 折交叉验证

Balanced Tune 共 420 条 Query，每场景 105 条。**不是原地测试**，而是：

1. 按 `expected_doc_ids` 将 Query 分为 5 个 Fold；
2. 每轮用 4 折训练、剩余 1 折测试，重复 5 轮，使每条 Query 各得一次样本外预测；
3. **同一证据文档对应的 Query 不允许同时进入训练 Fold 和测试 Fold**（防证据泄漏）。

因此 420 条结果均来自没训练过对应 Query 和证据文档的模型。但训练与测试仍来自同一套 Tune 分布——
该方式适合判断方案是否有效，**不能替代**一套完全独立、从未用于设计或调参的 Blind 集。

### 5.2 Balanced 420：总体与命中迁移

| 指标 | 固定 Hybrid | LambdaMART | 变化 |
| --- | ---: | ---: | ---: |
| Recall/Hit@10 | 63.33% | 71.90% | +8.57pp |
| MRR@10 | 29.23% | 37.96% | +8.73pp |

> 当前黄金集每条 Query 主要对应一个正确 Chunk，因此此处 `Hit@10` 与单相关项口径下的 `Recall@10` 数值一致。

5 个 Fold 的 `Recall@10` 变化：`+5.49 / +8.42 / +9.33 / +11.94 / +8.70`（pp）——**全部为正**，
说明提升不是单个随机划分造成的。

命中迁移（候选池覆盖率 99.05%）：

| 类型 | Query 数 | 含义 |
| --- | ---: | --- |
| kept_hit | 240 | 两种方式都命中 |
| gained | 62 | Hybrid 未命中、LambdaMART 命中 |
| lost | 26 | Hybrid 命中、LambdaMART 未命中 |
| kept_miss | 92 | 两种方式都未命中 |

新增 62、丢失 26，**净增 36 条**，对应 Recall@10 +8.57pp。**模型有效但不是无风险替换**——
生产设计需保护部分高置信度原始通道结果。

### 5.3 Balanced 420：分场景

| Query 场景 | n | 固定 Hybrid | LambdaMART | 变化 | 候选池覆盖率 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 长描述 / 多条件 | 105 | 54.29% | 70.48% | **+16.19pp** | 100.00% |
| 短关键词 | 105 | 60.00% | 69.52% | +9.52pp | 98.10% |
| 编号 / 日期 / 版本号 | 105 | 73.33% | 80.00% | +6.67pp | 100.00% |
| 自然语言改写 | 105 | 65.71% | 67.62% | +1.90pp | 98.10% |

原因分析：

- **长描述 / 多条件（提升最大）**：正确 Chunk 常在 Sparse/Dense 排名靠前，但固定 Hybrid 偏重 Dense、
  且无法利用两路共同命中；LambdaMART 学到 Sparse 排名、归一化分数与多路一致性。
- **短关键词**：语义信息少、Dense 易出现多个相似候选，模型靠 Sparse 精确信号与多路重合纠偏。
- **编号类**：本已较高（BM25/Sparse 擅长），但 BM25 固定权重仅 0.15；模型识别"BM25 排名靠前 + Query 含数字"组合，仍提升 6.67pp。
- **自然语言改写（提升最小）**：本就依赖 Dense，固定 Hybrid 已给 Dense 0.70，可纠正空间小；
  正确候选与语义相似干扰项结构化分数接近，仅靠排序特征难区分。后续可考虑更好的 Dense Embedding、
  独立新鲜的改写数据、对少量高歧义候选做文本 Rerank，或增加轻量语义交叉特征。

### 5.4 跨分布验证：旧 realistic Blind 116

为确认模型是否只对 balanced 构造方式有效，用 Balanced 420 训练模型（轮数固定 24，取自 5 折最佳轮数中位数），
在另一套未扩写的 `realistic_blind_scope_992003` 116 条 Query 上**一次性**评测。测试集不参与轮数选择、
特征设计或训练。

- 同候选缓存与参数口径下：Hybrid 44.83% → LambdaMART 50.86%，**+6.03pp**；候选池覆盖率 95.69%；
- 新增命中 14 条、丢失 7 条；
- MRR 从 16.98% 降到 14.48%（**-2.50pp**）——模型把更多正确 Chunk 推进 Top10，但部分仍排在较后位置。

排除 15 条与训练集共享正确 Chunk 的样本后（严格子集 101 条）：

| 指标 | 同口径 Hybrid | LambdaMART | 变化 |
| --- | ---: | ---: | ---: |
| Recall/Hit@10 | 43.56% | 50.50% | +6.93pp |
| MRR@10 | 15.94% | 13.93% | -2.02pp |

严格子集仍提升，说明 Recall 收益不是证据重叠造成；但 MRR 下降、`similar_docs` 场景从 56.25% 降到 50.00%，
进一步说明当前模型**不能直接生产替换**，需增加高置信度原始排名保护，并把训练目标从单一 NDCG 扩展为
同时约束 Recall@10、MRR 与原命中退化率。

### 5.5 数据扩展：1050 条严格集中间结果

用 Codex CLI 固定调用 `gpt-5.3-codex-spark` 生成储备 Query，每条配目标 Chunk 和 3 个同主题相似候选，
验证阶段随机打乱候选顺序、模型不知目标身份。配额耗尽前完成 1080 条盲审：648 条判定存在唯一完整证据，
去重后保留 630 条，与原 420 条合并成 1050 条严格集。

1050 条 5 折结果：

| 指标 | 固定 Hybrid | LambdaMART | 变化 |
| --- | ---: | ---: | ---: |
| Recall/Hit@10 | 42.57% | 48.38% | +5.81pp |
| MRR@10 | 18.79% | 22.82% | +4.03pp |

对旧 116 条未扩写 Query 的跨分布对比（用于观察扩数据是否提升泛化）：

| 训练数据 | Recall@10 | MRR@10 |
| --- | ---: | ---: |
| 420 条模型 | 50.86% | 14.48% |
| 1050 条模型 | 50.00% | 15.99% |

**中间结论**：扩数据后 MRR 改善，但外部 Recall 没有继续提高；多约束、关键词、数字时间场景受益，
相似文档和别名场景仍退化。后续不能只堆数量，需用盲审拒绝原因收缩宽泛 Query，并增加相似文档差异特征和
原始排名保护。

### 5.4 Hybrid Top1 保护优化

针对 1050 条模型外部 Recall 提升但 MRR 下降的问题，在 1050 条 5 折样本外预测上搜索
`LTR/Hybrid` 分数融合和 Hybrid TopK 保护。选参只使用 Tune OOF 预测，外部 116 条
不参与选参。

冻结配置为 `blend_alpha=1.0`，即保持 LambdaMART 排序分数；最终结果中强制保护
Hybrid Top1，其余位置按 LambdaMART 排序。

| 指标 | 固定 Hybrid | 原 1050 条 LambdaMART | Top1 保护后 | 相对 Hybrid 变化 |
| --- | ---: | ---: | ---: | ---: |
| 外部 Recall/Hit@10 | 44.83% | 50.00% | 50.00% | +5.17pp |
| 外部 MRR@10 | 16.98% | 15.99% | 18.80% | +1.82pp |
| 严格无证据重叠 Recall@10 | 43.30% | 47.42% | 47.42% | +4.12pp |
| 严格无证据重叠 MRR@10 | 16.27% | 15.43% | 18.08% | +1.81pp |

该保护没有牺牲外部 Recall，同时将 MRR 由负增长转为正增长，说明保留一个高置信度
Hybrid 候选能够修复部分头部排序退化。外部集仍然新增 13 条、丢失 7 条，且
`similar_docs` 和 `alias` 继续负增长，因此 Top1 保护是有效的第一阶段优化，
不是最终生产验收结论。

### 5.5 候选差异特征 v2

原 26 个特征主要描述三路分数、归一化分数和排名，模型看不到 Query 与候选正文之间的
具体差异。v2 从冻结 20k 语料为 19,988 个唯一候选导出正文 sidecar，并新增：

- 编号、日期、版本号及数字精确覆盖；
- 否定词一致性、多条件覆盖、Query 二元/三元词覆盖；
- Dense/Sparse/BM25 排名差、各路 Top1/Top2 分数间隔；
- 两路/三路共同召回；
- 候选池内差异 Query 词、同文档候选数量与正文相似度。

1050 条 Tune 继续采用 5 折 OOF 选参，冻结为 `blend_alpha=1.0`、
`protect_baseline_top_k=2`。116 条外部 Query 已被前序实验多次使用，本轮只作为回归集，
不再视为未触碰 Blind。

| 指标 | v1 Top1 保护 | v2 差异特征 | 变化 |
| --- | ---: | ---: | ---: |
| Tune OOF Hit@10 | 48.57% | 50.10% | +1.52pp |
| 外部 Hit@10 | 50.00% | 50.00% | 0.00pp |
| 外部 MRR@10 | 18.80% | 18.90% | +0.10pp |
| Alias Hit@10 | 41.38% | 44.83% | +3.45pp |
| Similar docs Hit@10 | 50.00% | 50.00% | 0.00pp |

结论是**局部有效、总体未证明继续提升**：`query_bigram_coverage` 成为新增特征中最重要的
信号，消除了 Alias 相对 Hybrid 的 3.45pp 下降；但 Similar docs 相对 Hybrid 56.25%
仍低 6.25pp。当前 20k 语料是一文档一 Chunk，同文档差异特征恒为零，不能为模型提供
有效监督。

这里尚未实现业务别名/同义词归一化。当前 `scenario_alias` 只是场景标签，字符 n-gram 覆盖也不是
可维护词表。后续候选方案是在 BM25/Sparse 查询前使用版本化、按业务域隔离的
`canonical -> aliases` 词表做受限扩展，同时保留原 Query、限制扩展数量并拒绝歧义别名；词表规则只能
在新的 Alias Tune 集上选择，冻结后再进入 Blind v4，不能根据 Blind v3 反推词条。

另行测试的 v2.1 加入候选池稀有 Query 词权重和 Top30 近邻相似度，Tune Hit@10 升至
50.86%，外部却降至 48.28%，Alias 降至 37.93%，属于过拟合，已拒绝进入最终实现。
后续若继续解决 Similar docs，应补充真实主题/文档族元数据和相似文档成组训练样本，再用
新的未触碰 Blind v2 验证，而不是继续添加无监督候选相似度。

---

## 6. 结论边界：为什么不能直接作为生产结论

1. 420 条训练/测试 Query 来自同一套 Tune 分布；
2. 当前 Blind 已被查看，不能再作无偏最终验收集；
3. 5 折训练了 5 个模型，尚未生成并冻结**单一**生产模型；
4. 当前提升同时包含"学习融合"与"重新利用固定阈值过滤候选"两部分贡献，未拆分；
5. 仍有 26 条原 Hybrid 命中发生退化；
6. 尚未完成生产延迟、模型文件版本管理与线上回退验证。

因此 71.90% 表示 Tune 样本外预测的实验结果，**不是生产流量承诺值**。

---

## 7. 生产落地建议

推进顺序：

1. 冻结候选深度、特征定义、LightGBM 参数与训练随机种子；
2. 固定已验证的 Hybrid Top1 保护，并继续分析 lost Query 的场景化保护规则；
3. 用全部 420 条 Tune Query 训练一个最终候选模型；
4. 生成与 Tune 来源隔离、未曝光的 **Blind v2**；
5. 在 Blind v2 上**只运行一次**固定 Hybrid 与 LambdaMART 对比；
6. 验收 Recall@10、MRR、分场景指标、退化率与推理延迟；
7. 先 Shadow 模式记录线上排序，不影响用户结果；
8. 过门禁后灰度启用，并保留固定 Hybrid 快速回退。

推荐上线结构：

```text
用户 Query
  -> Dense / Sparse / BM25 并行召回
  -> 候选去重和特征计算
  -> LambdaMART 排序
  -> 单路高置信度候选保护
  -> Top10
  -> 可选：只对高歧义 TopK 调用文本 Rerank
```

---

## 8. Query 扩展到 2000：已完成

最终训练集于 2026-07-18 完成。由于 GPT-5.3-Codex-Spark CLI 配额在处理中耗尽，按既定降级方案使用
`gpt-5.4-mini` 完成剩余生成、盲审和拒绝项窄化改写；每条候选仍经过打乱候选身份的独立完整证据判定。

| 项目 | 数量 |
| --- | ---: |
| 原始训练样本 | 420 |
| 已生成并独立判定的候选 Query | 2886 |
| 严格新增样本 | 1580 |
| 最终训练集 | 2000 |
| 判官判定无完整证据 | 746 |
| 因正证据 Chunk 重复丢弃 | 133 |
| 因 Query 重复丢弃 | 3 |

新增场景配额为：`similar_docs=600`、`multi_constraint=300`、`number_time=200`、`alias=160`、
`dense_paraphrase=140`、`short_keyword=100`、`exact_identifier=80`。最终 1580 条新增 Query 全部使用
单一 `expected_chunk_ids`，Query 唯一，新增正证据 Chunk 彼此唯一且不与原 420 条基集重叠。

原 420 条基集中已有 30 个证据 Chunk 被不同 Query 复用，因此全量 2000 条包含 1966 个唯一证据 Chunk；
报告已明确区分旧基集复用与本轮新增唯一性，避免把全量证据错误描述为完全唯一。

生成模型构成为 GPT-5.3-Codex-Spark 1850 条、GPT-5.4-Mini 1036 条；独立判定构成为
GPT-5.3-Codex-Spark 1080 条、GPT-5.4-Mini 1806 条。模型混用是配额降级，不改变同一套结构校验、
数字不得编造、同场景 Hard Negative 和完整证据判定门禁。

本节只确认训练数据构建完成。2000 条候选缓存、LambdaMART 重训、Tune OOF 选参和独立测试必须生成
新的阶段报告，不能沿用 1050 条模型结果冒充 2000 条模型效果。

### 8.1 2000 条模型重训与回归测试

2000 条数据完成后，按冻结候选深度 `Dense=150 / Sparse=50 / BM25=100` 重建候选缓存。
三路并集覆盖正确 Chunk 1905/2000，覆盖率 95.25%；剩余 95 条在候选生成阶段已经丢失，LambdaMART
无法通过排序找回。

5 折 Tune OOF 只用于训练与选择后处理参数，冻结结果为 `blend_alpha=1.0`、
`protect_baseline_top_k=1`：

| 指标 | 固定 Hybrid | 2000 条 LambdaMART | 变化 |
| --- | ---: | ---: | ---: |
| Tune OOF Recall@10 | 35.90% | 43.55% | +7.65pp |
| Tune OOF MRR@10 | 15.85% | 17.96% | +2.11pp |

在已被历史实验复用的 116 条外部回归集上：

| 指标 | 固定 Hybrid | 2000 条 LambdaMART | 变化 |
| --- | ---: | ---: | ---: |
| Recall@10 | 44.83% | 48.28% | +3.45pp |
| MRR@10 | 16.98% | 18.37% | +1.40pp |
| 无训练证据重叠 Recall@10（n=88） | 40.91% | 44.32% | +3.41pp |

1050 条 v2 模型在同一外部回归集为 50.00%，2000 条模型为 48.28%。逐题比较有 8 条发生变化：
2000 条模型新增命中 3 条、丢失 5 条，净少 2 条；双侧精确检验 `p=0.727`，样本量不足以证明
真实退化。因此正确结论是：**2000 条模型仍优于固定 Hybrid，但尚未证明优于 1050 条模型**。

主要风险仍是 `similar_docs`：外部 16 条由 Hybrid 56.25% 降至 LambdaMART 43.75%；
`number_time` 则由 32.00% 升至 44.00%，`alias` 由 44.83% 升至 48.28%。后续应保留 2000 条
训练数据，但增加相似文档成组差异监督或场景保护，并使用新的未触碰 Blind 做最终判断，不能继续根据
这 116 条回归集反复调参。

### 8.2 全新 Blind v2：历史 Query 与正标签隔离

为消除旧 116 条回归集已被反复查看的问题，重新冻结 Blind v2。构建前扫描历史阶段产物，记录
4225 条历史 Query 和 3041 个曾作为训练或测试正标签的 Chunk。新集执行以下门禁：

- Query 与历史 Query 文本重叠为 0；
- 正证据 Chunk 与训练及历史测试正标签重叠为 0；
- 每条只有一个 `expected_chunk_ids`，正证据和 Query 均唯一；
- 七类各 30 条，共 210 条；
- 603 条储备 Query 均经过四候选顺序打乱的独立完整证据判定；
- 模型参数在查看 Blind v2 结果前冻结，Blind 结果不参与调参。

严格边界：LTR 训练候选池覆盖接近完整 20k 语料，因此新正证据正文可能曾作为**负候选**进入特征训练。
这里的“未曝光”严格表示 Query 和正标签未曝光，而不是 Chunk 正文从未作为任何候选出现。该集按同主题
Hard Negative 平衡生成，属于高难 Blind，不代表自然线上流量分布。

冻结测试结果：

| 模型 | 命中 | Recall@10 | MRR@10 | 相对 Hybrid |
| --- | ---: | ---: | ---: | ---: |
| 固定 Hybrid | 44/210 | 20.95% | 5.91% | - |
| 1050 条 LambdaMART（Top2 保护） | 58/210 | 27.62% | 7.13% | +6.67pp |
| 2000 条 LambdaMART（Top1 保护） | 58/210 | 27.62% | 8.46% | +6.67pp |

1050 与 2000 模型 Top10 命中数完全相同。2000 相对 1050 新增命中 10 条，同时丢失 10 条；MRR
提高 1.33pp。新 Blind 因此不支持“1050 条训练集质量更好”的判断，也没有证明 2000 条训练能提高
Top10 总命中数。它证明两种 LambdaMART 均比固定 Hybrid 多命中 14 条，但模型收益被以下问题限制：

- 正确 Chunk 的三路候选并集覆盖率只有 89.05%，先天丢失 23 条；
- `short_keyword` 候选覆盖仅 63.33%，Hybrid Recall 为 0；
- 2000 模型改善 Dense 改写、Alias、精确编号和短关键词，但在多约束、数字时间和相似文档上抵消收益；
- 后续应优先优化候选覆盖、相似文档差异监督和场景保护，而不是继续只增加训练条数。

### 8.3 候选分流重训与未曝光 Blind v3 最终验收

Blind v2 审计后，先修正 4 条引入无证据“24 小时”条件的 Query，并将所有不满足严格文本门禁的
`exact_identifier` 标签降级到实际运行时场景；Tune 共修正 185 条场景标签，Blind v2 共修正 33 条。
构建脚本现在要求编号场景文本必须真实包含 ID、日期或版本号。

随后只用修复后的 2,000 Tune 搜索并冻结 Query 候选深度，重建完整缓存。候选并集覆盖从原始
95.25% 提升到 98.55%，实际去重候选数均值 278.56。五折 Tune OOF 冻结参数为
`n_estimators=31`、`learning_rate=0.03`、`blend_alpha=1.0`、`protect_baseline_top_k=0`：

| 指标 | 分流 Hybrid | LambdaMART | 变化 |
| --- | ---: | ---: | ---: |
| Tune OOF Recall@10 | 35.75% | 44.90% | **+9.15pp** |
| Tune OOF MRR@10 | 15.86% | 19.52% | +3.67pp |

Blind v3 在参数冻结后构建和评测。它扫描历史产物建立曝光清单，Query 与正证据历史重叠均为 0；
四候选随机打乱后由 GPT-5.3-Codex-Spark 优先、GPT-5.4-Mini 降级做独立完整证据判定，最终冻结
五个场景各 30 条，共 150 条。候选缓存 150/150 成功，只运行一次冻结模型：

| 场景 | 候选覆盖 | Hybrid Recall@10 | LambdaMART Recall@10 | 变化 |
| --- | ---: | ---: | ---: | ---: |
| 全部 | 92.67% | 22.67% | 30.67% | **+8.00pp** |
| 相似文档 | 100.00% | 30.00% | 53.33% | **+23.33pp** |
| 多条件 | 93.33% | 46.67% | 60.00% | **+13.33pp** |
| 别名 | 96.67% | 10.00% | 16.67% | +6.67pp |
| 自然语言改写 | 93.33% | 20.00% | 20.00% | 0.00pp |
| 短关键词 | 80.00% | 6.67% | 3.33% | **-3.33pp** |

新增命中 16 条、丢失 4 条，净增 12 条。该结果证明 LambdaMART 收益可以跨到未曝光 Query 和证据，
但也明确拒绝“已经生产达标”的结论：绝对 Recall@10 仍低，短关键词需要回退 Hybrid。当前 20k 语料
没有可构造严格编号、日期、版本号题目的未曝光证据，Blind v3 没有伪造这两个场景；后续必须先补
eval-only 语料，再建立独立子集验证。

### 8.4 Cross Encoder 作为 LambdaMART 特征（历史失败实验）

为避免重现 qwen3-rerank 直接覆盖三路排序的负增长，本轮只把 `qwen3-rerank` 分数作为附加特征：

```text
旧 LambdaMART 无泄漏初排 TopK
  -> qwen3-rerank 为 TopK 候选打分
  -> 原始分 / query 内归一化分 / 倒数排名 / 未打分标记
  -> 新 LambdaMART 与原三路特征共同排序
```

Tune 的 shortlist 使用旧模型 OOF 分数生成，确保每条 Query 都由未训练过该题的基础模型选择 TopK；
Cross Encoder 不读取标签。Blind v3 shortlist 使用全部 Tune 训练的旧模型生成，Blind 标签仍不参与选择。

| 方案 | Tune OOF Recall@10 | 相对原 LTR | Blind v3 Recall@10 | 相对原 LTR | 决策 |
| --- | ---: | ---: | ---: | ---: | --- |
| 原 `candidate_difference_v2` | 44.90% | - | 30.67% | - | 保持默认 |
| Cross Encoder Top50 | 45.60% | +0.70pp | 30.00% | -0.67pp | 拒绝默认启用 |
| Cross Encoder Top80 | 46.05% | +1.15pp | 未完成 | - | 已取消，不再验证 |

Top50 的旧 LTR shortlist 对正确 Chunk 的覆盖率在 Tune 为 79.20%，Blind v3 只有 59.33%；其余候选没有
Cross Encoder 分数。单独按 qwen3-rerank 分数取 Top10 时，Tune 仅 32.25%，Blind v3 仅 22.67%，
说明通用文本相关度本身不强。作为特征后，Blind v3 的别名和短词提高，但自然语言改写与相似文档下降，
总体净少 1 条命中。

Top80 将基础 shortlist 目标覆盖提高到 Tune 86.85%，Tune OOF 达到 46.05%，但 Blind v3 请求阶段百炼返回
`Arrearage`，150 条全部失败。此后又在相同固定 Top50 候选上完成 `qwen3-vl-rerank` 150 条批量对照：
`qwen3-vl-rerank` Recall@10 为 24.00%，只比 `qwen3-rerank` 的 22.67% 多 2 条命中，配对检验
`p=0.856`，且仍低于原 LambdaMART 的 30.67%。这不足以证明重排模型具有稳定净收益。

2026-07-21 最终决策：**终止直接 Rerank 与 Cross Encoder 附加特征路线，不再补跑 Top80。**
历史报告和结果继续保留用于解释失败原因；活动代码删除 Cross Encoder 分数缓存入口、LTR v3 特征和相关
CLI 参数。LambdaMART 的训练与推理统一固定为 `candidate_difference_v2`，因此不依赖用户是否选择重排模型。

---

## 9. 相关实现与报告

**实现代码**

- LambdaMART 交叉验证与外部评测：`src/linkrag_eval/retrieval/learning_to_rank/experiment.py`
- 候选缓存：`src/linkrag_eval/retrieval/learning_to_rank/cache.py`
- 单元测试：`tests/unit/test_ltr_experiment.py`

**LambdaMART 报告**（`runs/golden_v2/scale_100k_991004/scale_20k_overnight/` 下）

- 420 条 5 折：`balanced_query_expansion/balanced_final_600/ltr_fusion_v1/cv_v1/ltr_cross_validation.{html,json}`
- 420 条候选缓存：`balanced_query_expansion/balanced_final_600/ltr_fusion_v1/tune_candidates_420.jsonl`
- 跨分布 116（420 模型）：`balanced_query_expansion/balanced_final_600/ltr_fusion_v1/external_realistic_blind_116/evaluation/ltr_external_evaluation.{html,json}`
- 1050 条 5 折：`ltr_query_expansion_2000/ltr_partial_1050/cv/ltr_cross_validation.{html,json}`
- 1050 条跨分布 116：`ltr_query_expansion_2000/ltr_partial_1050/external_realistic_blind_116/ltr_external_evaluation.{html,json}`
- 1050 条 Hybrid Top1 保护优化：`ltr_query_expansion_2000/ltr_partial_1050/hybrid_protection_v1/optimization_summary.{html,json}`
- 1050 条候选差异特征最终复跑：`ltr_query_expansion_2000/ltr_partial_1050/candidate_features_v2_final/optimization_summary.{html,json}`
- v1/v2/v2.1 对比：`ltr_query_expansion_2000/ltr_partial_1050/candidate_features_v2_final/candidate_feature_comparison.{html,json}`
- 被拒绝的 v2.1 过拟合实验：`ltr_query_expansion_2000/ltr_partial_1050/candidate_features_v2_1/optimization_summary.{html,json}`
- 2000 条训练集完成与质量门禁：`ltr_query_expansion_2000/final_2000/training_set_2000_completion_report.{html,json}`
- 2000 条最终训练数据：`ltr_query_expansion_2000/final_2000/expanded_tune_2000.jsonl`
- 2000 条候选缓存与模型测试：`ltr_query_expansion_2000/final_2000/ltr_evaluation_v1/ltr_2000_evaluation_report.{html,json}`
- 全新 Blind v2 冻结测试：`ltr_query_expansion_2000/final_2000/blind_v2_20260718/blind_v2_evaluation_report.{html,json}`
- 候选分流与 Blind v3 最终验收：`ltr_query_expansion_2000/final_2000/candidate_routing_ltr_v3_20260720/candidate_routing_ltr_final_acceptance_report.{html,json}`
- Blind v3 单次外部评测：`ltr_query_expansion_2000/final_2000/candidate_routing_ltr_v3_20260720/blind_v3/evaluation/model_frozen_once/ltr_external_evaluation.{html,json}`
- Cross Encoder 特征实验：`ltr_query_expansion_2000/final_2000/candidate_routing_ltr_v3_20260720/cross_encoder_feature_v1/cross_encoder_ltr_experiment_report.{html,json}`
- qwen3-vl-rerank 150 条固定 Top50 对照：`ltr_query_expansion_2000/final_2000/candidate_routing_ltr_v3_20260720/qwen3_vl_rerank_batch_150_20260721/batch_comparison.{html,json}`

**对照方案报告**（同上目录前缀）

- qwen3-rerank Tune Top20/40/60/80：`rerank_qwen3/tune_top20_40_60_80_final.json`
- qwen3-rerank Blind Top20：`rerank_qwen3/blind_top20_final.json`
- qwen3-rerank Top60 Clean 复测：`rerank_qwen3/tune_top60_clean_retest_20260717.{html,json}`
- Query 重写无失败成对：`query_rewrite_benchmark_v1/pair_eval_smoke_40_reasoner_v2_retry5/query_rewrite_pair_report.html`
- Query 重写消融：`query_rewrite_benchmark_v1/pair_eval_smoke_40_rewrite_only_ablation/query_rewrite_pair_report.html`
- Query 重写原始 Top5 保护：`query_rewrite_benchmark_v1/pair_eval_smoke_40_rewrite_only_protect5/query_rewrite_pair_report.html`
- 20k Hybrid 与分场景基线：`retrieval_routing_analysis_report.html`
