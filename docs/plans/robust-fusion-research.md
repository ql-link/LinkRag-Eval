# 高相似度干扰下检索增强生成的多路来源感知鲁棒融合方法研究

> 文档定位：本文件是科研协议，负责冻结研究问题、构念、证据、实验设计、方法边界和决策门禁；环境、存储、快照和实验器实现在[工程实施协议](robust-fusion-engineering.md)维护，日常任务在[研究推进清单](robust-fusion-todo.md)维护，目标渠道与版本规则在[发表路径与投稿治理](robust-fusion-publication.md)维护。
> 研究记录：ROBUST-FUSION-RESEARCH-2026-08-28-v19。
> 当前阶段：P2 构念、标注与指标效度；尚未进入 Gate A，也尚未开发论文方法 M1。
> 证据入口：[定向文献地图](robust-fusion-literature.md)、[主张—证据—空缺表](robust-fusion-evidence.md)、[本地论文全文](../papers/)。
> 最近更新：2026-08-28。

## 0. 一页摘要

### 0.1 研究究竟要回答什么

本研究不比较“LambdaMART 和 Reranker 谁普遍更好”。它研究一个更窄、也更可检验的问题：

> 当候选池中出现大量主题和措辞高度相似、但版本、数字、否定或适用条件错误的 Chunk 时，语义 Reranker 是否更容易把错误候选排到前面；Dense、Learned Sparse、BM25 的分路分数和排名证据，结合少量局部相似邻居中的可观测冲突，能否在不重训 Reranker 的情况下减少这种退化？

论文只研究候选融合与排序，不把生成答案质量作为主终点。

### 0.2 最短逻辑链

1. 高相似候选可能是正确的等价证据，也可能是事实冲突的错误证据，因此“相似”本身不是风险结论。
2. 在固定候选池中，用事实等价作为对照、事实冲突作为处理，才能判断额外伤害是否来自事实关系。
3. 若两个独立 Reranker、至少两个数据集都出现稳定退化，且推理期可见的冲突代理确实测到了人工确认的冲突，Gate A 才通过。
4. Gate A 通过后，才在现有 LTR-v3 上增加 Top-M 局部冲突风险和分路局部 Margin，形成唯一新方法 M1。
5. M1 必须在未参与开发的数据上通过完整的 11 项 nAUDC 基线家族；其中 LTR-v3、无类型邻域 D3 和表面特征 A0 还必须达到实际效应界，Top1 翻转与 Clean 也必须非劣，Gate B 才支持方法贡献。

> **概念解释｜Gate A 与 Gate B**：Gate A 是独立的现象与测量研究，回答“问题是否真实存在、测量是否可信”；Gate B 是方法确证研究，回答“冻结后的新方法是否比强基线更稳健”。Gate A 不是软件测试，Gate B 也不是调参集。

### 0.3 一个主要科学贡献、一个诊断贡献和一个条件性方法贡献

| 角色 | 内容 | 成立条件 |
| --- | --- | --- |
| 主要科学贡献 C1 | 等价对照下的事实冲突特异性退化测量 | 连续交互、匹配高相似差分和跨模型/数据集重复同时通过 Gate A |
| 诊断贡献 C2 | 可检测、条件可裁决、不可识别三分边界 | 推理期可见代理在 held-out 自然冲突上具有增量效度；不可识别时保持 LTR-v3 顺序 |
| 条件性方法贡献 C3 | 局部冲突风险条件化的检索路感知融合 | 仅在 Gate A = Go 后开发；完整 11 项 nAUDC 家族通过，且 M1 相对 LTR-v3、容量匹配 D3 与表面特征 A0 达到冻结的实际增量 |

C1 是论文最低可独立成立的主要贡献；C3 是条件性次要贡献。M1 失败不能倒推 C1 失败，但 C1 未通过时不得继续开发 M1。

完整候选图、图神经网络、聚类拓扑、学习门控、强化学习干扰生成和重训大型 Reranker 均不属于本论文。

### 0.4 科研协议与工程协议的关系

真实环境已经解除“无法取得真实三路证据”的工程阻塞，但它没有自动提供 Gate A 所需的 Query、qrels、等价组和三分研究样本。

本文件只维护科学含义：什么是处理与对照、什么能够支持 RQ、何时通过 Gate。具体环境、资产覆盖、存储护栏、候选快照 schema、离线实验器、重放和验收统一由[工程实施协议](robust-fusion-engineering.md)维护。

两份协议共同遵守一条边界：工程测试证明研究仪器是否可信，Gate A/Gate B 才决定科学主张是否成立。

## 1. 题目、术语和研究边界

### 1.1 正式题目

中文：

**高相似度干扰下检索增强生成的多路来源感知鲁棒融合方法研究**

英文：

**Beyond Semantic Reranking: Retrieval-Route-Aware Robust Fusion under Similarity Crowding in RAG**

### 1.2 “多路来源感知”的严格含义

“来源”只表示候选来自哪一条检索路：

- Dense；
- Learned Sparse；
- BM25。

当前真实工程口径固定为：Dense 使用 `text-embedding-v4` 在线 API，Learned Sparse 使用火山方舟 `ark / doubao-embedding-vision-251215` 在线 API，BM25 使用 eval 自持 SQLite FTS5。BGE-M3 已由研究负责人淘汰，只能解释历史 Alt Embedding 资产；它不得进入当前 Gate A 的三路、实验相似度或独立相似性审计。

候选级来源证据包括 retrieved flag、原始分数、冻结归一化分数、原始排名、路间重合和路间差异。它不表示网页作者、机构权威性、引用出处可信度或文档 provenance。

> **概念解释｜Retriever 与检索路**：Retriever 是从语料中寻找候选的检索器。一个 Query 同时交给 Dense、Learned Sparse 和 BM25，就形成三条检索路。本文的“来源感知”是保留这三路各自的证据，而不是评价信息发布者是否权威。

### 1.3 研究对象

研究对象固定为：

- 三路召回后的候选并集；
- 固定候选池内的融合与排序；
- 高相似事实冲突对排序结果的影响；
- 不重训语义 Reranker 的低成本融合增量。

研究对象不包括：

- 生成答案质量；
- 文档权威性识别；
- 上游编码器训练；
- 生产流量在线 A/B；
- 提示注入、防越狱等安全攻击；
- 通用知识图谱或候选图建模。

> **概念解释｜召回、融合与重排**：召回负责尽量找全候选；融合把多条检索路的列表合并；重排在较小候选池中重新决定顺序。本文主要研究融合与重排，因此 Gold 根本没有进入候选池时，属于上游召回问题，不算排序方法失败。

### 1.4 结论边界

固定候选池实验只能支持“冻结上游证据后的排序阶段直接效应”。语料重新入索引实验才能补充端到端外部有效性。二者不能混成同一种因果结论。

> **概念解释｜内部有效性与外部有效性**：内部有效性关心观察到的差异能否归因于被操纵因素；外部有效性关心结论能否延伸到真实语料和完整系统。固定候选池更利于前者，重新入索引更接近后者。

## 2. 已有证据、研究空缺与创新边界

### 2.1 历史项目结果与分享包：研究起点，不是确认性分母

现有 LinkRag-Eval 结果曾观察到：

- 某些候选分布下，qwen3-rerank 相对固定融合明显退化；
- 历史 Blind v3 中，LTR 相对固定融合出现正向增量；
- 把 Reranker 分数加入 LTR 后，Tune 与 Blind 方向不一致；
- Blind v4、Blind v5 的整体增量与真实搜索子集增量不一致。

这些结果证明“值得研究”，不证明新论文的方法有效。不得将不同数据、不同指标的变化合并为“普遍提升约 7%”。

`linkrag-eval-sqlite-share-20260827` 是本研究想法的正式经验与工程起点，而不是可忽略的历史备份。它与 `.env.eval` 指向的旧 eval MySQL、当前 Qdrant、BM25 和 Alt Embedding 已完成只读对账，因而有三类可复核价值：历史观察为研究问题提供假设来源；真实三路与 LTR-v3 资产证明研究可实施并帮助估算预算；经逐集验证的 ID/provenance、索引覆盖和运行指纹可作为候选重建底座。

这项重要性不改变证据等级：分享包和旧 eval MySQL 都是 `eval_query=0`、`eval_qrel=0`，历史 Blind 又已曝光，所以其中 51 个 run、2,884 条聚合指标、旧向量或 dataset 名称均不能直接成为 C1/C2/C3 的确认性证据。准确表述固定为“研究问题的经验起点与工程底座，不是 Gate A/B 分母”。

> **概念解释｜研究动机与确认性证据**：研究动机用于提出问题；确认性证据用于支撑论文结论。已经看过并参与过工程决策的数据只能作为动机，不能再假装成未曝光验证。

### 2.2 LTR-v3 已占据的创新空间

现有 candidate_difference_v3 已包含 38 维线上特征：

- 三路原始/归一化分数、排名和缺失标记；
- 共同召回、路间排名差、Top1—Top2 间隔；
- 编号、数字、否定、条件覆盖；
- 同文档候选数量、同文档相似度和文本长度。

因此下列内容都不是新创新：

- 用 LambdaMART 融合 Dense、Sparse、BM25；
- 保留多路分数和排名；
- 使用编号、数字、否定或条件匹配；
- 使用普通 Top1—Top2 margin；
- 根据固定融合结果做简单保护。

论文新方法必须增加“局部高相似邻域中的事实冲突风险”和“候选相对疑似冲突近邻的分路 Margin”，并相对 LTR-v3、容量匹配的无类型局部对照 D3 和表面信息对照 A0 做 Blind 增量验证。

> **概念解释｜基线与创新增量**：基线是新方法必须比较的现有方法。项目已经拥有强基线 LTR-v3，所以论文不能把 v3 已经会做的事情重新命名为创新。

### 2.3 文献证据链

| 已有研究说明了什么 | 代表证据 | 仍未回答什么 |
| --- | --- | --- |
| 语义 Reranker 在相似候选中可能条件性失效 | Hagström et al. (2025) | 事实关系、剂量和多路缓解 |
| 矛盾事实与重复事实可能保持近似的向量相似度 | Temporal Validity in Retrieval Memory (2026) | 静态固定候选池中的 Reranker 排序效应 |
| 语义重排可能偏爱主题相近但证据无效的候选 | FinSAgent (2026) | 等价对照、受控交互和跨数据集因果隔离 |
| 高相似可能是等价冗余，也可能是相反标签 | RARE；Regulatory DOC2DOC | 统一的等价/冲突受控对照 |
| 多路融合可能互补，也可能被弱路拖累 | Balancing the Blend；Fusion Functions | 事实冲突环境下哪一路保留判别力 |
| 候选邻域、协作关系和 margin 已有先例 | HybRank；MoR；QuDAR | 类型化局部冲突是否有独立增量 |
| 多 Retriever Hard Negative 可用于重训 Ranker | R²ANKER；HYRR | 冻结 Reranker 时，融合层能否保护排序 |

完整证据和措辞边界见[主张—证据—空缺表](robust-fusion-evidence.md)。

### 2.4 可辩护的研究空缺

截至当前定向检索，已有工作已经观察到“矛盾事实仍可高度相似”和“语义重排偏爱主题相近但证据无效候选”。因此，本文不把发现这一一般现象本身作为新颖性。可独立辩护的空缺收束为：

1. **测量贡献 C1**：在固定候选池中，以同样相似的事实等价候选作为良性对照，估计相似度与事实冲突的额外交互伤害；
2. **诊断贡献 C2**：把局部分歧划分为可检测、条件可裁决和不可识别，并在 held-out 自然冲突上验证边界；
3. **条件性方法贡献 C3**：若 C1/C2 成立，再检验推理期局部冲突与检索路相对优势能否在 LTR-v3、容量匹配 D3 和表面特征对照 A0 之外保护排序。

论文引言按以下七步展开：

1. 语义 Reranker 的收益依赖候选分布；
2. 文本相似性不能替代版本、数字、否定和适用条件；
3. 高相似等价证据与高相似冲突证据必须分开；
4. 多路检索提供互补证据，但弱路也可能污染融合；
5. 时间有效性和金融问答中的近邻工作已经独立观察到相似度与证据有效性分离；
6. 候选上下文、margin、动态融合和多路难负例训练已有先例；
7. 本文只检验冻结候选池下的等价—冲突交互、可识别性边界，以及条件性局部冲突融合。

“首次发现语义 Reranker 会被相似候选误导”“首次发现矛盾事实仍然高度相似”“首次使用多路分数”“首次使用候选邻域”均禁止写入论文。新颖性不得依靠堆叠一长串设计条件证明，而必须分别由 C1、C2 和条件性 C3 的独立证据承担。

## 3. 研究问题与可证伪假设

### 3.1 RQ1：退化现象

对每个给定候选快照，候选 ID、正文和三路证据在排序方法之间完全相同；跨 Clean/Stress 和剂量条件时，压力候选替换普通负例并携带真实重算的三路证据，因此候选内容与证据允许按预注册干预变化。在保持池大小、目标等价组、组级 gain 和 IDCG 不变时，事实冲突候选的数量和相似度升高，是否使两个独立语义 Reranker 的 EG-nDCG、EG-MRR、Top1 正确性和目标组最佳排名稳定退化；该伤害是否大于等量事实等价候选造成的影响？

### 3.2 RQ2：退化机制与测量

退化是由普通相似密度、重复占位、版本/数字/否定/条件冲突，还是检索路局部判别差异驱动？只使用 Query、Chunk 正文和三路证据形成的可观测冲突代理，能否在未见数据上区分事实冲突与良性冗余？

### 3.3 RQ3：鲁棒融合

局部冲突风险条件化的检索路融合，能否相对固定融合、RRF、两个语义 Reranker、LTR-v3、普通局部去重、硬约束、D1—D3 以及表面特征对照 A0，降低退化曲线面积，同时不实质增加 Top1 错误翻转并保持 Clean 非劣？

### 3.4 假设

- **H1：密度不充分。** 高相似密度本身不能区分良性等价冗余和有害事实冲突。
- **H2：相似度与事实关系存在交互。** 相似度升高时，事实冲突条件的排序伤害比事实等价条件增长更快。
- **H3：可观测局部冲突代理有效。** 不读取 qrels 或人工场景标签的代理，能够在独立审计集上识别冲突。
- **H4：类型化检索路增量成立。** M1 相对 LTR-v3、D1—D3、A0 和简单策略具有样本外增量，且不是靠伤害 Clean 换取 Stress 收益。

若 RQ1/RQ2 的必要条件未通过，停止 M1 开发。若 Gate A 通过但 H4 未通过，论文收缩为退化机制与评测研究。

> **概念解释｜可证伪假设**：研究必须预先说明什么结果会推翻主张。若无论结果怎样都能解释为成功，就不构成科学检验。

## 4. 核心构念与测量规则

### 4.1 实验中的“相似”

每个确认性压力候选必须锚定唯一目标等价组 \(g\)。设 \(A_{qg}\) 为 Query \(q\) 在 Clean 池中属于目标组 \(g\) 的正确参照 Chunk 集，冻结编码器表示为 \(z(c)\)，则待测候选 \(c\) 的实验相似度为：

\[
S_{qg}(c)=\max_{h\in A_{qg}}\cos(z(c),z(h))
\]

它测量“候选有多像它所针对的正确证据”，不是 Query—Chunk 相似度，也不是 M1 的候选—近邻相似度。

主检验使用连续相似度，不依赖单个高/低阈值。低相似和高相似只用于预注册的 2×2 直观复核，规则为：

1. 使用同一冻结编码器和相同文本预处理；
2. 先限制为同主题、同实体或同事实族的合格候选；
3. 在每个数据源的 Dev 上合并等价与冲突候选计算相似度分布；
4. 等价与冲突共用同一组数据源内分带边界；
5. 中间区域作为模糊带，只进入连续分析；
6. 用独立编码器和盲人工量表审计分带；
7. 若最高分带仍不构成明显近邻，该数据源不进入高相似确认性结论。

这是一套可重复的操作标准，不是学界通用的绝对余弦阈值。

> **概念解释｜连续变量与分带**：连续变量保留每个相似度数值的信息；分带把数值划成低、高等组，便于解释但会损失信息。因此本文以连续交互为主，分带只作预注册复核。

> **概念解释｜共同支持区间**：等价候选和冲突候选必须在一段相似度范围内都真实存在，才能比较事实关系。若一类只在低端、另一类只在高端，就无法分清伤害来自相似度还是事实关系。

### 4.2 事实关系、等价组与可裁决性

Query—Chunk 不再用一个四值字段同时表示“是否相关”“与目标事实是什么关系”和“方法能否判断”。确认性数据固定使用下列正交字段；公开 qrel 原值另存且永不覆盖，人工判断作为带证据定位和手册版本的独立 adjudication layer。

#### 4.2.1 来源相关性层：`relevance_status`

| 标签 | 含义 | 是否进入确认性分析 |
| --- | --- | --- |
| `relevant_gold` | 数据集语义允许且经本研究复核的原始正确证据 | 是 |
| `relevant_equivalent` | 能替代目标组中 Gold、支持同一事实且不改变答案的正确证据 | 是 |
| `verified_incorrect_distractor` | 已有可定位证据确认不满足 Query 的候选 | 是；还须由 `target_relation` 区分冲突与普通错误 |
| `unresolved_possible_false_negative` | qrels 未判定、证据不足或无法排除漏标相关 | 否 |

公开 qrels 中没有出现的候选默认是 unjudged，不能自动映射为 `verified_incorrect_distractor`。`relevant_gold` 也不能仅凭字段名推断：必须符合该数据集 qrel 的官方语义，并在版本、条件或专业正确性可能变化时完成本研究复核。

#### 4.2.2 目标事实关系层：`target_relation`

| 标签 | 操作定义 | 与 `relevance_status` 的合法组合 |
| --- | --- | --- |
| `equivalent` | 对同一实体、事实槽、时间和适用范围给出相同或相容答案，可替代目标等价组成员 | `relevant_gold` / `relevant_equivalent` |
| `factual_conflict` | 针对同一事实槽与可比范围，给出与目标组不相容的值、方向、版本或条件 | `verified_incorrect_distractor` |
| `other_incorrect` | 不满足 Query，但错误来自跑题、信息不足、实体错配或普通无关，而非目标事实冲突 | `verified_incorrect_distractor` |
| `unresolved` | 现有证据不能排除等价、相关或事实冲突中的任一解释 | `unresolved_possible_false_negative` |

`factual_conflict` 还必须且只能标一个主 `conflict_type`：`version_or_time`、`numeric`、`negation_or_direction`、`applicability_or_condition`。一次合成变换只能改变一个事实单元；自然候选若同时含多种冲突，不进入四类原子确认性链，可留作探索性多标签样本。

近重复、同文档、同模板、高余弦相似或“看起来像 Hard Negative”只记录构造属性，不能单独证明 `factual_conflict`。事实等价候选继承既有 `target_equivalence_group_id`，不新建额外 gain。

#### 4.2.3 方法可裁决性层：`adjudicability`

该字段只对 `target_relation=factual_conflict` 生效；其他关系固定为 `not_applicable`。

| 标签 | `method_view` 下的操作定义 | 方法行为边界 |
| --- | --- | --- |
| `detectable_only` | 可从候选文本及允许元数据稳定发现同槽分歧，但 Query/候选没有足够信号选择正确成员 | 可报告冲突风险，不得声称已裁决真值 |
| `conditionally_adjudicable` | Query 的显式版本、时间、数值、方向或适用条件与候选证据足以按冻结规则选择正确成员 | 可进入 C2 正确成员裁决任务 |
| `unidentifiable` | evaluation view 已知真值，但 method view 连冲突存在或正确侧都无法可靠识别 | 作为 C2 边界样本；M1 必须保持 LTR-v3 顺序 |
| `not_applicable` | 候选不是已确认的目标事实冲突 | 不进入裁决任务 |

“真值未知”和“方法不可识别”不得混用：前者使用 `target_relation=unresolved` 并排除确认性分析；后者的评价真值已知，是 C2 的有效边界证据。

#### 4.2.4 候选对关系：`candidate_pair_relation`

该字段只服务 Top-M 成对冲突代理的效度审计，不替代候选级 `target_relation`，也不直接作为 M1 输入。

| 标签 | 操作定义 |
| --- | --- |
| `same_fact` | 两候选对同一事实槽、实体、时间和条件给出相同或相容陈述；两者都错的错误共识也属于此类 |
| `factual_conflict` | 两候选针对同一事实槽与可比范围给出互不相容陈述；该标签本身不判断哪一方正确 |
| `insufficient_context` | 可确认缺少实体、时间、条件或指代上下文，因而不能把表面差异判为同事实冲突 |
| `unresolved` | 按手册完成证据查找与仲裁后仍不能稳定落入前三类 |

人工层至少另存 `source_qrel`、`adjudicated_status`、`evidence_locator`、`rationale`、`reviewer_id`、`confidence`、`adjudication_status` 和 `handbook_version`。`confidence` 只描述把握度，不能把 unresolved 强行升级为可确认标签。

> **概念解释｜Gold、qrels 与等价组**：Gold 是确认正确的证据；qrels 是 Query 与 Chunk 的相关性标签表；等价组把支持同一事实的可替代 Chunk 归为一组。评价时同一组最多奖励一次，避免重复文本机械抬高分数。

> **概念解释｜Hard Negative 与 False Negative**：Hard Negative 是主题很像但关键事实不满足 Query 的困难负例；False Negative 是实际上相关却被误标为负例。越相似的候选越需要审计后者。

### 4.3 推理期可观测代理

M1 不读取人工关系标签，而从 Query、Chunk 和三路快照中计算：

1. Query 显式约束错配：版本/时间、数字、否定、条件；
2. Top-M 邻居的平均/最大相似度和有效邻居比例；
3. 候选与邻居之间可抽取的约束冲突；
4. 每条检索路上，候选相对疑似冲突邻居的分数和排名优势；
5. 每项覆盖率和 unknown 标记。

只观察每个候选最相似的少量邻居：

\[
N_M(i)=TopM\{c_j:sim(c_i,c_j)\ge\tau\}
\]

候选的局部冲突风险为：

\[
LocalConflictRisk(c_i)=
\frac{1}{M}\sum_{j\in N_M(i)}
sim(c_i,c_j)
\left[
\lambda\hat{\chi}_{ij}+(1-\lambda)\frac{\hat m_i+\hat m_j}{2}
\right]
\]

其中 \(\hat{\chi}_{ij}\) 表示可观测的候选对约束冲突，\(\hat m_i\) 表示 Query 显式约束与候选的错配。Query 未提供正确值的“待回答槽”只能判断候选之间有分歧，不能判断谁正确，必须记为 unknown。

每条检索路 \(r\) 的冲突条件化分数 Margin 为：

\[
Margin_r(c_i)=
\tilde s_r(c_i)-
\max_{c_j\in N_{conf}(i)\cap C_r}\tilde s_r(c_j)
\]

排名 Margin 使用同样定义，把归一化分数替换为倒数排名。Dense、Sparse、BM25 六个 score/rank Margin 分别保留，不先求和。

Top-M 默认只在 \(\{5,10\}\) 中选择；\(\tau\)、冲突阈值、\(\lambda\)、归一化和缺失编码全部只在 Dev/Tune 冻结。相似矩阵按 Query 即算即弃，不建立持久化图，不训练图模型，不调用成对 LLM/NLI。

> **概念解释｜Top-M 局部邻域**：只观察与当前候选最相似的 M 个候选，就能描述局部拥挤，而不必把所有候选连接成图。

> **概念解释｜显式约束与待回答槽**：Query 写明“2025 版”时，可以判断候选版本是否匹配；Query 问“数值是多少”时，Query 本身没有正确数值，只能看候选之间是否冲突，不能把人工答案偷偷输入模型。

### 4.4 真值与方法输入隔离

候选快照生成两个不可混用的视图：

| 视图 | 允许字段 | 用途 |
| --- | --- | --- |
| method_view | Query/Chunk 正文、生产可见文档元数据、三路分数/排名/命中标记、确定性可观测特征 | 所有排序方法输入 |
| evaluation_view | qrels、Gold/等价/冲突标签、pool_role、目标等价组、压力链、父 Chunk、变换记录、注入数量 | 构造、算指标和审计 |

删除、随机置换或脱敏 evaluation_view 后，方法分数与排序必须逐值不变。

> **概念解释｜标签泄漏**：如果模型训练或推理时读取了只有评测阶段才知道的答案、Gold 身份或人工干扰类型，就叫标签泄漏。它会产生不可部署的虚高结果。

### 4.5 构件效度

代理进入 M1 前，先在独立分层审计集上验证：

- Query—候选显式错配的 PR-AUC、宏平均 F1 和分类型召回；
- Top-M 候选对冲突的 PR-AUC、宏平均 F1 和分类型召回；
- 相对 prevalence 和 similarity-only 的增量；
- 高相似事实等价候选被误判为冲突的比例；
- 有可判定约束与无可判定约束 Query 的覆盖率和分开表现。

人工标签只用于验证代理，不进入 M1 输入。

> **概念解释｜构件效度**：构件效度回答“这个代理是否真的测到了事实冲突”，而不是只与结果碰巧相关。若代理无法区分良性冗余和错误冲突，方法构件失败。

## 5. 数据、划分与标注

### 5.1 数据角色

| 数据 | 角色 | 当前状态 |
| --- | --- | --- |
| Lo/rerankers-and-lexical-similarities，DRUID `standard` | 英文相似候选退化复现；只回答 RQ1/RQ2 | 固定 revision 已落盘并审计；只进入外部复现，不进入六单元 C1 主分母或 Gate B |
| T2Ranking / T2Retrieval | 中文通用公开主实验 | 原始 230 万 corpus 与 Train/Dev 四级 qrels 已落盘对账。C-MTEB/历史 v4/v5 恰好来自原始 Dev；Dev 整体仅作 calibration/exposed-only，GateA/Blind 候选只从与 Dev QID 交集为 0 的原始 Train 按 family 再分 |
| DuRetrieval | 独立完整保留的中文公开数据；用于预先声明的辅助稳健性分析 | 固定 C-MTEB compact revision 的 100,001 条 corpus、2,000 个 Query 与 9,839 条 qrel 作为一个不可拆分实体保留；不因其文本出现在 C-MTEB Cmedqa 中而删行、合并或降格。本角色不进入当前六单元 C1 主分母或 Gate B；若要改变 Gate 角色，必须在查看结果前另升协议版本 |
| cMedQA2 | 条件、数字、否定等约束密集的中文公开主实验 | 研究负责人已确认本项目属于非商业科研并接受保守治理；使用上游固定 commit `85feb9278c3ae552c591205cbf3e828368c91f8f` 的原始问题、回答与 train/dev/test candidate 标签。医学只作为预先记录的数据分层属性，不构成研究问题、专门终点或额外 Gate；全文仅在本地研究环境使用，不进入论文复现制品 |
| MedicalRetrieval（原计划，已替换） | 许可审计与历史方案追溯 | 原始与 C-MTEB 派生版虽已落盘，但官方仓库与 card 均无明确数据许可；不进入确认性主分母 |
| Internal Stress v6-Dev | 构念、标注、相似度、代理和功效校准 | 数据 ID、目录、schema 与来源资格已建立；真实 Query/正确证据尚未摄取 |
| Internal Stress v6-GateA | 独立现象与代理研究 | 独立目录与方法访问锁已建立；人口为空，未获得 Gate 资格 |
| Internal Stress v6-Blind | M1 冻结后的 Gate B 一次性内部确认 | 独立目录与 Blind 访问锁已建立；人口为空，未获得 Gate 资格 |

DuRetrieval 不再表述为 cMedQA2/Cmedqa 的混合来源或“治理变化时才启用”的备用数据。当前完整保留范围严格指固定 C-MTEB compact revision：100,001 条 corpus、2,000 个 Query、9,839 条 qrel；它不等同于、也不声称已经取得上游约 800 万 passage 的 DuReader Retrieval 全量语料。其功能角色与 T2 有重叠，因此预先固定为独立的辅助稳健性数据，而不是当前强制六单元 Gate 的备用通过路径。EcomRetrieval 仍是第一增强数据；RedQA 只在最低包完成且许可、qrels 与成本可控时再加入。

C-MTEB Cmedqa 的 100,001 条 compact corpus 已完成逐条精确正文来源剥离：88,242 条只匹配 C-MTEB DuRetrieval，7,137 条只匹配上游 cMedQA2 answer，2,086 条同时匹配两者，2,536 条两者均无法按原文精确归属；合计 90,328 条匹配 DuRetrieval、9,223 条匹配上游 answer。`both_exact` 不能强制单归因。2,536 条 `unresolved_neither` 统一保持一个仅审计类别，不再按 qrel 关联建立子类，也不做归一化/模糊回配、专项标注、删除或正式语义使用。该剥离只作为 ID/hash provenance 与曝光 crosswalk，正式 cMedQA2 corpus 仍必须从 pinned 上游全量回答重建；它也不得反向裁剪独立 DuRetrieval 的任何 corpus、Query 或 qrel。

所有主数据统一使用同一套 `equivalent / factual_conflict / other_incorrect / unresolved` 事实关系和证据规则。某一领域的事实无法可靠裁决时进入 `unresolved`，不另立“医学正确性”Gate，也不以领域身份改变 C1/C2 estimand 或 pooled 权重。

### 5.2 内部三分数据

内部母池需要包含真实 Query、对应文档和正确证据。先按 Query、文档族、文档版本和反事实模板分组，再把组整体分为：

- **v6-Dev**：可反复查看，用于规则、阈值和模型开发；
- **v6-GateA**：不参与规则调整，只检验现象和代理；
- **v6-Blind**：不参与 Gate A 和方法开发，只在 M1 完全冻结后运行一次。

T2 的原始 Dev 不再重命名为确认性 cohort；它整体属于 calibration/exposed-only。T2 的 GateA/GateB 候选从原始 Train 按 Query/document family 重新物理分组。

cMedQA2 的上游 Dev 整体属于 calibration/exposed-only；Train 是 Gate A 资格母池，Test 是 Gate B 资格母池，但上游 split 名称本身不构成隔离证明。以 Unicode NFKC、首尾空白删除和连续空白折叠后的问题文本为第一层 family key，固定实体中 Train×Dev、Train×Test、Dev×Test 分别有 35、46、1 个 family 重合，合并后共有 80 个跨 split family，涉及 Train/Dev/Test 的 106/35/46 个 Query；这些 family 全部排除出 Gate A/B 资格母池。去除后，Train 与 Test 分别剩 99,894 和 3,954 个 Query 的资格上界。三个 split 的正例 answer ID 两两交集为 0，但后续仍须按 Query、回答/文档、版本和反事实模板 family 扩大隔离，最终分母由功效分析与构造率先导决定。

历史 Blind v4/v5 已曝光，只能作动机；不得重新命名后进入 v6。

Internal v6 的唯一数据协议为[Internal Stress v6 数据协议](robust-fusion-internal-stress-v6.md)。分享包可为 v6 提供假设来源、工程 provenance、预算和经验证的 corpus 材料，但不能提供不存在的 Query/qrels。当前三分骨架已正式建立、人口仍为空；只有摄取新的真实 Query、正确证据并完成 family 级隔离、双人复核、构造率与功效封存后才取得 Gate 资格。

> **概念解释｜Dev、GateA 与 Blind**：Dev 用来修改规则和模型；GateA 用独立样本判断研究问题是否成立；Blind 用未曝光样本确认最终方法。三者不能由同一 Query、相邻 Chunk、新旧版本或同一反事实模板跨集合派生。

### 5.3 Chunk 产生规则

- 公开数据：一个带稳定 corpus ID 的原始 record 直接作为实验 Chunk，不再用 LinkRag 二次切分；
- 内部文档：使用钉版本的一次性确定性切分，保存 parser、chunker、参数、代码 SHA 和原文位置；
- 同一基础 Chunk 对不同 Query 可以是 Gold、普通负例或干扰项，标签必须挂在 query_id × chunk_id 上；
- Chunking 不是本文方法变量，所有方法共享同一基础 Chunk。

### 5.4 自然候选、等价对照和反事实干扰

每个主数据集同时尽量包含：

- 经复核的自然 Hard Negative；
- 高相似事实等价候选；
- 一次只改变一个事实单元的合成反事实；
- 同文档、旧版本或近重复语料属性。

合成项必须保存父 Chunk、变更前后片段、冲突类型和错误理由，并重新经过与真实语料相同的 Dense、Sparse、BM25 计算。禁止手工填写分数、排名或检索路命中标记。

自然和合成结果分开报告；公开 qrels 中未标相关只能表示“待审”，不能自动当作负例。

### 5.5 标注质量

- 进入确认性压力池的候选 100% 单人内容复核；
- 至少 20% 按数据集、相似度和冲突类型分层双人独立复核；
- 最高相似分带、全部等价对照、全部分歧和疑似 false negative 必须第二人复核；
- 分歧按预先写明的证据优先级仲裁；
- 报告 Cohen’s \(\kappa\) 或 Krippendorff’s \(\alpha\)、分歧数和最终 unresolved 数；
- 相似性审计者不看被测方法结果和预期分带。

### 5.6 样本与资源原则

起始目标不是机械跑满所有组合：

- T2Ranking、cMedQA2、Internal Stress v6 各至少 100 条有效 Query，合计约 300 条作为低成本起点；
- 校准先导初始不超过 100 条 Query；
- Gate A 样本量由校准后的功效分析冻结，不受 100 条上限约束；
- 主剂量曲线为 \(n=0,5,10,20,50\)；
- \(n=100\) 只在资格充足的饱和压力子集上做敏感性分析；
- 固定 \(n=20\) 用于连续相似度×事实关系交互和 2×2 分带复核。

团队必须在 Gate A 前冻结最大 Query 数、单 Query 人工候选上限、双审人时、API 费用和 GPU 小时。若功效需求超过预算，依次删除 \(n=100\) 饱和敏感性、第二随机种子、额外数据集/第三 Reranker 和完整 HybRank/QuDAR 类增强基线。\(n=50\) 是 Gate B \(nAUDC_{0:50}\) 与 Top1 安全的主剂量；如果仍无法承担，必须在 Gate A 前将论文收缩为 C1/C2 现象与测量研究，不能保留 C3 后再删除主剂量。不能先删两个独立 Reranker、两个以上数据集、H2 配对条件和 false-negative 审计。

> **概念解释｜功效分析**：功效分析根据预计效应和数据波动估算需要多少独立 Query。预算不足时应缩小研究主张或记为 Inconclusive，不能靠降低证据标准制造 Go。

## 6. 实验设计与研究仪器要求

### 6.1 候选快照的科研要求

候选快照生成器是研究测量仪器，不是论文方法。它必须把冻结的 corpus、Query/qrels、三路检索证据、压力构造和版本指纹固化为不可变快照，使所有方法接收相同输入。

科研侧只规定：快照必须支持 Query 级配对、等价组指标、连续相似度、事实关系、压力链、方法/评价视图隔离和完整重放。字段 schema、物理格式、目录和验证流程见[工程实施协议第 5 节](robust-fusion-engineering.md)。

> **概念解释｜不可变快照**：快照生成后不再覆盖；任何正文、标签、模型或配置变化都产生新版本。这样所有方法才能在完全相同的输入上重复比较。

### 6.2 轨道 A：固定候选池干预

轨道 A 是主要证据：

1. 用冻结 Dense、Sparse、BM25 生成深层候选超集；
2. 只把 Gold 自然进入超集的 Query 纳入排序因果分析；
3. 为每条 Query 建立固定大小 Clean 池；
4. 用 \(n\) 个压力候选替换 \(n\) 个按检索路命中模式、原始排名、长度和文档族匹配的普通负例；
5. 保持候选总数、目标等价组、组级 gain、IDCG 和随机种子不变；
6. 使用嵌套链 \(D_5\subset D_{10}\subset D_{20}\subset D_{50}\)；
7. 同一条件下，所有方法接收逐 ID 相同的候选池；
8. Clean 与 Stress 做 Query 级成对比较。

若运行 \(n=100\)，候选池 K 至少为 150；任何 Reranker 若只看到更浅输入，就不能声称接受了 100 个干扰。

### 6.3 主处理、对照和机制分析

| 条件 | 相似度 | 事实关系 | 角色 |
| --- | --- | --- | --- |
| Clean | 普通负例 | 错误/不相关 | 基准 |
| 低分带 × 等价 | 低端 | 等价 | 2×2 对照 |
| 低分带 × 冲突 | 低端 | 冲突 | 事实关系对照 |
| 高分带 × 等价 | 高端 | 等价 | 良性冗余对照 |
| 高分带 × 冲突 | 高端 | 冲突 | 核心压力条件 |

核心机制证据按优先级为：

1. 连续相似度×事实关系交互；
2. 预注册 2×2 分带复核；
3. 四类冲突分组；
4. 单路/两路/三路检索支持分层；
5. M1 特征组消融。

不再构造完整候选图、全组合 route knockout 或所有类型×剂量×相似度的全因子矩阵。

### 6.4 轨道 B：语料与索引级干预

在较小子集上把相同干扰 Chunk 真正加入独立 eval 语料和索引，重新运行三路召回。它分别报告：

- Gold 是否进入三路并集；
- Gold 在各路和融合前的位置；
- 干扰由哪一路召回；
- 融合/重排后的排名。

轨道 B 同时改变上游召回和下游排序，只用于端到端外部有效性，不单独证明 M1 的排序因果效果。它检验的 estimand 与轨道 A 不同，因此不作为 C1/C2 或固定候选池 C3 的否决门槛：

- 若轨道 A、Gate A 和 Gate B 通过，但轨道 B 未显示同方向收益，保留“固定候选池内排序直接效应”的相应结论；
- 同时撤回“索引级、端到端或部署环境中同样稳健”的主张，并把上游候选供应变化作为不一致结果报告；
- 若轨道 B 因资源或接口原因未完成，论文只能声称固定候选池效度，不能用“生产外部有效性”措辞；
- 只有未来明确把端到端部署稳健性改为论文主结论时，才需要在一份新的预注册中把轨道 B 提升为否决性门禁。

> **概念解释｜Estimand（目标估计量）**：Estimand 是实验准备估计的具体效应。轨道 A 估计“候选不变时排序方法造成的差异”；轨道 B 估计“索引和召回也变化时整条检索链的差异”，二者不能用同一通过规则替代。

### 6.5 离线融合与重排实验器的科研要求

离线实验器只消费不可变快照，并负责：

- 为全部方法生成完整排序和候选分数；
- 强制方法只读取 method_view；
- 计算 EG 指标、官方指标、成对差值、翻转率和退化曲线；
- 输出 Query 级结果、运行指纹、随机种子和审计日志；
- 对 evaluator-only 字段执行置换不变性测试；
- 不重新访问在线 Retriever，不改变候选正文和冻结的三路原始证据。

方法接口、运行产物、重放和工程验收见[工程实施协议第 7—10 节](robust-fusion-engineering.md)。

## 7. 方法、基线与消融

### 7.1 方法阶梯

| 编号 | 方法 | 用途 |
| --- | --- | --- |
| B1 | BM25 | 词法检索基线 |
| B2 | Dense | 稠密语义基线 |
| B3 | Learned Sparse | 学习稀疏基线 |
| B4 | Fixed Weighted Fusion | 当前稳定融合基线 |
| B5 | RRF | 无监督名次融合基线 |
| B6/B7 | 两个独立家族 Semantic Reranker | 退化现象与强排序基线 |
| B8 | LambdaMART v3 | 现有 38 维强基线 |
| B9 | Local Similarity Dedup/Quota | 排除普通去重或配额解释 |
| B10 | Exact-Constraint Hard Filter | 排除简单显式约束过滤解释 |
| D1 | v3 + Density-only | 只增加局部相似密度 |
| D2 | v3 + Query-Constraint-only | 只增加单候选显式约束错配 |
| D3 | v3 + Matched-Capacity Untyped Local | 同特征数、同预算的无类型局部邻域 |
| A0 | v3 + Matched-Capacity Surface-only | 只使用长度、编辑距离、词面重叠、标点/格式和由 method_view 文本确定性计算的模板相似等表面信息的伪影对照；不含局部密度 |
| M1 | v3 + Local Conflict Route | 唯一完整新方法 |

两个 Reranker 必须来自不同训练或架构家族，不能只替换同一 API 的模型尺寸。模型 ID、revision、量化、最大长度、截断、批处理和推理日期全部冻结。

### 7.2 M1 的最小新增

M1 只增加：

- LocalCrowd；
- LocalConflictRisk；
- MaxConflictSimilarity；
- QueryConstraintMismatch 及覆盖率；
- Dense、Sparse、BM25 各自的 score/rank ConflictAdjustedRouteMargin；
- 必要的 unknown 和缺失标记。

QueryConstraintMismatch 与 v3 已有 exact features 重叠，不单独构成创新。M1 的待检验方法贡献是：在控制 LTR-v3、无类型局部信息 D3 和表面信息 A0 后，类型化局部冲突与分路相对优势是否仍有样本外增量；把若干已有成分组合起来本身不构成创新证据。

### 7.3 容量匹配与必要消融

D3、A0 与 M1 使用相同学习器、训练数据、新增特征数、缺失编码、调参次数和计算预算。D3 逐项替换：

- LocalConflictRisk → LocalCrowd；
- MaxConflictSimilarity → MaxNeighborSimilarity；
- 冲突条件化六个 route Margin → 全部 Top-M 邻居上的无类型六个 route Margin。

A0 不读取关系类型、query constraint truth、route-relative conflict margin，也不读取构造阶段的 transformation-template identity。它只以等数量的长度、编辑距离、字符/词项重叠、标点/格式和由 method_view 文本确定性计算的模板相似特征占位；局部密度由 D1/D3 单独控制，不进入 A0。A0 的特征清单在 Gate A 前冻结，并只在 Gate A = Go 后与 D1—D3、M1 同步训练。

> **概念解释｜Surface-only 对照**：A0 只利用文本表面可能泄露的痕迹，检验 M1 的收益是否其实来自长度、标点、编辑模式或模板相似，而不是事实冲突信息。构造时使用的模板编号属于评价真值，A0 不得读取。

必要消融：

- 去除 LocalCrowd；
- 去除 LocalConflictRisk 与 MaxConflictSimilarity；
- 去除全部 ConflictAdjustedRouteMargin。

若 M1 不优于 D3 或 A0，不能把收益解释为事实冲突类型化贡献。若只优于固定融合而不优于 LTR-v3，方法贡献不成立。

> **概念解释｜Matched-capacity（容量匹配）**：比较方法时保持模型容量、特征数和调参预算相近，只替换真正想研究的信息。这样能减少“只是因为模型更复杂”这一解释。

### 7.4 Gate A 前禁止提前开发的内容

Gate A 前：

- 不训练 D1—D3 或 M1；
- 不训练 A0；
- 不复现 HybRank、QuDAR；
- 不为图模型或近邻系统预留显卡训练；
- 不使用 Gate A 结果反向修改相似度、标签或主指标。

Gate A = Go 后，如投稿目标确实需要，可在官方代码和预算可控时增加 HybRank 或 QuDAR 类方法中的一个；否则 D3 承担最低近邻解释基线。

## 8. 指标与统计分析

### 8.1 主指标

- C1 排序主指标：EG-nDCG@10；
- 方法鲁棒性主指标：\(nAUDC_{0:50}\)；
- 离散安全终点：各 Stress 剂量的 EG-Top1 正确→错误翻转，Gate B 以跨剂量最坏翻转率差作确证量；
- Clean 保护：M1 相对 LTR-v3 的 EG-nDCG@10 非劣性。

同时报告 EG-MRR@10、EG-Hit@10、EG-Recall@10、官方 qrels 指标、目标等价组最佳排名位移、干扰晋升率、Win/Tie/Loss、负收益率、最坏 10% 和最坏分组。

单个方法在每个 Stress 剂量下的 EG-Top1 正确→错误翻转率是描述性风险率：分母为该方法在对应 Clean 条件下 Top1 属于正确等价组的 Query，分子为其中在 Stress 下 Top1 变为非正确组的 Query。比较同一方法的等价/冲突条件时使用这一共同 Clean 风险集；比较 M1 与基线时，使用两种方法在 Clean 中都正确的 Query 交集作为共同风险集，并对 Stress 失败指示做成对比较。另行在全共同 cohort 报告错误→正确、错误保持错误和正确保持正确，不能把方法特异分母的两个率直接相减。Gate B 不从 5/10/20/50 中事后挑一个剂量；其确证安全量在第 9.5 节固定为四个 Stress 剂量中的最坏合并翻转率差。

> **概念解释｜EG 指标**：EG 表示 equivalence-group-capped。支持同一正确事实的多个等价 Chunk 最多计一次收益，既不误罚正确近重复，也不因复制正例抬高指标。

### 8.2 退化曲线

设 \(M(q,n)\) 为 Query \(q\) 在 \(n\) 个干扰下的指标：

\[
D(q,n)=M(q,0)-M(q,n)
\]

\[
nAUDC_{0:50}(q)=\frac{1}{50}
\sum_t
\frac{D(q,n_t)+D(q,n_{t+1})}{2}
(n_{t+1}-n_t)
\]

nAUDC 越小表示整体退化越弱。Gate B 主曲线只在 Clean、全部 Stress 剂量及 M1 与 11 个基线都有完整输出的共同 Query cohort 上计算；运行故障应先修复和重放，不得为某个方法选择性删除 Query。每个 Query family 内先对 Query 取算术平均，每个数据集内再对 Query family 等权平均，最后对 Gate A 前已冻结的主数据集等权宏平均；不按 Query 数、候选数或数据集规模做 micro 加权。对基线 \(b\) 的合并估计量为：

\[
\widehat\Delta^{nAUDC}_{M1>b}
=
\frac{1}{|\mathcal D|}
\sum_{d\in\mathcal D}
\frac{1}{|\mathcal F_d|}
\sum_{f\in\mathcal F_d}
\frac{1}{|\mathcal Q_{df}|}
\sum_{q\in\mathcal Q_{df}}
\left[nAUDC_b(q)-nAUDC_{M1}(q)\right]
\]

其中 \(\mathcal D\) 是 Gate A 前已封存的 Gate B 数据集分母。每次 bootstrap 在各数据集内独立重采样 Query family，但对所有方法、基线和剂量复用同一组抽样索引，并按上式重算完整估计量。Clean EG-nDCG@10 非劣差异也在同一主 cohort 上使用“Query → family → 数据集等权宏平均”规则。每个数据集的最低有效 Query-family 数 \(F_{min,nAUDC}\) 根据 Dev 可构造率和功效分析在 Gate A 前冻结；任一主数据集未达标时不得删除该集或重定权重，Gate B 记为 `Inconclusive`。

> **概念解释｜Macro 与 micro 合并**：Macro 先在每个数据集中得到结果，再让数据集等权；micro 直接把所有 Query 混在一起，大数据集会支配结果。本研究固定使用前者，防止样本量差异改变 Gate。

### 8.3 H2 主模型

固定 \(n=20\)。令 \(C^{(20)}_{qgpa}\) 表示 Query \(q\)、目标等价组 \(g\)、事实关系 \(p\in\{equivalent,conflict\}\) 和匹配压力链 \(a\) 下插入的 20 个候选。C1 的确认性压力集在同一行内必须是单一事实关系，混合等价/冲突的集合只能作探索性分析。候选级相似度先聚合到与结局相同的分析单元：

\[
\bar S_{qgpa}=\frac{1}{20}\sum_{c\in C^{(20)}_{qgpa}}S_{qg}(c)
\]

主预测量 \(\widetilde S_{qgpa}\) 是 \(\bar S_{qgpa}\) 按数据集使用 Dev 均值和标准差冻结后的标准化值。等价与冲突压力链还要匹配候选级相似度分布，并报告均值、中位数、四分位距和最大值的平衡；以中位数替换均值只作预注册敏感性分析，不提供替代通过路径。

每个 \((q,g,p,a,reranker)\) 只产生一行排序伤害 \(D\)，不得把同一个 Query 级 \(D\) 复制到 20 个候选行中。主估计先在每个 Reranker \(r\) ×数据集 \(d\) 单元内使用下式：

\[
D_{qgpa}^{(r,d)}=
\beta_0^{(r,d)}+
\beta_1^{(r,d)}\widetilde S+
\beta_2^{(r,d)}I(conflict)+
\beta_3^{(r,d)}\widetilde S I(conflict)+
\gamma_{qga}+\epsilon
\]

\(\gamma_{qga}\) 是匹配的 Query—目标组—压力链 block 固定截距，使等价与冲突在同一 block 内比较。\(\beta_3^{(r,d)}>0\) 表示压力集平均相似度升高时，事实冲突的额外伤害比事实等价增长更快。模型只在条件级 \(\bar S\) 的共同支持区间估计；同一 Query family 的行使用逆行数权重，使每个 family 在该单元的总权重相同。Bootstrap 在每个数据集内以 Query family 为最高层整组重采样，保留其全部目标组、关系、压力链和两个 Reranker 行，同一重采样索引用于全部确证量。

C1 两个 pooled 主估计量不由样本最多的单元主导，而固定为六个 Reranker×数据集单元的等权算术平均：

\[
\widehat\beta_3^{pool}=\frac{1}{6}\sum_{r,d}\widehat\beta_3^{(r,d)},
\qquad
\widehat\Delta_{high}^{pool}=\frac{1}{6}\sum_{r,d}\widehat\Delta_{conflict>equiv}^{(r,d)}
\]

六个单元的实际分母如果在 Gate A 前依许可、qrel 质量或可构造率依预案变更，必须重做功效、版本化并时间戳封存新的等权公式。解封后任一必要单元无法估计时，pooled 主检验记为 `Inconclusive`，不得删除该单元后重定权重。

六个单元估计同时用于第 9.3 节的方向重复规则，不承担单独显著性检验。若单元模型因稀疏而无法估计，该单元记为不可判定而不是正向；具体最小有效 Query-family 数和后备的配对斜率差 bootstrap 在 Gate A 前冻结。

> **概念解释｜分析单元与伪重复**：分析单元是模型中的一行独立观测。排序伤害是整个候选池的结果，因此必须把 20 个候选的相似度先汇总成一个压力集曝光；若把同一个伤害值复制 20 次，会虚增样本量和统计把握度，这叫伪重复。

高相似分带核心差分：

\[
\Delta_{conflict>equiv}
=
D(high\text{-}sim\ conflict)
-
D(high\text{-}sim\ equivalent)
\]

2×2 分带复核：

\[
\Delta_{interaction}
=
[D(high,conflict)-D(low,conflict)]
-
[D(high,equivalent)-D(low,equivalent)]
\]

### 8.4 不确定性与多重比较

- 连续指标、nAUDC 和交互效应使用以 Query family 为最高 cluster 的 bootstrap CI；所有 pooled 估计量每次重采样都必须重算预先固定的“family 内 Query 平均→数据集内 family 等权→数据集等权”规则，不得对解封后的样本数差异事后重定权重；
- Top1 成对 0/1 转移报告 McNemar exact，但若一个 Query family 含多个相关 Query，该检验只作未校正描述；确认性 Top1 非劣使用以 Query family 为最高 cluster 的 paired bootstrap 同时上界。只有预先保证每个 family 恰有一个 Query 时，McNemar exact 才可承担独立配对推断；等价/冲突比较保留同一方法的共同 Clean 风险集，方法间比较保留两方法 Clean 均正确的共同风险集；
- C1 使用层级式 intersection–union gate：连续交互与高相似匹配差分都是必要条件，二者必须同时通过；剂量曲线、2×2 相邻分带和冲突类型分组只作支持性或敏感性分析，不提供替代显著性路径；
- C1 通过后才检验 C2。C2 固定为 10 个方向性比较：冲突检测与正确成员裁决两个任务，各自在一个冻结主终点上比较 prevalence/majority、similarity-only、v3-only、untyped-local 和 surface-only 五类基线；10 项合成一个 Holm 家族。`untyped-local` 使用无类型邻域相似度、密度和普通局部 margin，`surface-only` 只使用长度、编辑距离、重叠、标点/格式和 method_view 文本模板相似，二者不是同一比较器；
- C3 只有在 C1/C2 允许开发 M1 后才进入 Gate B；Gate B 的 nAUDC 预注册比较构成独立的 11 项家族，另有针对 LTR-v3/D3/A0 的 3 项 Top1 非劣安全家族；
- 探索性冲突类型、单数据集、单 Reranker 和非主剂量结果不参与 Gate 判定，并明确标记为探索性；
- 效应量、CI 和 Query 级 Win/Tie/Loss 同时报告；
- 不把“方向看起来单调”替代正式剂量分析。

这里的 C2 `v3-only`、`untyped-local` 和 `surface-only` 是用于检验冲突检测/正确成员裁决的诊断分类器：前者只读现有 v3 可见特征，第二类只增加无类型局部相似度/密度/margin，第三类只增加文本表面信息。它们不是 Gate B 的排序方法 D1—D3/A0，也不输出最终候选排序，因此不违反 Gate A 前禁止开发 D1—D3/A0/M1 的规则。

C2 的每个主终点先在数据集内重算：检测任务以候选为样例，裁决任务以自然冲突集为样例，两者都使每个 Query family 的总权重为 1，再对 Gate A 前冻结的 C2 合格主数据集等权宏平均“代理方法减比较器”的指标差。同一组数据集内 Query-family bootstrap 索引复用于 10 项比较。有效正/负例、冲突集和 family 的最低覆盖在 Dev 上按指标可估性和功效冻结；解封后任一已纳入数据集无法计算主终点时，该必要比较为 `Inconclusive`，不得跳过数据集或改用 micro 权重。

> **概念解释｜置信区间和效应量**：效应量说明差异有多大；置信区间说明估计有多不确定。只报告 p 值不能判断实际意义。

本协议不使用含义不明确的“Holm-adjusted CI”。对每个预注册家族，在同一组 Query-family cluster bootstrap 重采样上同时计算：一是 Holm step-down 校正后的单侧 p 值；二是分别构造的 Bonferroni family-wise 95% 同时下界和上界。家族大小为 \(m\) 时，下界取每项 bootstrap 差值分布的 \(\alpha/m\) 分位点，上界取 \(1-\alpha/m\) 分位点（\(\alpha=0.05\)）；二者是分别用于正效应确认和明确低效/反向判定的单侧界，不冒充一个双侧 95% 区间。确认性优效比较必须同时满足 Holm-adjusted \(p<0.05\) 和同时下界大于 0；只有同时上界低于实际效应界时，才把正向但过小的结果判为明确低效。Top1 非劣家族只使用 Bonferroni 同时上界与冻结非劣界比较，不把“未显著变差”冒充非劣。普通未校正 95% CI 只作描述。bootstrap 次数、随机种子和 C2 的 10 项、Gate B nAUDC 的 11 项、Top1 安全的 3 项家族清单在 Gate A 前冻结。

> **概念解释｜Bootstrap、McNemar、Holm 与 Bonferroni 同时界**：Bootstrap 通过成组重采样估计连续差异的不确定性；McNemar 检验同一批 Query 的成对正确/错误变化；Holm 逐步校正一组 p 值；Bonferroni 同时界则用更严格的分位点保证整组置信界的覆盖率。这里把“显著性校正”和“同时置信界”分开定义，避免把普通 CI 误称为 Holm CI。

> **概念解释｜Intersection–union gate 与层级检验**：Intersection–union 要求多个必要条件全部成立，任何一项失败都不能用另一项补救；层级检验则先检验上游主张，只有通过后才检验下游主张。这样可以控制“尝试很多检验后挑一个成功”的偶然性，同时保留 C1、C2、C3 各自的科学含义。

### 8.5 反伪影控制及组合规则

反伪影控制不是一组可任意挑选的附加图表，而按以下后果冻结：

| 阶段 | 角色 | 控制 | 通过要求 | 失败后果 |
| --- | --- | --- | --- | --- |
| Gate A 与 Gate B | 硬门禁 | 分组隔离、method/evaluation 视图隔离、候选池配对 | 必须全部通过 | 对应确认性运行无效，不得进入相应 Gate |
| Gate A | 硬门禁 | 自然样本独立复核 | 在预注册最低自然覆盖上，自然-only 的高相似冲突—等价差分点估计必须大于 0，且双侧 90% CI 下界大于冻结的 \(-\delta_{nat}\)（等价于单侧 95% 下界），排除有实际意义的反向效应 | 点估计不为正或 CI 上界小于等于 \(-\delta_{nat}\) 为失败；其余未通过组合为 Inconclusive。失败时只能保留受控合成敏感性结论，Inconclusive 时不授权 M1 |
| Gate A | 硬门禁 | Surface-only 诊断对照 | 类型化代理相对只读 method_view 表面信息的诊断器，在检测与裁决各自冻结主终点上的点估计至少达到对应的 \(\boldsymbol\epsilon_{surf,A}=(\epsilon_{surf,A}^{det},\epsilon_{surf,A}^{adj})\)，Holm-adjusted \(p<0.05\)，且 Bonferroni 同时下界大于 0 | 任一必要任务点估计非正，或 Bonferroni 同时上界低于对应实际效应界为失败；其余未通过组合为 Inconclusive。失败或 Inconclusive 均不授权 M1 |
| Gate A | 硬门禁 | 关系标签/伪类型置换 | 置换后 C2 增量和类型化解释应消失到冻结容差内 | 若置换仍保留同等效应，视为管线泄漏或伪影，C2 失败 |
| Gate A | 范围敏感性，不否决已见类型 C1 | held-out 冲突类型 | 报告未见类型上的方向、覆盖和校准 | 失败限制跨类型泛化；不得声称类型无关，但不单独改变 Gate A |
| Gate B | 硬门禁 | M1 对 A0 | \(\widehat\Delta^{nAUDC}_{M1>A0}\ge\epsilon_{M1}\)，Holm-adjusted \(p<0.05\)，且 Bonferroni 同时下界大于 0 | 点估计非正或 Bonferroni 同时上界低于 \(\epsilon_{M1}\) 为失败；其余未通过组合为 Inconclusive。失败或 Inconclusive 均不支持 C3 |
| Gate B | 硬门禁 | route assignment 置换 | route-relative 增量应消失到冻结容差内 | 若不消失，撤回检索路机制解释和 M1 分路贡献，C3 不成立 |

Gate A 的 \(\boldsymbol\epsilon_{surf,A}\)、自然反向非劣界 \(\delta_{nat}\)、Gate B 的 \(\epsilon_{M1}\)、置换容差、最低自然覆盖和每项统计终点均进入 Gate A 前的时间戳冻结清单；各实际效应界只能依据外部可解释性和不含 M1/D3/A0 比较结果的 Dev 方差规则确定。Gate A 只判定表中标为 Gate A 硬门禁或两阶段共有硬门禁的项目，不能等待尚未开发的 A0/M1；held-out 类型只限制范围。Gate B 再判定 A0、route assignment 与共有隔离。任何关键隔离或泄漏控制失败都不能由其他控制的正结果抵消。

> **概念解释｜实际效应界、反向非劣界与伪影**：实际效应界 \(\epsilon\) 规定正向增量至少多大才值得主张；反向非劣界 \(\delta_{nat}\) 规定自然样本最多容许多大的反方向差异。这里不执行“两者等价”的 TOST 检验。伪影是由文本长度、标点、模板痕迹或数据泄漏造成的假信号，而不是研究声称的事实冲突信息。

### 8.6 成本指标

Fixed Fusion、LTR-v3、D3、A0、M1 和两个 Reranker 至少报告：

- 单 Query p50/p95 延迟；
- 峰值 CPU/GPU 内存；
- 邻域、约束抽取、route margin 和排序的分阶段耗时；
- Reranker 调用次数、token 或 API 成本；
- 复用现有向量的增量成本；
- 无缓存时的 cold-start 成本。

只有 M1 在相同 K 和硬件下的增量 p95 与资源低于全量 Reranker，且不调用 Reranker，才使用“低成本”表述；否则改称“无需重训 Reranker”。

## 9. 阶段、门禁与当前行动

### 9.1 三种研究活动不能混用

| 活动 | 是否可看结果并改规则 | 样本角色 | 能否支持论文结论 |
| --- | --- | --- | --- |
| 构念/仪器校准 | 可以 | Dev | 不能单独支持核心结论 |
| Gate A 独立研究 | 不可以 | GateA cohort | 支持 RQ1/RQ2 |
| Gate B 方法确证 | 不可以 | Blind cohort | 支持或否定 RQ3 |

> **概念解释｜校准先导**：校准先导用于检查尺子、标签和流程是否可用，并估计正式研究需要多少样本。它不是为了先跑出一个正结果。

### 9.2 Gate A 之前的阶段

| 顺序 | 阶段 | 必要产出 | 当前状态 |
| ---: | --- | --- | --- |
| 1 | P2 核心构念与标注 | 相似度 manifest、标注手册、EG 指标规范 | 当前进行 |
| 2 | P3 数据与模型冻结 | 公共数据 revision/qrels、内部三分数据、两个 Reranker | 进行中；cMedQA2 已正式替换 MedicalRetrieval，T2/cMedQA2 已有 split-level 资格规则；相似度编码器资格预选已完成，Reranker、分母与功效仍待冻结 |
| 3 | P4 测量仪器 | 候选快照、离线实验器、视图隔离、重放校验 | 待做；现有工程资产可直接审计 |
| 4 | P5 校准先导 | 可构造率、效应方差、代理正类率、功效分析 | 待做 |
| 5 | P5 预注册 | Gate A 样本量、模型、实际效应阈值、比较家族、正向单元、反伪影组合、排除与停止规则 | 待做 |
| 6 | P6 Gate A | 独立现象、交互与代理报告 | 待做 |

当前下一任务仍是完成 P2-01，而不是立即运行 Reranker；按“先穷尽公开数据和既有资产”的数据策略，P3-01 文件摄取已经完成，P3-02 数据资格收口与 P2 校准准备并行：

1. 非 BGE 主/独立审计编码器的精确 revision、实现、权重摘要与固定无标签重放已经完成资格预选；下一步先冻结两个 Reranker 家族并确认不复用这两个 encoder，再在 Dev 完成长短文本分层的人机效度、共同支持、分带和参照集合封存；
2. 已从 pinned T2/DRUID 生成并哈希锁定 12 个 Dev 桌面案例；由两名标注员在不查看 facilitator key 的条件下独立校准四类冲突标注手册；
3. 将已确认的 cMedQA2 非商业本地使用边界、Dev-exposed/Train-GateA/Test-GateB 资格规则与 T2 的 Dev-exposed/Train-resplit 规则写入数据 manifest；完成 family 排除、构造率先导和功效分析后冻结三数据集分母；
4. 只有公开标签与既有资产仍无法补足语义关系时，才生成最小人工标注包。

### 9.3 Gate A 判定

Gate A 是开发 M1 前的必要门禁。当前预注册草案中的继续开发门槛为：

- \(\epsilon_{phen}=0.02\) EG-nDCG@10；
- \(\epsilon_{int}\)：标准化相似度每增加 1 SD 时，冲突相对等价增加的最小实际伤害；具体值由 Dev 方差、可解释性和功效分析确定，不能以 0 代替；
- 代理相对 prevalence 的 PR-AUC 增量 \(\epsilon_{prev}=0.05\)；
- 代理相对 similarity-only 的增量 \(\epsilon_{sim}=0.02\)；
- surface-only 对照在检测与正确成员裁决两个冻结主终点上的实际效应界 \(\boldsymbol\epsilon_{surf,A}\)：由 Dev 方差与外部可解释性分别定标；
- 自然-only 高相似差分允许的最大实际反向界 \(\delta_{nat}>0\)：用于排除“总体正效应其实由合成样本驱动、自然样本有实质反向”的情况。

\(\epsilon_{phen}\)、\(\epsilon_{int}\) 和代理增量共同区分“统计上非零”与“科研上值得研究”。C1 采用双条件：点估计达到实际效应阈值，双侧 90% CI 下界大于 0；当前协议不要求 CI 下界同时越过实际效应阈值。若点估计为正但未通过，只有双侧 90% CI 上界低于对应实际效应阈值时才判为明确低效，否则为 Inconclusive。最小实际效应阈值不得为了迎合校准或 Gate A 的结果而调整；其最终依据、功效目标和 Gate A 样本量必须在读取 Gate A 结果前冻结。若草案数值改变，必须使用未接触 Gate A 的 Dev 证据记录理由、时间和研究版本。

Gate A = Go 必须同时满足：

1. 标签、等价组、固定候选池、相似性审计、false-negative 和泄漏检查均通过；
2. 预注册高相似分带、\(n=20\) 下的 \(\Delta_{conflict>equiv}\ge\epsilon_{phen}\)，且分组 bootstrap 90% CI 下界大于 0；
3. 连续模型 \(\beta_3\ge\epsilon_{int}\)，90% CI 下界大于 0，并达到共同支持覆盖率；
4. 两个 Reranker × 三个数据集的六个单元中至少四个为“正向单元”，覆盖两个 Reranker 和至少两个数据集；正向单元定义为该单元的预注册 \(\hat\beta_3>0\) 且 \(\widehat\Delta_{conflict>equiv}>0\)，不要求每个小单元各自显著，统计不确定性由第 2—3 条的合并主检验承担；
5. 至少两个数据集完成有效 2×2 复核，方向不被预指定相邻分带边界稳定反转；
6. C1 的 intersection–union gate 通过后，C2 的冲突检测和正确成员裁决按冻结的 10 项比较家族执行；相对 prevalence/majority、similarity-only、v3-only、untyped-local 和 surface-only 的增量须同时满足实际效应门槛、Holm-adjusted \(p<0.05\)、Bonferroni 同时下界大于 0 与覆盖率要求，且至少两个数据集方向一致；
7. 第 8.5 节标为 Gate A 或两阶段共有的**硬门禁**均按预注册组合规则通过；held-out 类型只限制结论范围，Gate B 专属的 M1—A0 与 route assignment 不参与 Gate A 判定。

判定：

- **Go**：全部必要条件通过，允许开发 M1；
- **Inconclusive**：尚未触发任何预注册失败规则，但至少一个硬门禁因区间、样本资格、覆盖或功效不足而未满足该条件自身适用的通过规则；只允许一次预注册扩样，或者终止方法门禁并把论文收缩为不需要该 Gate 成功的描述性/边界结果；收缩主张本身不构成 `Go`；
- **No-Go**：任一硬门禁触发其预注册失败规则（包括必要主效应点估计不为正、CI 上界低于对应实际效应界、自然-only 触发第 8.5 节反向失败、代理无法测量冲突，或少于两个合格数据集）；停止方法路线。

停止规则对当前协议版本具有约束力：

1. `No-Go` 是本研究协议下事实冲突方法路线的终局，不能重新划分相似度、替换结果不利的数据集、改写冲突标签或重新抽取 Gate A 后再声称本研究通过；
2. `Inconclusive` 最多允许一次由原功效模型支持、且不改变 estimand、标签、数据集分母和阈值的追加样本。追加范围、上限、停止点和合并分析必须在读取新增结果前另行时间戳冻结；若选择收缩主张而不扩样，当前 Gate 仍不判为 `Go`，也不授权 M1；
3. 若未来根据新理论、新数据或新定义发起第二个 Gate A 周期，必须使用新的研究 ID、独立预注册和独立结论，且不得与本研究的失败 Gate A 合并成一次成功验证；
4. 明确失败后仍可发表负结果或机制边界，但不得开发并宣传当前 C3 方法已经获得现象依据。

剂量是否严格单调、LTR-v3 是否已经保护排序是诊断结果，不单独决定 Gate A。

> **概念解释｜正向单元与合并主检验**：一个单元是“某个 Reranker × 某个数据集”。单元正向只检查两个预注册效应的方向是否一致，用于判断结果是否集中在单一模型或数据集；是否有足够统计证据由合并后的主检验和置信区间决定，不能要求六个小样本分别显著。

### 9.4 Gate A 通过后的方法开发

只使用 Dev/Train/Tune/OOF：

1. 实现 D1—D3 和 A0；
2. 实现 M1；
3. 冻结特征签名、逐项替换、阈值、训练与调参预算；
4. 冻结数据源×基线×主指标判定矩阵；
5. 不读取 GateB/Blind 结果；
6. 完成后 seal 模型和分析代码。

### 9.5 Gate B 判定

Gate B 使用公开 held-out GateB cohort 和一次性 Internal Stress v6-Blind。唯一确证性 Stress population 是“高相似分带 × verified factual conflict”的嵌套压力链；低相似、事实等价、混合关系与 \(n=100\) 只作诊断/敏感性，不能替代 Gate 结果。自然/合成来源在每个数据集使用一个由 Dev 合格可构造率决定、且在 Gate A 前封存的非零自然候选配额 \(\pi_d=(\pi_{natural},\pi_{synthetic})\)；候选以确定性分层顺序加入，使 5/10/20/50 的每个前缀都按冻结取整规则接近该配额。某 Query 无法满足配额时事先记为不合格，不得解封后用另一 origin 顶替。各 origin 另行分层报告，但不产生第二条 Gate 路径。

> **概念解释｜Stress population 与 origin 配额**：Stress population 是真正用来判定 Gate B 的压力样本集合；origin 配额规定其中自然难负例和人工反事实各占多少。预先固定它，是为了防止看到结果后才挑选更有利的样本类型。

主 nAUDC 固定由该 Stress population 上 EG-nDCG@10 的 Clean-to-Stress 退化计算，并使用第 8.2 节的 Query→family→数据集等权宏平均；对任一基线 \(b\)，定义：

\[
\Delta^{nAUDC}_{M1>b}=nAUDC_b-nAUDC_{M1}
\]

正值表示 M1 的累计退化更小。最小实际鲁棒性增量 \(\epsilon_{M1}>0\) 与 Top1 翻转非劣界 \(\delta_{flip}>0\) 必须在训练 M1、D3、A0 和观察它们之间的任何 Dev 差值之前冻结；数值或确定性选取规则只依赖外部可解释性与基线结果方差，并进入 Gate A 前的时间戳包。第 8.2 节的等权宏平均是 nAUDC 与 Clean 非劣的唯一 pooled 规则，不报告任何可替代 Gate 判定的 micro 结果。M1 必须同时满足：

1. 对 Fixed Fusion、RRF、两个 Reranker、LTR-v3、D1、D2、D3、A0、B9、B10 的 11 项分层合并 \(\Delta^{nAUDC}_{M1>b}\)，Holm-adjusted 单侧 \(p<0.05\)，且 Bonferroni family-wise 95% 同时下界大于 0；
2. 对新颖性关键基线 LTR-v3、D3 和 A0，\(\widehat\Delta^{nAUDC}_{M1>b}\ge\epsilon_{M1}\)；
3. 对每个主数据集 \(d\) 与每个新颖性关键基线 \(b\in\{LTR\text{-}v3,D3,A0\}\)，分数据集点估计 \(\widehat\Delta^{nAUDC}_{M1>b,d}\ge0\)；该要求不扩展为每个数据集都必须逐一显著；
4. 对每个 \(b\in\{LTR\text{-}v3,D3,A0\}\) 和剂量 \(n\in\{5,10,20,50\}\)，在 M1 与 \(b\) 的成对共同 Clean 正确风险集上，按“Query → family →冻结主数据集等权”计算 \(\Delta^{flip}_{M1-b}(n)=FlipRate_{M1}(n)-FlipRate_b(n)\)，并固定确证量 \(\Delta^{flip,worst}_{M1-b}=\max_n\Delta^{flip}_{M1-b}(n)\)。该成对风险集在四个剂量中保持不变；每个 bootstrap 重采样中先重算四个剂量差，再取最大值；3 项安全家族的 Bonferroni family-wise 95% 同时上界均必须小于 \(\delta_{flip}\)。对基线 \(b\)、数据集 \(d\) 和该集主 cohort 的 family \(\mathcal F_d\)，令 \(\mathcal R_{bdf}\subseteq\mathcal Q_{df}\) 为 M1 与 \(b\) 在 Clean 都正确的 Query，则共同正确覆盖唯一定义为
   \[
   \rho_{bd}^{flip}=\frac{1}{|\mathcal F_d|}\sum_{f\in\mathcal F_d}\frac{|\mathcal R_{bdf}|}{|\mathcal Q_{df}|}。
   \]
   有效风险 family 数定义为 \(|\{f:|\mathcal R_{bdf}|>0\}|\)。每个基线×数据集必须同时达到 Gate A 前依非劣功效冻结的 \(F_{min,flip}\) 和 \(\rho_{min,flip}\)；任一已冻结主数据集未达标、风险集为空或上界无法构造时，该比较为 `Inconclusive` 且 C3 不成立，不得跳过该基线或数据集。各剂量率、McNemar exact 与四格转移仅作未校正描述；
5. Clean EG-nDCG@10 相对 LTR-v3 的非劣界 \(\delta_{clean}=0.01\)；使用第 8.2 节冻结的 pooled 权重和 Query-family cluster bootstrap，确证性单侧 95% 下界（等价于双侧 90% 区间下端）必须大于 \(-0.01\)；
6. evaluator-only 字段置换不改变方法输出；
7. route assignment 置换后分路增量消失到冻结容差内；
8. Top1 翻转、负收益率和最坏分组完整报告。

任一主条件失败或 `Inconclusive`，停止“新方法已成立”的主张；若 Gate A 仍成立，收缩为退化机制与评测论文。Gate B 是一次性 Blind 确证：不享有 Gate A 的一次功效支持扩样权，不得补抽 Blind Query 后将两次结果合并为通过。

> **概念解释｜非劣性**：新方法不一定要让 Clean 更好，但必须证明它没有差到超过预先允许的界限。这样可以防止用严重损害普通场景换取压力场景收益。

> **概念解释｜共同风险集上的翻转非劣**：比较 M1 和某条基线时，只看两者在 Clean 都排对的 Query，再判断谁在 Stress 下翻错。\(\delta_{flip}\) 是 M1 最多允许增加的翻错率；置信上界低于该值才叫非劣，单纯“p 值不显著”不够。

> **概念解释｜跨剂量最坏翻转率差**：分别计算 5、10、20、50 个干扰时 M1 比基线多翻错多少，再取其中最大的一个。这使某个中间剂量的安全恶化不会被其他剂量的平均数掩盖。

> **概念解释｜nAUDC 差值方向**：nAUDC 越小越好，因此本文用“基线减 M1”。差值大于 0 才表示 M1 更稳健；写反方向会把更严重的退化误判成改进。

### 9.6 预注册封存与外部时间戳

Gate A 输入解封前，必须形成一个只读预注册包，至少包含科研协议版本、数据集分母、Reranker、样本量与功效、所有阈值（包括 \(\boldsymbol\epsilon_{surf,A}\)、\(\delta_{nat}\)、\(\epsilon_{M1}\) 与 \(\delta_{flip}\)）、C1/C2/Gate B/Clean 的冻结 pooled 权重和最低风险集覆盖、Gate B 高相似冲突 Stress population 与数据集内 origin 配额、C2 的 10 项、Gate B nAUDC 的 11 项和 Top1 安全的 3 项比较家族、Top1 跨剂量最坏 estimand、Holm p 值与 Bonferroni 单侧同时上下界实现、正向单元定义、反伪影组合规则、排除规则、仅适用于 Gate A 的一次扩样条件、统计代码 SHA 和输入 manifest 摘要。

封存同时满足：

1. 先生成并只做资格/完整性复核的 Gate A 候选快照，不运行或读取确认性排序结果；
2. 冻结一个 root manifest，逐项列出协议、分析代码、数据/划分、候选快照和配置的内容摘要；
3. 仓库中的专用 clean commit/tag 能唯一解析代码与协议，root manifest 生成 SHA-256；
4. 使用独立于本地工作区的公开或受控第三方服务时间戳该 root hash，优先 OSF Registries；若数据不能公开，只登记协议、摘要和哈希，不上传内部正文；
5. 时间戳 receipt 作为只追加 sidecar 保存，引用 root hash，但不反向进入已哈希的 root manifest，避免自引用；
6. 运行清单同时记录 root hash 与 receipt ID，验证后才解锁 Gate A；
7. 任何主数据集缩减或分母变化必须在查看 Gate A 结果前生成新的版本与时间戳，并重新完成对应功效分析；
8. Gate A 报告同时披露冻结时间、解封时间和所有偏离。

仅有未推送的本地文件修改不能作为外部冻结证据。

> **概念解释｜外部时间戳**：外部时间戳由本地工作区之外的登记服务记录“某份协议在某个时间已经存在”。它不能保证研究一定正确，但能减少结果出现后偷偷改规则的空间。

> **概念解释｜Root manifest 与 receipt sidecar**：Root manifest 是被封存产物的总装箱单；receipt sidecar 是第三方时间戳返回的凭据。先哈希装箱单、再让凭据引用该哈希，可以避免“装箱单必须先包含尚未生成的凭据”这一循环。

## 10. 最低发表包、结论和投稿边界

### 10.1 最低发表包

最低包只保留支撑 RQ1—RQ3 的必要内容：

1. DRUID 英文现象复现；
2. T2Ranking、cMedQA2、Internal Stress v6；
3. 两个独立 Reranker；
4. 固定候选池 0/5/10/20/50 剂量曲线；
5. 固定 \(n=20\) 的连续交互与 2×2 分带复核；
6. 四类冲突、检索路支持分层和构件效度；
7. Fixed Fusion、RRF、两个 Reranker、LTR-v3、B9/B10、D1—D3、A0、M1；
8. EG-nDCG、Top1 翻转、nAUDC、Clean 非劣、Query 级风险；
9. 分组 CI、McNemar、Holm；
10. 一次小规模轨道 B；
11. 成本报告；
12. 完整 manifest 和可重复播放快照。

Gate A 前不复现 HybRank 或 QuDAR。Gate A = Go 后，只有目标渠道和预算明确要求时才增加一个完整近邻强基线。

### 10.2 增强项

- EcomRetrieval；
- leave-one-domain-out；
- \(n=100\) 饱和压力；
- 第二随机种子扩大覆盖；
- 一个完整近邻强基线；
- 可公开的干扰构造与标注材料。

增强项失败不能推翻已经由最低包支持的结论，也不能成为无限延长研究的理由。

### 10.3 允许的结论

只有相应门禁通过后，才允许写：

- 在预注册条件下，事实冲突型高相似候选对多种 Reranker 造成可重复的额外排序伤害；
- 连续相似度×事实关系交互和分带复核方向一致；
- 可观测冲突代理具有构件效度；
- M1 相对强基线降低 nAUDC 且保持 Clean 非劣；
- 结果在预定义数据与模型范围内方向一致。

### 10.4 禁止的结论

- LambdaMART 普遍优于神经 Reranker；
- 首次发现 Reranker 会被 Hard Negative 欺骗；
- 首次提出 sparse/dense/BM25 融合、候选邻域或 margin；
- 检索改善必然提高生成答案质量；
- 本方法彻底解决相似拥挤或提供安全保证；
- 把历史 Blind、单一内部集合或一次“约 7%”外推为通用结论；
- 把 oracle、人工关系标签或 evaluator-only 信息冒充部署方法；
- 隐瞒合成干扰、qrels 漏标风险或失败数据集。

### 10.5 发表规划入口

目标渠道、投稿顺序、arXiv、版本关系、费用和投稿伦理统一见[发表路径与投稿治理](robust-fusion-publication.md)。本科研协议不重复维护发表路径。

## 11. 冻结决定与变更规则

当前冻结：

1. 中英文题目和候选融合/排序研究边界；
2. C1 为主要科学贡献、C2 为诊断贡献、C3 为 Gate A 后的条件性方法贡献，以及 RQ1—RQ3；
3. LTR-v3 是强基线，不是论文创新；
4. 实验相似度为候选—唯一目标等价组正确参照相似度；
5. 连续相似度×事实关系为主检验，低/高分带只作预注册复核；
6. 推理方法只读 method_view；
7. M1 为 Top-M 局部冲突风险和冲突条件化分路 Margin；
8. 不构建图、不做学习门控、不用 RL 生成干扰、不重训大型 Reranker；
9. 内部数据分为 Dev、GateA、Blind；
10. 轨道 A 为主要排序证据；轨道 B 为不同 estimand 的端到端外部有效性证据，失败时限制部署主张而不反向否定固定池结论；
11. 公开 corpus record 直通，内部文档确定性切分；
12. 合成反事实一次只改一个事实单元并重算三路证据；
13. Gate A 前不复现 HybRank/QuDAR，不训练 M1；
14. Blind v4/v5 和历史项目增量只作动机；
15. 已恢复的工程资产不自动成为确认性研究数据；
16. 一个确认性快照只使用一个冻结的上游索引版本，不混合不同历史口径；
17. 所有阈值、模型、样本量、比较家族、正向单元、反伪影组合、排除规则和统计代码在相应 Gate 前冻结；
18. 当前协议的 Gate A `No-Go` 不能通过重开同一研究周期挽救，`Inconclusive` 最多一次预注册扩样；
19. Gate A 预注册包必须有 commit/SHA-256 和外部时间戳，数据集分母变更也必须先冻结；
20. 新颖性分别依赖 C1 的等价—冲突受控测量、C2 的可识别性分区和条件性 C3，不依靠“没有工作同时满足全部条件”的长合取。
21. Query—Chunk 标签拆为 `relevance_status`、`target_relation` 与 `adjudicability` 三个正交字段，候选对另用 `candidate_pair_relation`；不得退回单一混合标签；
22. 真值未知必须排除确认性分析；评价真值已知但 method view 不可识别的样本保留为 C2 边界，并保持 LTR-v3 顺序；
23. 原始 qrel 永不覆盖；人工复核作为带 evidence locator、reviewer、状态和手册版本的独立 adjudication layer。
24. 历史 T2 的 `993101/993103` 是由已揭盲 Query 条件化生成的子池，只用于曝光恢复和工程追溯；正式 T2 候选生成必须回到固定 revision 的原始完整 corpus。原始 Dev 整体 calibration/exposed-only，GateA/Blind 只从原始 Train 按 family 再分。
25. SQLite `990126/990127` 各 800 个 ID 可作 provenance crosswalk，但其乱码正文和相关历史向量/token 不得进入正式语义快照；正文必须回到 pinned 官方文件。
26. C-MTEB Cmedqa 的 DuRetrieval 混合 corpus 不得作为权威 cMedQA2 候选总体；研究负责人已确认本项目属于非商业科研，上游 `cMedQA2@85feb9278c3ae552c591205cbf3e828368c91f8f` 正式替换 MedicalRetrieval，全文只在本地研究环境使用，复现制品只发布上游 commit、ID、hash、派生标签与 loader。医学域只作预先分层，不形成专门研究终点或 Gate。
27. cMedQA2 原始 Dev 整体 calibration/exposed-only，Train/Test 分别只作为 Gate A/Gate B 资格母池；任何跨 split 的规范化 Query family 均排除出确认性母池，后续 document/version/template family 审计只能扩大排除，不能缩小。
28. DuRetrieval 是独立且完整保留的数据集；固定 C-MTEB compact revision 的 100,001 条 corpus、2,000 个 Query 与 9,839 条 qrel 不因 C-MTEB Cmedqa 的重合关系被删除、合并或抽取子集。它预先固定为当前六单元 Gate 之外的辅助稳健性数据，任何 Gate 角色变化都需要在结果不可见时另升协议版本。
29. C-MTEB Cmedqa compact corpus 的四类精确来源剥离只用于 provenance/曝光对账；不把 `both_exact` 强制单归因。全部 2,536 条 `unresolved_neither` 作为一个未解析审计类原样保留，不按 qrel 关联单列，不做回配、专项标注、删除或正式语义使用。
30. `linkrag-eval-sqlite-share-20260827` 固定为研究假设与工程可行性的正式起点；Internal v6 的 ID、三分目录、访问锁和最小摄取 schema 已建立，但现有资产没有 Query/qrel 行，不能伪造人口或提前取得 Gate 资格。
31. 当前真实三路固定为 `text-embedding-v4` Dense、Ark/豆包 Learned Sparse 与 SQLite FTS5 BM25；BGE-M3 已淘汰，历史 Alt Embedding 不得进入 Gate A route、实验相似度或独立审计。
32. 实验相似度在不读取研究数据时预选 `multilingual-e5-base@d1287505…` 为主编码器、multilingual DistilUSE `@bfe45d07…` 为独立审计编码器；该决定只冻结资格阶段的模型身份、输入和确定性，不授权 Gate A。Dev 人工效度、共同支持、分带和正式参照集合仍须在结果不可见时封存。
33. Gate A 两个独立 Reranker 家族在 Gate A/B 与 Dev 排序效果均不可见时冻结为 `Qwen/Qwen3-Reranker-0.6B@e61197ed…`（生成式）与 `jinaai/jina-reranker-v2-base-multilingual@9cfeff2d…`（跨编码器）。Qwen 对应项目真实测评，Jina 提供不同生产者、架构与打分头的确认性重复；Jina 被独立 FEVER 2025 多 Reranker 研究采用（DOI `10.18653/v1/2025.fever-1.2`），但该采用不证明模型天然最优或本文 C1。两者选择不得按 Dev 或 Gate 结果更换；P3-05 仍须完成资源、截断覆盖与逐值重放契约。

任何变更必须记录：

- 变更时间；
- 变更原因；
- 是否已经看过相关结果；
- 受影响的 RQ、假设、数据和结论；
- 新研究记录版本。

### 11.1 本版变更记录

| 版本 | 时间 | 原因 | 是否已看相关结果 | 影响范围 |
| --- | --- | --- | --- | --- |
| v19 | 2026-08-28 | 研究负责人确认以 Qwen3-Reranker-0.6B 与 Jina v2 multilingual 作为 Gate A 两个独立 Reranker 家族 | Gate A/B 与 Dev 排序效果均未读取；只核对项目真实模型、固定公开制品、许可、合成探针重放和独立学术采用 | 冻结两个 Reranker 的模型 ID/revision、家族角色和不得按效果换模规则；不改变六单元等权 estimand、4/6 方向规则、RQ、Gate 阈值或数据分母；P3-05 仍待资源与 Dev 契约 |
| v18 | 2026-08-28 | 研究负责人纠正真实 Learned Sparse 使用豆包在线 API，并明确淘汰 BGE-M3；同时重申医学场景不是研究终点 | Gate A/B 均未运行；只核对本地真实配置、兼容代码和一次固定无标签 API 探针，没有查看排序或研究结果 | 固定真实三路；BGE 历史 sidecar 退出 route、\(S_{qg}(c)\) 与独立审计；主相似度编码器回到结果不可见的重新选择门禁；cMedQA2 保留主数据角色但域只作分层，不改变 RQ、Gate estimand、比较家族或门槛 |
| v17 | 2026-08-28 | 研究负责人要求不对 2,536 条未解析记录中的 qrel 关联项作专项标记或处理，并把 DuRetrieval 的独立性与完整性置于首位 | Gate A/B 均未运行；只使用既有固定 revision、文件摘要和公开实体计数，没有查看新的排序结果 | 完整保留 pinned C-MTEB DuRetrieval 的 100,001/2,000/9,839 实体且禁止重合扣除；2,536 条 `unresolved_neither` 统一保持一个仅审计类别；DuRetrieval 作为六单元 Gate 之外的预先声明辅助稳健性数据，不改变 RQ、Gate estimand、比较家族、门槛或当前确认性分母 |
| v16 | 2026-08-28 | 研究负责人要求把 DuRetrieval 与混合 C-MTEB Cmedqa 明确剥离、提升分享包在研究溯源中的地位，并正式建立 Internal Stress v6 | Gate A/B 均未运行；只查看公开实体的逐文本来源对账、历史资产计数和空 Query/qrel 状态，未观察任何新排序结果 | 冻结 C-MTEB Cmedqa 的四类精确来源 crosswalk；将分享包定义为假设来源/工程底座而非确认性分母；建立 Internal v6 数据 ID、三分目录、访问锁、摄取 schema 与资格台账，同时明确人口为空、P3-04 仅部分完成；不改变 RQ、Gate estimand、比较家族、门槛或最终分母 |
| v15 | 2026-08-28 | 研究负责人确认项目属于非商业科研并接受 cMedQA2 的使用治理；替代数据的 split/family 复核同时发现 80 个跨 split 规范化问题文本 family | Gate A/B 均未运行；未观察任何 cMedQA2 排序结果，只审计公开实体、标签结构、split ID、文本 family 与正例 answer ID | cMedQA2 正式替换许可不明的 MedicalRetrieval；冻结 Dev-exposed、Train-GateA-eligible、Test-GateB-eligible 资格方向及跨 split family 全排除规则；不改变 RQ、Gate estimand、比较家族或门槛，最终样本分母仍待构造率与功效分析 |
| v14 | 2026-08-28 | 原始 T2 Train 落盘后可以用 split-level 规则保守关闭丢失 11 个身份的曝光残余；备选审计又发现 C-MTEB Cmedqa 大部分是 DuRetrieval 背景，而上游 cMedQA2 有完整标签但受非商业/GPL 约束 | Gate A/B 均未运行；只读审计公开文件、历史资产与曝光来源 | 冻结 T2 Dev-exposed/Train-resplit 数据资格规则；排除 SQLite 乱码正文和 C-MTEB Cmedqa 混合 corpus 进入语义快照；记录 cMedQA2 优先替代候选但不在用户确认前改变三数据集分母；不改变 RQ、Gate estimand、比较家族或门槛 |
| v13 | 2026-08-28 | 数据覆盖审计发现单一四值关系标签混合来源相关性、目标事实关系与方法可裁决性；研究负责人同意继续按正交 schema 推进；同轮公开实体与历史曝光审计关闭了 P3-01 | Gate A/B 均未运行、未查看任何确认性结果；只读历史工程结果仅用于资产/曝光恢复，未用于定义标签或选择结果方向 | 收紧 P2 标注、C1 处理/对照资格、C2 可识别性边界和 P4 快照字段；固定历史 Query 条件化 T2 子池不得进入确认性候选生成；不改变 RQ、H1—H4、Gate estimand、比较家族或门槛 |

## 12. 概念速查

> **概念解释｜RAG、Query、Chunk 与 Candidate**：RAG 是先检索证据再生成答案的系统；Query 是问题；Chunk 是可检索文本单元；Candidate 是某个 Chunk 在特定 Query 下被召回后形成的候选。

> **概念解释｜Dense、Learned Sparse 与 BM25**：Dense 用稠密向量表示整体语义；Learned Sparse 学习少量重要词项及权重；BM25 依据关键词出现、频率和稀有度评分。三者可能互补，也可能产生不同噪声。

> **概念解释｜原始分数、归一化分数与排名**：不同检索器的原始分数量纲不同；归一化把它们变到较可比尺度；排名表示候选在单路中的相对位置。三种信息要同时保存。

> **概念解释｜LTR 与 LambdaMART**：LTR 是让模型学习排序；LambdaMART 用梯度提升树根据特征学习候选先后。本文的 LTR-v3 是已有工程强基线。

> **概念解释｜特征、消融与诊断基线**：特征是模型读取的数值信号；消融是移除一组特征再比较；诊断基线用于排除更简单的解释，而不是单纯增加基线数量。

> **概念解释｜构念与操作化**：构念是研究概念，例如“事实冲突型相似拥挤”；操作化是把它变成可重复计算和标注的规则。

> **概念解释｜离线真值与可观测代理**：离线真值来自 qrels 和人工复核；真实推理时只能看到文本、分数、排名等信息，用它们估计风险的量叫代理。

> **概念解释｜主效应与交互效应**：主效应问单个因素是否有影响；交互效应问一个因素的影响是否随另一个因素改变。H2 关心相似度的伤害是否在事实冲突条件下更强。

> **概念解释｜Clean、Stress、处理与对照**：Clean 是无目标干扰的基准池；Stress 是加入压力候选后的池；事实冲突是主要处理，事实等价是良性对照。

> **概念解释｜候选超集、候选池与 K**：候选超集是深召回形成的大备选库；候选池是实际交给排序方法的固定集合；K 是池大小。

> **概念解释｜反事实与原子变换**：反事实尽量保持文本其他部分不变，只改变关键事实；原子变换表示一次只改版本、数字、否定或条件中的一个。

> **概念解释｜自然样本与合成样本**：自然样本来自原始语料，现实性强但控制弱；合成样本按规则构造，控制强但可能有人工痕迹，必须分开报告。

> **概念解释｜Train、Tune、OOF、Blind 与 OOD**：Train 用于拟合；Tune 用于选择阈值和超参数；OOF 是开发集内部的折外预测；Blind 在开发期间不可见；OOD 来自不同领域或分布。

> **概念解释｜预注册与 Seal**：预注册是在正式结果前冻结假设、指标和分析；Seal 是封存数据、模型和代码，揭盲后不得回调。

> **概念解释｜EG-nDCG、MRR、Hit 与 Recall**：nDCG 同时考虑相关等级和排名位置；MRR 看首个正确组有多靠前；Hit 看前 k 是否有正确组；Recall 看找回了多少正确组。EG 表示同一等价事实组最多计一次。

> **概念解释｜nAUDC**：nAUDC 是归一化退化曲线面积，把多个干扰剂量下相对 Clean 的损失汇总为一个数。数值越小表示从低剂量到高剂量的累计退化越弱；它只在各剂量都存在的同一批 Query 上计算。

> **概念解释｜Win/Tie/Loss、负收益率与最坏 10%**：它们分别统计每个 Query 变好、持平、变差，变差比例，以及受伤最严重的一部分 Query，防止平均值掩盖局部失败。

> **概念解释｜置信区间、统计显著和实际效应**：置信区间表示估计的不确定性；统计显著说明零差异不太符合数据；实际效应说明差异是否大到值得投入。三者不能互相替代。

> **概念解释｜Prevalence 与 PR-AUC**：Prevalence 是冲突正类比例；PR-AUC 汇总不同阈值的精确率与召回率。在类别不平衡时，代理至少应明显优于 prevalence 基线。

> **概念解释｜非劣界 \(\delta\)**：它规定新方法在 Clean 上最多允许下降多少。CI 下界必须高于 \(-\delta\)，才能认为没有出现不可接受的普通场景损失。

> **概念解释｜Manifest、revision、SHA 与指纹**：Manifest 是实验装箱单；revision 是版本；SHA/内容摘要用于识别文件内容；指纹记录模型、代码、配置和环境。它们共同回答“这次实验究竟用了什么”。

> **概念解释｜pp（百分点）**：百分比从 70% 到 77% 是增加 7 个百分点，不等于相对增长 7%。

## 13. 核心参考来源

本文件只保留直接依赖的来源；完整证据覆盖为[文献地图](robust-fusion-literature.md)中的 45 个本地论文实体证据卡，以及 2 个仅核验官方元数据与摘要的外部近邻卡。

1. [Language Model Re-rankers are Fooled by Lexical Similarities](https://aclanthology.org/2025.fever-1.2/).
2. [Hybrid and Collaborative Passage Reranking](https://aclanthology.org/2023.findings-acl.880/).
3. [Balancing the Blend: An Experimental Analysis of Trade-offs in Hybrid Search](https://www.vldb.org/pvldb/vol19/p1715-gao.pdf).
4. [RARE: Redundancy-Aware Retrieval Evaluation Framework for High-Similarity Corpora](https://aclanthology.org/2026.acl-long.923/).
5. [Contextual Relevance and Adaptive Sampling for LLM-Based Document Reranking](https://aclanthology.org/2026.acl-long.94/).
6. [Regulatory Compliance through Doc2Doc Information Retrieval](https://aclanthology.org/2021.eacl-main.305/).
7. [An Analysis of Fusion Functions for Hybrid Retrieval](https://doi.org/10.1145/3596512).
8. [MoR: Better Handling Diverse Queries with a Mixture of Sparse, Dense, and Human Retrievers](https://aclanthology.org/2025.emnlp-main.601/).
9. [QuDAR: Query-Wise Dual-Perspective Adaptive Retrieval](https://aclanthology.org/2026.acl-long.1791/).
10. [Towards Robust Ranker for Text Retrieval](https://aclanthology.org/2023.findings-acl.332/).
11. [Hard Negatives, Hard Lessons](https://aclanthology.org/2025.findings-emnlp.481/).
12. [DocReRank](https://aclanthology.org/2025.emnlp-main.436/).
13. *Temporal Validity in Retrieval Memory: Eliminating Stale-Fact Errors for AI Agents over Evolving Knowledge*. DOI: `10.48550/arXiv.2606.26511`.
14. *FinSAgent: Corpus-Aligned Multi-Agent RAG Framework for Evidence-Grounded SEC Filing Question Answering*. DOI: `10.48550/arXiv.2607.18102`.

本次文献工作是定向检索，不是系统性综述。正式写论文前必须更新检索，并继续使用限制性新颖性措辞。第 13—14 项已核验官方元数据和摘要，但尚未作为本地 PDF 逐页阅读，不能据此引用摘要以外的细节。
