# 高相似度干扰下检索增强生成的多路来源感知鲁棒融合方法研究：主张—证据—空缺表

> 用途：把[定向文献地图](robust-fusion-literature.md)转成可以直接约束引言、研究问题、方法定位和结论措辞的证据台账。
> 对应方案：[科研协议](robust-fusion-research.md)。
> 证据范围：截至 2026-08-28 的 45 个本地论文实体、48 份本地 PDF，以及本表列出的外部一手论文页面；两项新增 2026 近邻工作目前只核验官方元数据与摘要。
> 文档状态：`P1-01—P1-05` 已完成；最相近工作的边界、最低强基线范围和引言问题链均已冻结。

> **概念解释｜主张—证据—空缺表**：`主张`是论文准备表达的判断；`证据`是已有研究实际证明到哪一步；`空缺`是证据尚未覆盖、需要本研究亲自检验的部分。它的作用不是罗列读过的论文，而是防止把研究假设误写成已有事实，也防止把已有工作误写成本文首创。

## 1. 使用与判定规则

### 1.1 证据等级

| 等级 | 含义 | 在论文中的用法 |
| --- | --- | --- |
| `A 直接证据` | 一手实证直接研究相同或非常接近的现象、关系或方法 | 可作为引言中的已有发现，但仍须保留数据、模型和任务条件 |
| `B 邻接证据` | 一手实证研究了相邻任务、相邻系统层或部分机制 | 可用于提出合理研究动机，不能直接替代本研究的实证 |
| `C 方法/测量依据` | 支持实验设计、指标或数据治理，但不证明核心现象 | 可说明为什么采用某种设计，不能写成结果性结论 |
| `H 待检验假设` | 多篇文献的联合推论或本项目提出的新机制 | 只能写成 RQ、假设或研究空缺，必须由新实验决定是否成立 |

> **概念解释｜联合推论**：两篇论文分别证明 A 和 B，并不等于已经证明“A 导致 B”或“A 与 B 的组合有效”。把多项已有发现连接成一个新的、可检验判断，称为联合推论；它仍然是待验证假设。

### 1.2 三条硬规则

1. `A/B/C` 说明已有文献能支持什么；`H` 说明本研究必须自己证明什么。任何 `H` 在 Gate A/Gate B 前都不得改写为确定事实。
2. “未检索到”只表示在本次定向检索、当前关键词和本地全文集合中未发现，不等于已经完成系统综述，也不支持“全球首次”。
3. 所有方法新颖性至少相对现有 `LTR-v3`、容量匹配的无类型局部对照 `D3` 和容量匹配的表面信息对照 `A0` 判断。文献中没有相同特征，不代表项目已有的 38 维特征可以重新声明为创新。

## 2. 核心主张—证据—空缺表

| ID | 拟写入论文的主张 | 最强证据及其真实边界 | 等级/当前状态 | 尚未被证明的空缺 | 本研究的处理 |
| --- | --- | --- | --- | --- | --- |
| C01 | 语义 Reranker 并不在所有候选分布中稳定优于词法基线。 | [Hagström et al., 2025](https://aclanthology.org/2025.fever-1.2/)比较 6 个 LM Reranker，在 NQ、LitQA2、DRUID 上发现其在 DRUID 中难以稳定超过 BM25，并用词法分离度定位易错区域。论文证明的是条件性失效及相关性，不是“所有语义 Reranker 都会被欺骗”。本地证据见[全文 pp. 1–16](<../papers/Language Model Re-rankers are Fooled by Lexical Similarities.pdf>)。 | `A`；已有发现 | C1 尚缺以等价证据为良性对照的固定候选池相似度×事实关系交互测量；C3 的多路保护则是另一个条件性待检验假设，不与 C1 拼成长合取式空缺。 | 作为 RQ1 的起点；C1 与 C3 分别给出 estimand 和否证条件，不得声称首次发现 Reranker 失效。 |
| C02 | 文本或语义高度相似不等于任务相关；时间、版本、实体关系和适用条件可能改变标签。 | [Regulatory DOC2DOC IR](https://aclanthology.org/2021.eacl-main.305/)显示相似 query-document 对可具有相反标签，神经重排会受冲突监督影响，日期过滤在部分方向上有效；其任务是 EU/UK 法律长文档关系检索，不是一般 RAG Chunk。另有 DocReRank、DuReader 对年份、实体、数值、修饰语等难例的证据。本地证据见[Regulatory pp. 2–9](<../papers/Regulatory Compliance through Doc2Doc Information Retrieval: A case study in EU／UK legislation where text similarity has limitations.pdf>)。 | `A`；已有发现 | 尚未证明四类约束在本文中文/内部 Chunk、三路候选和冻结 Reranker 中造成同样退化。 | 支撑版本/时间、数字、否定、适用条件四类冲突；具体效应交给 RQ2。 |
| C03 | 高相似候选不是同一种处理：它既可能是等价证据，也可能是事实冲突干扰。 | [RARE](https://aclanthology.org/2026.acl-long.923/)证明高相似冗余中存在可替代的等价事实证据；Regulatory DOC2DOC 显示相似候选可有相反任务标签；*Temporal Validity in Retrieval Memory*（DOI `10.48550/arXiv.2606.26511`）进一步报告余弦相似度区分矛盾与重复事实的 AUROC 约为 0.59。三者任务不同，均未直接完成本文固定候选池中的“等价/冲突 × 连续相似度”排序交互。 | `A/B/H`；一般分离现象已有依据，本文交互仍待检验 | 高相似事实冲突是否比同样相似的事实等价对照造成额外 Reranker 排序伤害，现有文献未直接回答。 | 以连续交互为主、2×2 为复核；H1/H2 和 Gate A 直接检验差异，不声称首次发现矛盾事实仍可高度相似。 |
| C04 | 高冗余语料若只标 canonical Gold，会把有效等价证据误计为错误并改变指标含义。 | [RARE](https://aclanthology.org/2026.acl-long.923/)将文档拆成 atomic facts 并追踪跨 Chunk 等价关系，明确指出忽略冗余会低估有效检索；[T²Ranking](<../papers/T2Ranking: A large-scale Chinese Benchmark for Passage Ranking.pdf>)、[DuReader](https://aclanthology.org/2022.emnlp-main.357/)也说明 pooling 深度和漏标会改变评测。RARE 的等价链接本身仍缺独立人工 precision/recall 审计。 | `A/C`；已有测量依据 | 本研究数据中的等价组仍需人工定义和审计，不能直接复用别的数据集结论。 | 主指标采用 equivalence-group-capped 指标；官方 qrels 另报，单个原 Gold 排名只作敏感性分析。 |
| C05 | 越接近决策边界的 Hard Negative 越需要单独审计 false negative 风险。 | [Hard Negatives, Hard Lessons](https://aclanthology.org/2025.findings-emnlp.481/)显示修复错误负标签后，增加困难负例仍可有益；[DocReRank](https://aclanthology.org/2025.emnlp-main.436/)以最小属性改写构造难负例，但人工检查仍发现残余假阴性；DuReader 也报告 qrels 修正会改变同模型指标。 | `A`；已有发现 | 哪种生成/筛选规则能在本文数据上同时保证相似度与标签可信度，不能由现有结果代替。 | 合成反事实一次只改一个事实单元；保存父 Chunk、变更记录和理由；自然难负例与最高相似项进入重点复核。 |
| C06 | 多路检索的收益取决于互补性和每路质量；增加路径不保证更好，弱路可能拖累融合。 | [Balancing the Blend](https://www.vldb.org/pvldb/vol19/p1715-gao.pdf)在多数据集、多路径组合中观察 weakest-link；MoR、QuDAR 和法律域混合检索也显示最佳路与融合收益依 Query、领域和监督条件变化。该证据针对一般混合检索权衡，不是事实冲突拥挤。 | `A/B`；已有发现 | 尚不清楚高相似事实冲突时，哪一检索路保留了可用于候选级纠错的局部证据。 | 支撑“来源感知”的必要性；用分路 score/rank margin 检验局部判别信息，而不是预设某一路恒优。 |
| C07 | RRF、归一化分数加权和学习融合都是既有方法，不能作为本文算法首创。 | [Fusion Functions](https://doi.org/10.1145/3596512)系统分析 RRF 与归一化凸组合的条件性；[RRF 原文](<../papers/Reciprocal Rank Fusion outperforms Condorcet and Individual Rank Learning Methods.pdf>)给出免分数校准的名次融合；项目自身已有 38 维 `LTR-v3`。 | `A`；新颖性边界已确定 | 现有方法是否能在本文压力条件下保持稳定仍需实测，但“使用这些方法”本身没有新颖性。 | 固定加权、RRF、LTR-v3 均为强基线；贡献只能来自冲突条件化的增量。 |
| C08 | 利用候选列表上下文、候选间相似结构或协作关系进行重排已经存在。 | [HybRank](https://aclanthology.org/2023.findings-acl.880/)用 sparse/dense 上游相似度和共同 anchors 建模候选协作；[Contextual Relevance](https://aclanthology.org/2026.acl-long.94/)证明 LLM 判断会受候选批次组成和顺序影响。二者都未把局部关系类型化为事实等价/冲突。 | `A`；新颖性边界已确定 | 普通候选上下文是否足以解释收益，还是类型化事实冲突有独立价值，仍未回答。 | 不宣称首次使用候选邻域；以 D3 容量匹配的无类型局部邻域排除“只是多加邻域特征”的解释。 |
| C09 | 查询级自适应融合、检索器选择和 margin-based confidence 已经存在。 | [MoR](https://aclanthology.org/2025.emnlp-main.601/)做逐 Query 多检索器软加权；[QuDAR](https://aclanthology.org/2026.acl-long.1791/)用 Top1–Top2 分数间隔和 LLM relevance 为 sparse/dense、原始/扩展查询动态赋权。它们处理整路或整 Query 的可靠性，不是候选相对事实冲突近邻的 margin。 | `A`；新颖性边界已确定 | “冲突近邻条件化的候选级分路优势”是否有独立增量尚无直接证据。 | 门控退出主论文；不得声称首次使用 margin 或动态多路融合，只检验 conflict-conditioned local margin。 |
| C10 | 用多 Retriever 产生 Hard Negative 并重训更鲁棒的 Ranker 已经存在。 | [R²ANKER](https://aclanthology.org/2023.findings-acl.332/)联合 BM25、dense、learned sparse 产生训练负例；HYRR 研究训练候选来源变化的稳健性。它们改变 Ranker 训练，且主要基于英语检索基准。 | `A`；新颖性边界已确定 | 冻结现成 Reranker、只在推理期融合层缓解事实冲突的路线尚未由这些工作回答。 | 明确把“大 Reranker 重训练”排除出范围；以冻结模型强调方法边界，而不是宣称训练路线无效。 |
| C11 | 生成模型受 hard distractor 影响的证据不能直接证明排序器退化。 | [The Distracting Effect](https://aclanthology.org/2025.acl-long.892/)和噪声研究测量生成阶段的回答/拒答变化；检索排序、证据利用和答案生成是不同被测层。 | `B/C`；层级边界已确定 | 生成端干扰强度与排序端错误晋升的对应关系仍未知，且不属于本论文主终点。 | 只用于说明“干扰”概念的相邻研究；主终点保持为排序指标与抗退化性。 |
| C12 | 只报告总体平均会掩盖一部分 Query 的显著损失。 | [Risk–Reward Trade-offs in Rank Fusion](https://doi.org/10.1145/3166072.3166084)直接研究融合的查询级风险；现有项目 Blind v5 也出现总体正收益、真实搜索子集负收益，但历史项目结果只作动机。 | `A/B`；已有依据 | 本方法是否减少最坏 Query、负收益率和错误翻转必须由新样本确认。 | 除 nDCG@10 外，报告 Win/Tie/Loss、负收益率、最坏 10%、Top1 翻转与 nAUDC。 |
| C13 | 模型和检索策略的相对排名会随语言、领域、Query 和 qrels 口径改变。 | MTEB/MMTEB 展示任务和语言依赖；T²Ranking、DuReader、Multi-CPR 与 cMedQA2 展示中文检索中的候选池、分级/正负标签、领域监督和精确词项效应。它们不直接证明本文机制，但反对单数据集外推。 | `C`；设计依据 | 本文方法的跨域方向一致性尚无证据。 | 最低包使用 T2Ranking、已确认非商业本地使用边界的上游 cMedQA2 和独立内部集合；MedicalRetrieval 因许可不明退出确认性分母。公开数据与内部数据的结论分层报告。 |
| C14 | 固定候选池可以把研究对象限定为同一批证据上的排序直接效应。 | 这是由实验隔离目标导出的设计选择；现有检索/重排论文普遍受上游候选差异约束，但本次定向检索没有找到一篇能够替代本文固定池干预设计的直接因果证据。 | `C/H`；方法选择，不是已有结果 | 固定池实验本身能否显示稳定剂量—反应和相似度×事实关系交互，必须由轨道 A 数据决定。 | 各方法消费同一不可变候选快照；只把结果解释为“冻结上游后的排序直接效应”，轨道 B 另测外部有效性。 |
| C15 | 在控制现有 LTR-v3、无类型局部信息和表面构造痕迹后，类型化局部冲突与分路相对优势是否仍提供样本外判别增量，是一个尚待检验的方法假设。 | HybRank 说明候选关系可提供附加信号；QuDAR 说明 margin 可用于可靠性估计；Regulatory 说明精确关系可能推翻文本相似性。这些工作只为假设提供邻接依据，不自动证明 M1。 | `H`；核心方法假设 | M1 是否优于 LTR-v3、density-only、query-constraint-only、容量匹配 D3 和表面特征 A0，完全未知。 | 作为 H3/H4 和 RQ3；以独立 estimand、容量匹配对照和 Blind 增量判定。Gate B 未通过时，不得保留方法贡献结论。 |
| C16 | 本方法只有在真实增量延迟、内存和离线准备成本达标时，才可称为低成本。 | Balancing the Blend、MoR、QuDAR 等显示“training-free”“模型较小”或调用次数少不等于总成本低；多路索引、全路执行、查询扩展和 LLM 评分都可能主导成本。 | `C/H`；待测 | Top-M 邻域和约束抽取在真实 K、M、模型与硬件上的成本尚未测量。 | 报告 p50/p95、峰值内存、索引/特征准备和增量成本；成本门槛未成立时删除“低成本”措辞。 |
| C17 | 可辩护的新颖性必须由自立贡献承担，不能依赖“没有工作同时满足一长串条件”的合取。 | C01–C16 显示相似干扰、等价冗余、多路融合、候选协作、margin、自适应融合和 hard-negative 训练均已有先例；新增时间有效性与金融问答工作又直接接近“相似度不等于证据有效性”的动机。 | `H`；检索范围内的空缺判断 | 当前尚未识别到直接估计“等价对照下相似度×事实冲突排序伤害”的工作，也未识别到把分歧分为可检测、条件可裁决、不可识别并据此约束排序干预的同题研究；但这仍是检索有界判断。 | C1 作为主要测量贡献，C2 作为诊断贡献，C3 作为条件性方法贡献；分别给出 estimand、falsifier 和强对照，禁用长合取式首创论证。 |
| C18 | 在动态知识环境中，embedding similarity 可能几乎不能区分事实矛盾与语义重复。 | *Temporal Validity in Retrieval Memory*（DOI `10.48550/arXiv.2606.26511`）在校准数据上报告 contradiction-vs-duplication cosine AUROC 约 0.59，并以 subject–relation–object supersession 处理旧事实。当前只核验官方摘要，且研究对象是演化记忆，不是静态候选池重排。 | `B`；近邻实证 | 该结果不能替代本文 C1 的固定池排序交互，也不能证明 BM25/Sparse/route evidence 可以裁决正确项。 | 用作动机和新颖性边界；禁止把“相似度无法识别矛盾”写成本文首次发现。 |
| C19 | 特定长文金融问答中，语义重排会偏爱主题相似但证据无效的 false-positive Chunk。 | *FinSAgent*（DOI `10.48550/arXiv.2607.18102`）的官方摘要将 prior-corpus misalignment 表述为问题驱动的 query generation 与 semantic ranking 共同造成的管线级错位，并报告 semantic reranking 会偏爱主题相近但证据无效的 false-positive Chunk；其方法包含 multi-path retrieval 和 learned feature-gated reranker。当前只核验官方摘要，尚未逐页确认特征、训练、对照和消融细节。 | `B`；应用层近邻证据 | 该工作未由已核验摘要证明等价—冲突受控交互、固定候选池因果隔离或本文的可识别性分区；但它显著压缩“现象首次发现”和泛化方法表述。 | 作为独立动机并列引用；C3 必须相对 LTR-v3、D3 与 A0 证明增量，不能用“语义相关≠证据有效”本身声称创新。 |
| C20 | `linkrag-eval-sqlite-share-20260827` 是本研究问题的经验起点和工程可行性底座，但不是确认性分母。 | [SQLite 与检索资产对账报告](../reports/sqlite_share_restore_and_asset_reconciliation_2026_08_28.md)证明分享包、本地工作副本、旧 eval MySQL 和检索资产的 ID/计数对应关系；历史三路、LTR-v3 和 Blind 结果提供提出问题的经验背景。两端 Query/qrel 都为 0，历史 Blind 已曝光。 | `C`；研究 provenance 与工程依据 | 分享包不能回答事实冲突相对等价对照的 Gate A estimand，也不能从聚合结果恢复行级关系标签。 | 正式写作可说明研究缘起、已有系统和工程可行性；不得把 51 run/2,884 aggregate metric 写成 C1/C2/C3 证据。 |
| C21 | C-MTEB Cmedqa compact corpus 不是纯上游 cMedQA2 corpus，且必须与独立 DuRetrieval 数据集分开描述。 | 固定 revision 的逐条原文 SHA-256 crosswalk 将 100,001 条分为 88,242 DuRetrieval-only、7,137 cMedQA2-only、2,086 both、2,536 unresolved；v2 制品为 `ROBUST-FUSION-CMEDQA-PROVENANCE-PEEL-2026-08-28-v2`。 | `C`；数据治理直接证据 | 精确 membership 不能恢复未文档化生成流程；`both` 无法排他归因；全部 2,536 条 unresolved 统一停留在一个仅审计类，不再追认来源。 | Crosswalk 只用于 provenance/曝光；正式 cMedQA2 corpus 回到 pinned 上游实体，医学域只作预注册分层属性；unresolved 不按 qrel 单列、不回配、不专项标注、不删除、不作正式语义输入。 |
| C22 | DuRetrieval 的数据实体可独立于 C-MTEB Cmedqa 完整保留。 | v2 manifest 对固定 C-MTEB DuRetrieval data/qrels revisions 和三个文件 SHA-256 做硬校验，复现 100,001 个唯一 corpus ID/文本、2,000 个唯一 Query ID/文本、9,839 个唯一且引用有效的 `score=1` qrel pair，并记录三个实体 `rows_removed=0`。 | `C`；数据完整性直接证据 | 当前“完整”只覆盖 pinned C-MTEB compact revision，不证明上游约 800 万 passage 全量 DuReader corpus 已取得，也不提供新的确认性主单元。 | DuRetrieval 作为独立完整的辅助稳健性数据保留；不因 Cmedqa 重合扣行或合并，且不得在结果可见后临时改成当前六单元 Gate 的备用路径。 |

## 3. 可以直接用于引言的证据链

以下不是最终论文文本，而是引言各段应承担的论证功能。每一步都只推进一个判断。

| 引言步骤 | 可写的受限主张 | 核心证据 | 下一步留下的问题 |
| --- | --- | --- | --- |
| 1. 现象 | 语义 Reranker 在部分真实或困难候选分布中未稳定兑现相对 BM25 的优势。 | C01 | “困难”究竟来自什么？ |
| 2. 任务相关性 | 语义/词法相似不能替代版本、时间、数字、否定和适用关系；矛盾与重复事实可能仍有近似 embedding 分数。 | C02、C18 | 高相似本身是否一定有害？ |
| 3. 对照必要性 | 高相似可表示等价证据，也可表示事实冲突；canonical qrel 还可能误罚等价证据。 | C03–C05 | 如何分离冗余占位与错误关系？ |
| 4. 多路条件性 | sparse/dense/BM25 的误差可能互补，也可能形成 weakest-link，固定融合不能保证逐 Query 稳定。 | C06–C07 | 能否从现有路由证据识别局部风险？ |
| 5. 邻近方法边界 | 候选协作、查询级门控、margin、多源 hard-negative 重训和证据有效性门控已有先例。 | C08–C10、C19 | 哪个尚未覆盖的增量仍值得研究？ |
| 6. 研究空缺 | 缺少等价对照下的连续事实冲突交互测量，以及可检测/可裁决/不可识别的诊断分区；融合方法只能作为二者成立后的条件性贡献。 | C14–C19 | 进入 RQ1—RQ3、H1—H4。 |

建议的空缺表述为：

> 现有研究已经观察到语言模型重排器在相似候选中的条件性失效、矛盾事实与重复事实的 embedding 分数难以分离，以及特定领域中主题相似但证据无效的候选会获得高分。本文不把这些一般现象据为首创。其主要空缺是：在固定候选池中，以同样相似的事实等价证据为良性对照，估计事实冲突的额外交互伤害；随后验证哪些分歧仅可检测、哪些能够由推理期证据条件性裁决；只有这两项成立后，才检验局部冲突条件化的检索路融合是否提供样本外增量。

这段话允许进入研究方案和论文草稿；“首次提出”“首次发现”“彻底解决”不允许进入。

完整的七步引言骨架已写入[科研协议第 2.4 节](robust-fusion-research.md)，后续论文写作应以该版本为起点，不再从文献清单重新拼接论证。

## 4. 最相近工作的边界核验

| 工作 | 它已经做了什么 | 它没有做什么 | 对本研究的直接约束 |
| --- | --- | --- | --- |
| Hagström et al. (2025) | 多 Reranker、多数据集、词法分离度与易错分组 | 无事实等价/冲突 2×2、无剂量曲线、无多路缓解 | 现象不能首创；RQ1 必须比“分组相关性”更强 |
| Balancing the Blend (2026) | 多路径组合、效果—成本、weakest-link | 无事实错误型拥挤、无冻结池方向翻转 | 多路不自动有益；必须解释风险来自哪一路和何种候选 |
| HybRank (2023) | sparse/dense 上游相似度、候选协作、插件式重排 | 无类型化事实冲突、无本文 2×2 | 邻域/协作不能首创；D3 必须排除普通邻域解释 |
| RARE (2026) | 高相似高冗余语料、atomic facts、等价证据评测 | 不研究语义 Reranker 晋升事实错误项，也不提出本文融合方法 | 等价组评测不能首创；事实等价必须作为对照而非负例 |
| Regulatory DOC2DOC (2021) | 相似文本相反标签、关系/时间约束、神经重排受冲突监督影响 | 长文法律关系任务，非三路 RAG Chunk 压力实验 | 精确约束机制已有依据，但跨任务效应要重做 |
| Contextual Relevance (2026) | 候选批次组成和顺序会改变 LLM relevance judgment | 不研究本文四类事实冲突或低成本路由特征 | 必须控制候选顺序；不能把一次 setwise 结果当稳定真值 |
| MoR / QuDAR | 逐 Query 动态多路融合；QuDAR 使用 score gap/margin | 不以冲突近邻为比较集合，不是候选级类型化排序保护 | 门控和 margin 不能首创；本文只保留 conflict-conditioned local margin |
| R²ANKER / HYRR | 多 Retriever 生成训练负例，重训 Ranker 获得候选源稳健性 | 不冻结 Reranker，不做本文推理期小增量 | 需明确“冻结模型、融合层缓解”的工程与科研边界 |
| DocReRank / Hard Negatives | 可控最小反事实、难负例质量与 false-negative 审计 | 不回答本文多路来源感知排序问题 | 合成构造必须可追溯；困难度不能替代标签可信度 |
| Temporal Validity in Retrieval Memory (2026) | 报告矛盾与重复事实的余弦相似度近乎难分，并提出动态事实 supersession | 演化记忆任务；不测固定池 Reranker 排序、等价对照交互或多路融合 | 一般表示缺口不能首创；C1 必须测量排序层面的额外伤害 |
| FinSAgent (2026) | 在 SEC filing QA 中观察 semantic reranking 偏爱主题相近但证据无效候选，并提出 multi-path retrieval 与 learned feature-gated reranker | 当前摘要不足以证明本文受控交互、可识别性分区或相对 LTR-v3/D3/A0 的同题增量 | 该现象和这类 feature-gated remedy 不能作为本文首创；C1/C2/C3 必须分别立证 |

## 5. 当前证据不足、必须由本研究回答的事项

下列内容目前没有现成文献可以替我们完成，因此只能作为待检验主张：

1. 高相似事实冲突相对高相似事实等价是否造成额外的 Reranker 排序退化；
2. 退化是否随干扰数量和相似强度形成可重复剂量—反应；
3. 版本/时间、数字、否定、适用条件四类冲突中，哪些机制稳定存在，哪些只在特定领域出现；
4. 推理期可见的局部冲突代理是否真的测到离线人工真值，而不是一般相似密度；
5. 冲突条件化的分路 score/rank margin 是否比已有 route count、共同召回和普通 Top-M 邻域提供样本外增量；
6. M1 的 Stress 收益能否在不超过预注册 Clean 非劣界的前提下成立；
7. Top-M 方案是否满足预先冻结的成本门槛；
8. 结果能否在两个独立 Reranker、两个公开中文数据集和一次性内部 Blind 中保持方向一致。

## 6. 结论措辞护栏

### 6.1 现在即可写入研究方案

- “已有研究表明，语义 Reranker 的优势依赖候选分布，并可能在相似候选压力下退化。”
- “文本相似性不能替代版本、时间、数字和适用关系等任务约束。”
- “高相似候选既可能是等价证据，也可能是事实冲突，因此实验必须设置良性冗余对照。”
- “多路检索的净收益依赖互补性和弱路噪声，RRF、加权融合、候选协作和查询级自适应均已有先例。”
- “本文提出并检验一个尚未确认的假设：类型化局部冲突和分路局部优势可为冻结 Reranker 提供排序保护。”

### 6.2 只有实验成立后才可写

- “高相似事实冲突造成了超出等价冗余的额外退化。”
- “局部冲突代理具有基本构件效度，并对既有 LTR 特征提供增量信息。”
- “M1 相对 LTR-v3、D1—D3 和容量匹配的表面对照 A0 降低了预注册 Stress 条件下的退化，且 Clean 性能满足非劣性要求。”
- “在已测试数据集、模型和候选预算内，该方法表现出跨域方向一致性或较低增量成本。”

### 6.3 无论结果如何均不得写

- “本文首次发现语义 Reranker 会被 Hard Negative 欺骗。”
- “本文首次提出 sparse/dense/BM25 来源感知融合、候选邻域或 margin。”
- “高相似度天然有害。”
- “LambdaMART 普遍优于语义 Reranker。”
- “检索排序改进必然提升生成答案质量。”
- “本方法已经解决 RAG 的相似干扰或提供安全保证。”
- “未发现同题论文，所以本研究全球首创。”

## 7. 本表得出的研究收束

文献没有要求本研究改题，也没有支持继续扩张到图学习、策略门控、强化学习干扰生成或重训大 Reranker。更稳妥的研究方法是保留当前主题，并把贡献压缩为三层：

1. **现象层**：用固定候选池和完整 2×2 证明“事实冲突型相似拥挤”是否构成超出良性冗余的排序压力；
2. **机制层**：验证局部冲突代理和分路相对优势是否与错误晋升相关，且不是纯密度或单候选约束的替代说法；
3. **方法层**：只在现有 `LTR-v3` 上加入 Top-M 类型化局部冲突和 conflict-conditioned route margin，并要求相对 LTR-v3、容量匹配 D3 和表面对照 A0 的样本外增量，以及跨域、Clean/Stress 和成本证据同时成立。

`P1-03` 已冻结：Gate A 前不复现 HybRank/QuDAR；Gate A = `Go` 后，最低发表包同时使用容量匹配的 D3 承担“普通邻域特征是否已经解释收益”的对照，使用容量匹配的 A0 承担“表面或构造痕迹是否已经解释收益”的对照。只有 Gate A = `Go` 后，才根据投稿目标、官方产物可用性和独立计算预算决定是否增加一个完整近邻强方法；涉及显卡训练时必须另行审批，不能默认计入当前研究成本。

## 8. 一手来源核验状态

截至 2026-08-28，已对下列最相近工作核对官方页面元数据、摘要和本地全文证据边界：Hagström et al.、HybRank、RARE、Regulatory DOC2DOC、Contextual Relevance、MoR、QuDAR、R²ANKER、Hard Negatives, Hard Lessons、DocReRank。Balancing the Blend 与 Fusion Functions 以正式 PDF/DOI 和本地全文为准。*Temporal Validity in Retrieval Memory* 与 *FinSAgent* 目前只核验官方 arXiv 元数据和摘要，未标记为本地全文已读。详细逐篇证据、页码和 45 个本地实体的完整覆盖仍以[文献地图](robust-fusion-literature.md)为权威入口。
