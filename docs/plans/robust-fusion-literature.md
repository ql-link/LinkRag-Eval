# 高相似度干扰下检索增强生成的多路来源感知鲁棒融合方法研究：文献地图

> 证据更新至 2026-08-28。本文档主体是对 [`docs/papers/`](../papers/) 当时本地全文快照的逐篇阅读与跨文献综合；页码均指链接所指本地 PDF 的文件页码。第 4.4 节另列未纳入本地 PDF 快照的外部来源，各项分别说明既有核验范围。
> 使用身份：这是历史阅读记录，原稿中的研究设想不作为当前方法或实验约束。2026-09-06 将旧证据表独有的 15 个出版链接并入既有卡片及 E03；本次未重新核验论文。旧表中的项目来源结论已有[数据来源审计](../reports/robust_fusion_gate_a_data_coverage_audit_2026_08_28.md)和[资产对账报告](../reports/sqlite_share_restore_and_asset_reconciliation_2026_08_28.md)承载，不重复建立证据表。

> 2026-09-06 文件去重说明：仅删除 016 的字节级重复 PDF，主文件哈希不变。当前目录为 47 个 PDF、45 个论文实体；第 1 节和第 5 节仍记录 2026-08-28 的 48 文件历史盘点，不改写当时预检／OCR 结果。本次未重新阅读或核验论文内容，删除与恢复依据见[重构执行记录](runtime-simplification-2026-09-06.md#recovery)。

## 1. 历史状态与覆盖（2026-08-28）

| 审计项 | 结果 | 解释 |
| --- | ---: | --- |
| 物理 PDF | 48 | `docs/papers/*.pdf` 全部纳入，无孤立文件 |
| 不同 SHA-256 | 47 | 仅有 1 组字节级完全重复副本 |
| 论文实体 | 45 | `48 - 1` 个重复副本 - 2 个 ACL/arXiv 版本对 = 45 |
| 文献卡 | 45 | 编号 001–045 连续，每个实体恰好一张卡 |
| 文件/实体覆盖 | 48/48；45/45 | 均为 100% |
| PDF 预检 | 48 `PASS` | 使用 `../LinkRag/.venv` 运行完整性预检；48 个文件的声明页数、枚举页数和读取器页数一致，且无解析告警 |
| 全文抽取/OCR | 48/48 | 每个物理 PDF 均有逐页文本；公式、表格、异常字符和关键数值按证据卡所述回看原页 |
| 外部近邻工作 | 2 | 已核验官方 arXiv 元数据与摘要，尚未逐页阅读，不计入 45 个本地论文实体 |

`PASS` 只证明页数声明、枚举和读取器结果一致且没有解析告警，不证明论文主张正确。OCR/文本抽取只用于定位和通读；遇到漏字、数学符号、表格或版式异常，以 PDF 原页为准。尤其是 016 的重复副本 OCR 只有页眉/页码，但两个 PDF 的字节、页数和 SHA-256 完全相同，因此这属于衍生文本缺失，不是论文内容缺失。

版本归并遵循“同一研究实体、不同物理文件”的口径：023 与 045 各有一组 ACL/arXiv 版本对；016 有一个字节级重复副本。两个名为 RARE 的实体不得合并：023 展开为 *Redundancy-Aware Retrieval Evaluation*，024 展开为 *Retrieval-Aware Robustness Evaluation*，题名、作者、任务和方法均不同。

## 2. 总体逻辑链

下面的七个环节存在先后依赖，后一个环节不能补偿前一个环节尚未定义或测量的问题。

### 2.1 数据与 qrel：先定义“什么算相关”

MTEB/MMTEB 说明模型名次依任务、语言和领域而变，覆盖数量不等于覆盖均衡；Multi-CPR、T²Ranking 与 DuReader 又表明，单一正例、分级多正例、pooling 深度和漏标会直接改变指标含义。法律 DOC2DOC 进一步显示，文本极相似的文档可能因制度关系错误而是严格负例；Redundancy-Aware RARE 则显示，同一事实的多个等价 passage 若只标一个 canonical qrel，会把有效检索误判为失败。【017，PDF pp. 2–11、42–48；018，pp. 1–10；006，pp. 3–8；020，pp. 2–7；023，pp. 1–9；028，pp. 2–5；032，pp. 1–9】

因此，第一步必须明确标签编码的是答案包含、分级满足、事实覆盖、制度关系、来源身份还是生成可用性，并审计假阴性、近重复、等价证据和数据泄漏。未完成这一步，模型分数变化无法被可靠归因。

### 2.2 结构与粒度：决定检索器能够看见什么

领域语料不是无结构字符流。术语、章节、父子条件、兄弟段落、关系邻域和来源权威性会共同决定证据边界。粗粒度保留上下文但增加冗余，细粒度提高定位精度却可能切断条件；图、树、摘要前缀和多粒度索引分别恢复不同类型的跨块信息，不能互相替代。【013，PDF pp. 4–9；035，pp. 2–8；038，pp. 4–8；039，pp. 3–8；042，pp. 2–8；043，pp. 2–10；044，pp. 1–13】

因此，数据定义之后应先确定 discovery unit 与 evidence unit：前者服务候选发现，后者必须保留足以判断答案、条件和出处的上下文。切块方式改变候选空间，不能仅凭最终生成分数反推切块机制优越。

### 2.3 互补检索：收益来自非冗余且可靠的剩余误差

RRF、归一化分数凸组合等方法只解决异构排序如何合并，不自动创造有效信息。稀疏、稠密、learned sparse 与 late interaction 的表示不同，并不保证错误互补；新增通道同时带来边际召回和高排噪声，净效果取决于两者之差。OOD 法律检索中互补更明显，域内微调强检索器后等权融合反而常稀释强信号；多路实验也观察到 weakest-link。【001，PDF pp. 10–25、29–36；002，pp. 7–11；011，pp. 7–8；014，pp. 3–8、18–20；021，pp. 1–8；026，pp. 1–2】

因此，合理顺序是先测每路质量与成功集合重叠，再选融合函数；“路数更多”或“模型异构”都不能替代互补性证据。

### 2.4 查询级适应：从总体平均转向当前查询的可靠性

固定权重只优化平均查询。DAT、MoR 与 QuDAR 分别从各路 Top-1、语料熟悉度、结果结构、分数间隔或 LLM 可答性估计逐查询权重；R³AG 把“不检索”与多个检索器统一为动作；INKER、ReflectiveRAG 和 SA-RAG 又把何时继续、如何改写、是否补证据及何时终止纳入控制流。【003，PDF pp. 4–12；012，pp. 4–16；019，pp. 3–8、16–19；022，pp. 2–9；027，pp. 2–8；029，pp. 1–9；030，pp. 3–13】

这一层解决的是是否融合、融合哪些路、干预多强和何时停止。其代价是控制器本身成为新的误差源：Top-1 未必代表整路，LLM judge 可能失准，路由效用依赖生成器，全路并行或多轮检索也未必降低总成本。

### 2.5 候选集重排与难负例：学习局部决策边界

首阶段候选确定后，排序质量取决于榜内细微差异。RankNet/LambdaRank/LambdaMART 将成对错序与榜首指标效用连接；HybRank 用共同 anchors 的关系矩阵建模候选协作；Setwise LLM 工作则证明批次组成与顺序会改变判断，必须把 contextual relevance 视作相对于采样分布的操作量。【004，PDF pp. 1–9；008，pp. 2–18；011，pp. 2–10】

真正困难的局部边界常是“主题相同、表面相近，但实体、数字、年份、修饰语、句法方向或业务分部错误”。HYRR、R²ANKER 与 DocReRank 用多检索器或最小反事实构造困难监督；但 DuReader、DocReRank 与 Hard Negatives, Hard Lessons 同时说明，越接近决策边界越容易混入假阴性，故难度和标签可信度必须分开审计。【005，PDF pp. 1–9、15–18；006，pp. 6–8、12–13；009，pp. 3–5；010，pp. 1–9、19–20；016，pp. 1–16；036，pp. 1–13】外部近邻工作又分别报告矛盾与重复事实的余弦分数近乎难分，以及金融问答中主题相似但证据无效候选被语义重排偏爱的现象；这两项目前只支持摘要范围内的动机，不能替代本文的受控排序交互。【E01；E02】

### 2.6 噪声、冗余与安全：相关性之外的失败面

高相似语料中的冗余既可能提供替代证据，也可能占满 top-k，使多跳所需的其他事实缺失。语义近但不含答案的 distractor 通常有害；完全随机文本在特定数量、位置和模型下却可能条件性改善生成，二者不能合并成一个“噪声率”。主动攻击还会利用部分支持、证据冲突、软广告和拒答诱导，从知识库、检索结果或过滤后上下文的不同入口穿透系统。【023，PDF pp. 1–9、17–19；027，p. 4；031，pp. 1–13；033，pp. 3–14；034，pp. 2–9】

法律检索又增加来源、时间和正式关系约束：内容相似但来自错误文件，或与目标法规只有修订而非转置关系，不能视为可靠证据。可靠性因此不是单一相关性分数，而是事实多样性、来源身份、关系、时间、答案承载、位置与攻击权限的组合条件。【028，PDF pp. 2–9；035，pp. 2–12】

### 2.7 分层评测：分别测量数据、检索、利用、生成、安全与成本

检索指标仍是必要上限，但必须声明 qrel 密度、pooling、分级标签、top-k 和未标文档处理。高冗余场景需要事实级 Coverage、等价证据集合和全部所需事实命中的 PerfRecall；路由系统需要选择率、静态最佳、逐查询 oracle headroom 与调用成本；噪声和安全需要分类型、分入口报告；拒答需要同时报告回答覆盖、条件正确率和拒答代价。【017，PDF pp. 42–45；019，pp. 4–8、17–19；023，pp. 4–9；024，pp. 8–10、31；031，pp. 5–8；032，pp. 8–9】

最终还要单独测“模型是否利用了证据”。DRUID/ACU 显示真实检索中约一半证据不足，答案正确与上下文被正确利用不是同一量；结构化引文也只是可审计接口，不自动证明引文支持答案。【039，PDF pp. 5–8；045，PDF pp. 5–10、20–30】

压缩后的链条是：

**任务相关性与 qrel → 结构保持的检索粒度 → 经验证的通道互补 → 查询级融合/路由 → 候选集重排与可信难负例 → 冗余、噪声、来源与安全控制 → 数据、召回、排序、证据利用、答案、安全和成本的分层评测。**

## 3. 关键条件性分歧与不可越界结论

### 3.1 可调和的条件性分歧

1. **凸组合与 RRF**：分数可校准且有独立验证数据时，连续归一化分数融合更可解释；只能获得名次、分数不可比或零样本部署时，RRF 更易落地。二者不存在脱离信息条件的永久胜者。【001；026】
2. **融合与强单路**：OOD 或路径错误差异大时，融合更可能获益；域内监督使强模型领先且信号趋同时，等权融合可能稀释强路。异构不是互补的充分条件。【002；014；019；022】
3. **dense 与 sparse**：自然语言改写与描述性表达为 dense 提供优势，实体、数字、短精确查询和规范术语常保留 sparse 优势；监督、领域和 qrel 口径都会改变方向。【006；014；020；028；040】
4. **候选协作与相似干扰**：相关项围绕共同实体/关系成簇时，候选关系可作正证据；多意图、模板重复或共同词法诱饵场景中，相似性可能只表示冗余或共同错误。【011；016；023】
5. **更多上下文与证据利用**：增加 top-k 可提高覆盖，也会累积 distractor、拉远证据—问题距离并加剧位置偏差；最佳深度依证据充分性、噪声密度、Prompt 布局和模型家族而变。【033；034；038；041；045】
6. **难负例与假阴性**：困难且真实的负例提高区分力；未标相关项被当成负例时，梯度方向才有害。修复标签后，增加困难负例仍可能继续获益。【005；010；036】
7. **冗余与可靠性**：重复事实可提供替代路径，也可挤占有限 top-k；决定效应的是所需事实的多样性与覆盖，而非重复率本身。【023；027】
8. **拒答与鲁棒性**：证据不足时拒答可能是安全行为，但若不同时报告回答覆盖和拒答代价，保守模型会被误判为总体更可靠。【024；031】
9. **结构增强与局部相关**：树、图和摘要可恢复全局语境，但过强的结构信号也会遮蔽局部条款；完整管线增益不等于某个结构算子的独立因果效应。【013；025；035；039；042；043】
10. **上下文判断与上下文波动**：列表上下文提供相对比较信息，也引入批次和位置噪声；需要多上下文聚合并明确采样分布，而非把一次 setwise 判断当作稳定真值。【004】

### 3.2 不可越界的结论

- 不能断言 hybrid、动态门控、图/树增强、listwise reranking 或 hard-negative training 中任何一种方法普遍优于强单路；当前证据反复显示数据、领域、查询、候选池、生成器、指标与预算会改变结论。
- 不能把 Recall、MRR、nDCG、P@1 或重排分数的改善直接写成答案更正确、更忠实、更安全或更少幻觉；检索、证据利用与生成是不同被测层。
- 不能把语义相似度等同于任务相关性，也不能把词法分离度与失败之间的关联写成因果；制度关系、来源、时间、数字、否定和条件可能决定真实标签。
- 不能宣称 reranker 能修复首阶段漏召；所有候选内方法都受候选召回上限约束。
- 不能把 LLM judge、生成一致性、RAGAS 或自动字符串匹配当作人工真值；它们会受提示、位置、采样、模型家族和稳定错误影响。
- 不能把 `training-free`、调用次数少或小模型直接等同于低成本；多路索引、全路检索、查询扩展、多次采样、NLI、图编辑和长上下文都可能主导总成本。
- 不能把点估计、小幅优势、单次运行、best-of-grid、同一数据调参与报告或人工示意结果解释为稳定总体效应。
- 不能由离线闭集结果推出线上、临床、法律、国防或农业决策安全；多数相关研究缺少真实部署结局与完整威胁模型。
- 不能由拒答率更高推出更安全，也不能由显式引文推出引用忠实；必须分别测回答覆盖、引用支持、事实充分性和正常任务效用。
- 不能把两个 RARE 当作同一框架，也不能把同论文的 ACL/arXiv 版本当成两项独立证据。
- 不能把“矛盾与重复事实难以由余弦分离”或“主题相似但证据无效候选获得高分”写成本文首次发现；近邻工作已经明确覆盖这两项一般现象。

## 4. 逐篇文献卡

### 4.1 证据卡 001–016

#### 001

- **题名**：[An Analysis of Fusion Functions for Hybrid Retrieval](<../papers/An Analysis of Fusion Functions for Hybrid Retrieval.pdf>)
- **官方来源**：[出版页](https://doi.org/10.1145/3596512)
- **逻辑链**：词法与语义检索的分数尺度不同，混合排序首先需要可比较的融合函数。论文把归一化凸组合的敏感性转化为 rank-equivalence 与相对扩张率问题，并把 RRF 的折扣参数与离散名次跳变显式化。主实验中，理论 min-max 归一化的凸组合以少量验证查询即可调到较强结果，但附录显示这种优势不对所有检索器配对成立。因此函数选择取决于分数可校准性、验证预算与候选构造，而不是脱离条件的算法名次。
- **创新/价值亮点**：给出“归一化改变能否由权重变化吸收”的充分条件，并用连续性、齐次性、可解释性和样本效率评价融合函数；Smooth RRF 还提供从离散名次到平滑近似的机制检验路径。
- **证据边界与 PDF 页码**：只覆盖二路融合、有限候选并集和深截断指标；未证明线性融合逐查询最优，平滑也并非越强越好。候选构造与主结果见 pp. 4–6、15–16，归一化理论见 pp. 10–14，RRF 参数和平滑见 pp. 17–25，配对反例见 pp. 29–36。

#### 002

- **题名**：[Balancing the Blend: An Experimental Analysis of Trade-offs in Hybrid Search](<../papers/Balancing the Blend: An Experimental Analysis of Trade-offs in Hybrid Search.pdf>)
- **官方来源**：[出版页](https://www.vldb.org/pvldb/vol19/p1715-gao.pdf)
- **逻辑链**：真实混合检索可同时包含全文、学习式稀疏、单向量稠密和 token-level tensor 路径；增加路径既可能补充召回，也可能加入高排噪声。全组合实验发现“路径越多越好”不成立，弱路径会形成 weakest-link；效果还受最慢路径、索引体积和查询内存约束。TRF 将 MaxSim 限定在小候选集上，以低于全库 tensor 检索的成本执行细粒度重排，但仍不能消除语义近似难负例。
- **创新/价值亮点**：完整覆盖四类路径的 15 种配置，并把准确率、P99 延迟、QPS、内存和建索引成本纳入同一框架；将 late interaction 从全库路径重定位为候选重排器，是清晰的架构创新。
- **证据边界与 PDF 页码**：TRF 并非处处优于 RRF，query length 也只是一项数据集级线索；没有端到端生成质量和动态路径选择实验。weakest-link 见 pp. 7–9，效果—成本与 TRF 见 pp. 8–10，单查询 hard negative 案例见 pp. 10–11，外推边界见 pp. 11–12。

#### 003

- **题名**：[DAT: Dynamic Alpha Tuning for Hybrid Retrieval in Retrieval-Augmented Generation](<../papers/DAT: Dynamic Alpha Tuning for Hybrid Retrieval in Retrieval-Augmented Generation.pdf>)
- **逻辑链**：固定融合权重优化平均查询，但不同查询对词法与语义信号的依赖不同。DAT 以 BM25 和 dense 各自 Top-1 作为当前查询—知识库交互的诊断探针，让 LLM 分别评分，再把两路有效性比值映射为查询专属权重。相对固定 α=0.6，动态权重在完整集上有中等增益，在预定义 hybrid-sensitive 查询上增益更集中；较小 judge 仍保留主要收益，但规模与权重判断质量不严格单调。
- **创新/价值亮点**：不先分类 query type，而是直接读取当前知识库的两路实际返回结果；一次双结果评分即可产生透明、可审计的门控决策。完整集与敏感子集并列报告，也揭示收益并非均匀分布。
- **证据边界与 PDF 页码**：Top-1 代表性、judge 校准、极端分段规则和比例映射缺少消融，且没有 RRF、学习路由器或端到端生成对照。方法和公式见 pp. 4–5，数据与基线见 pp. 5–7，完整集及敏感子集结果见 pp. 7–8，成本与提示边界见 pp. 11–12。

#### 004

- **题名**：[Contextual Relevance and Adaptive Sampling for LLM-Based Document Reranking](<../papers/Contextual Relevance and Adaptive Sampling for LLM-Based Document Reranking.pdf>)
- **官方来源**：[出版页](https://aclanthology.org/2026.acl-long.94/)
- **逻辑链**：Setwise LLM 对同一文档的判断会随批次组成、顺序和采样改变，因此单次比较不是稳定标签。论文把目标改为跨上下文分布的期望判断概率，并用 Beta–Bernoulli 后验聚合重复观察。Uniform sampling 提供上下文平均，Thompson Sampling 在有限预算下更快聚焦高潜力或高不确定候选，但预算增大后差距缩小；分主题结果中部分集合仍由原始 BM25 或 Uniform 最佳。
- **创新/价值亮点**：把候选上下文从“待消除偏差”提升为明确估计对象，并把 LLM 调用预算写成 combinatorial semi-bandit 的序贯分配问题；Intrinsic、Positional、Total 三条件分开诊断内在采样、位置与组成变异。
- **证据边界与 PDF 页码**：理论遗憾界只针对独立 Bernoulli arms 和线性代理奖励，不保证 nDCG；自适应采样还会改变它试图平均的上下文分布。相关文档判断准确率仅约 0.26–0.28，核心实证又只使用 Qwen2.5-7B-Instruct，不能直接外推到一般 LLM reranker。定义与算法见 pp. 2–4，方差和主结果见 pp. 6–7，预算与并行性见 pp. 7–8，逐主题退化及适用边界见 pp. 9、13–14。

#### 005

- **题名**：[DocReRank: Single-Page Hard Negative Query Generation for Training Multi-Modal RAG Rerankers](<../papers/DocReRank: Single-Page Hard Negative Query Generation for Training Multi-Modal RAG Rerankers.pdf>)
- **官方来源**：[出版页](https://aclanthology.org/2025.emnlp-main.436/)
- **逻辑链**：传统 hard-negative mining 固定 query、从语料找负页面，候选受语料和首阶段检索器限制，还可能把未标相关页面当作负例。DocReRank 反转采样轴：固定页面，在 query 轴生成主题和句式相近但无法由页面回答的负例，再用独立 VLM 双提示过滤。通过只修改年份、实体、数值或业务分部，方法定向制造单属性最小反事实；同规模消融显示与传统负页面混合优于只用传统负页面。最强 Full 结果还包含更多训练数据，不能全部归因于负例类型。
- **创新/价值亮点**：负 query 比完整负页面更容易生成和控制，使错误类型从检索器偶然决定变为可指定；“语言生成—视觉可回答性验证”的任务解耦与非对称共识过滤规则具有可复查性。
- **证据边界与 PDF 页码**：人工检查仍发现 8.2% 残余假阴性，Full 模型又混入更大数据量；生成成本、跨生成器稳定性和端到端答案质量均未证明。方法见 pp. 1–5，训练与同规模消融见 pp. 6–8，人工验证见 p. 9，prompts 与失败案例见 pp. 15–18。

#### 006

- **题名**：[DuReader-Retrieval: A Large-scale Chinese Benchmark for Passage Retrieval from Web Search Engine](<../papers/DuReader_retrieval: A Large-scale Chinese Benchmark for Passage Retrieval from Web Search Engine.pdf>)
- **官方来源**：[出版页](https://aclanthology.org/2022.emnlp-main.357/)
- **逻辑链**：大规模中文检索评测同时受假阴性、训练—测试语义重复和单一域内切面影响。论文用多检索器池化加人工复标补充相关段落，删除与开发/测试近义的训练查询，并加入医学域外与英问中段跨语言测试。域内 dense 与 cross-encoder 明显胜过 BM25，但该优势在医学域和跨语言设置中大幅收缩；失败集中于实体、数字、修饰语、句法方向和词法重叠干扰。指标上升的一部分来自 qrels 修正，而非模型变化。
- **创新/价值亮点**：把 qrels 漏标作为测量误差，并用标签修正前后的同模型变化直接展示评测偏差；错误分类具体到约束槽位，比笼统“语义不足”更可操作。
- **证据边界与 PDF 页码**：人工池化仍受贡献系统和 top-5 深度限制，失败案例中还有 14.8% 残余假阴性；两个 OOD 集都属医学域。数据治理见 pp. 3–5，域内与域外结果见 pp. 6–8，错误类型和残余漏标见 pp. 7、12–13。

#### 007

- **题名**：[Enhancing Retrieval-Augmented Generation with Topic-Enriched Embeddings: A Hybrid Approach Integrating Traditional NLP Techniques](<../papers/Enhancing Retrieval-Augmented Generation with Topic-Enriched Embeddings: A Hybrid Approach Integrating Traditional NLP Techniques.pdf>)
- **逻辑链**：contextual embedding 表达局部语义，但可能缺少语料级主题组织；TF-IDF/LSA、LDA 和 MiniLM 分别提供词项、潜在主题和上下文信号。方法要求文档与查询经过同构变换，再以拼接或加权形成统一检索向量。作者报告 topic-enriched 表示优于单路表示，但结果节明确标注为 artificial data and outputs，数值不能视为真实、可复核的经验成绩。
- **创新/价值亮点**：把主题结构直接注入索引和查询坐标，而不是仅作检索后过滤；random-topic 负对照提出了正确的因果排查方向。框架模块化且不依赖人工主题标签。
- **证据边界与 PDF 页码**：融合维度、完整模型定义、真实 qrels、方差和代码均不充分，主表与附录基线存在不一致；只能作为待验证设计。架构与公式见 pp. 7–8，人工示意声明见 p. 12，报告结果见 pp. 13–17，方法边界见 pp. 19–21，消融见 p. 25。

#### 008

- **题名**：[From RankNet to LambdaRank to LambdaMART: An Overview](<../papers/From RankNet to LambdaRank to LambdaMART: An Overview.pdf>)
- **逻辑链**：RankNet 用成对交叉熵平滑“谁应排在谁前”，但不能区分榜首与榜尾错序对 NDCG 的价值差异。LambdaRank 将成对 λ 乘以交换对目标指标的影响，使更新优先修正重要位置；LambdaMART 再用梯度提升树拟合逐文档 λ。这绕过了离散排序指标无法直接求普通梯度的问题，但没有把 NDCG 变成处处可微的全局损失；指标、截断深度和当前排序都会改变 λ。
- **创新/价值亮点**：以“成对概率损失→逐文档 λ→指标加权 λ→回归树拟合 λ”的统一接口贯通三代算法；明确区分固定排序区间内的局部效用与全局可积性，避免把启发式梯度包装成严格全局目标。
- **证据边界与 PDF 页码**：这是教程型技术报告，明确不提供新对比实验；逐对计算仍可能二次增长，总体效用也会掩盖查询级退化。RankNet 与因式分解见 pp. 2–5，指标冲突及 LambdaRank 见 pp. 5–11，LambdaMART 见 pp. 12–17，排序器组合见 p. 18。

#### 009

- **题名**：[HYRR: Hybrid Infused Reranking for Passage Retrieval](<../papers/HYRR: Hybrid Infused Reranking for Passage Retrieval.pdf>)
- **逻辑链**：reranker 若只在一种首阶段检索器的候选上训练，会学习该检索器特有的负例分布，并在候选来源切换时负迁移。HYRR 先拼接稀疏与稠密表示，在联合内积空间中挖掘候选，使训练负例同时反映两类信号。跨 BM25、dense 和 hybrid 的消融显示 HYRR 较稳定，但相对 dense-negative 受控基线的增益很小，较大的 BEIR 平均收益还混入目标域合成训练。因此证据更支持“小幅稳健性收益”，不支持逐条件稳定支配。
- **创新/价值亮点**：把训练候选分布提升为独立于模型架构的设计变量，并用“简单混合两份负例训练集”作为关键反事实；训练源与部署源的交叉矩阵比只报同源结果更能说明 retriever-robustness。
- **证据边界与 PDF 页码**：MS MARCO 主受控增益仅 0.0013 MRR@10，缺少显著性和多随机种子；完整交叉矩阵也只覆盖两个数据集。方法与合成训练见 p. 3，主结果和泄漏边界见 p. 4，跨检索器消融及负结果见 p. 5。

#### 010

- **题名**：[Hard Negatives, Hard Lessons: Revisiting Training Data Quality for Robust Information Retrieval with LLMs](<../papers/Hard Negatives, Hard Lessons: Revisiting Training Data Quality for Robust Information Retrieval with LLMs.pdf>)
- **官方来源**：[出版页](https://aclanthology.org/2025.findings-emnlp.481/)
- **逻辑链**：多源训练数据的某些来源会造成负迁移，hard-negative 集合中还可能混入未标相关 passage。论文先做来源级 leave-one-out 剪枝，再用 GPT-4o-mini→GPT-4o 级联识别 false hard negatives，并比较保留、删除和重标为 positive。重标通常优于保留或删除，且修复标签后增加 hard-negative 数量仍继续提升，说明问题在标签错误而不是困难负例本身。OOD 汇总收益更突出，但不同数据集仍有下降，CE distillation 也未被全面击败。
- **创新/价值亮点**：来源级筛查与样本级修复构成双尺度数据审计；“停止错误负监督”与“回收正监督”被清楚拆开，同一修复数据又跨 encoder retriever、decoder retriever 和 reranker 验证。
- **证据边界与 PDF 页码**：剪枝在 BEIR 上选择又在 BEIR 上报告，存在选择偏差；judge 与人工的 κ 仅 .320/.390，E5 汇总效应区间包含 0。框架及计数见 pp. 1–5，retriever/reranker 与负例数消融见 pp. 6–7，人工审计见 pp. 8–9，效应区间见 pp. 19–20。

#### 011

- **题名**：[Hybrid and Collaborative Passage Reranking](<../papers/Hybrid and Collaborative Passage Reranking.pdf>)
- **官方来源**：[出版页](https://aclanthology.org/2023.findings-acl.880/)
- **逻辑链**：逐 passage reranker 忽略候选列表内部的相似结构，而相关 passages 在部分任务中会围绕共同实体和关系成簇。HybRank 把 query 与每个候选表示成它们对共同 anchors 的稀疏—稠密相似度序列，再用列方向交互和行方向聚合学习列表级协作。多种上游列表均获单次运行增益，但完整协作和 hybrid 特征并非每个 cutoff 都优于消融或最佳单路；较弱上游和浅 cutoff 通常获益更大，强 reranker 后边际收益收缩。
- **创新/价值亮点**：共同 anchors 将列表上下文变成可学习关系矩阵，轴向注意力把全矩阵交互复杂度降为可管理形式；只有 0.22M 参数且能接在已有 reranker 后继续增益，使插件主张有直接证据。
- **证据边界与 PDF 页码**：协作假设不适合多意图、覆盖和多样性排序，相似簇也可能只是重复；主结果均为 single run，缺少在线延迟。表示和模型见 pp. 2–5，主结果见 p. 6，协作与特征反例见 pp. 7–8，复杂度及任务边界见 pp. 9–10、14–17。

#### 012

- **题名**：[INKER: Adaptive dynamic retrieval augmented generation with internal-external knowledge integration](<../papers/INKER: Adaptive dynamic retrieval augmented generation with internal-external knowledge integration.pdf>)
- **逻辑链**：动态 RAG 同时需要回答何时检索和检索什么；仅依赖生成内部置信度会忽略问题需求，仅依赖静态复杂度又不能反映生成中的实时缺口。INKER 以 query complexity 减去逐 token confidence 触发检索，并把生成轨迹短语与原 query 分析信息拼成 BM25 查询。多跳任务通常获得更高 QA 点估计和更少检索，但简单任务中存在无检索更好以及部分指标退化的反例。这说明价值取决于任务知识需求，不能由更少调用或总体平均单独判定。
- **创新/价值亮点**：when 与 what 被拆成两个可审计决策，且都显式融合生成内部状态与原始问题信息；检索次数、生成 token 和 QA 质量同时报告，使质量—调用折中可观察。
- **证据边界与 PDF 页码**：`training-free` 只针对主 LLM，Eva 和 confidence direction 仍需拟合；检索质量、总延迟、组件校准与跨语言泛化未直接测量。框架与公式见 pp. 4–7，实验与主结果见 pp. 8–10，when/what 消融见 pp. 10–11、15，拟合细节与边界见 pp. 13–16。

#### 013

- **题名**：[Improving knowledge management in building engineering with hybrid retrieval-augmented generation framework](<../papers/Improving knowledge management in building engineering with hybrid retrieval-augmented generation framework.pdf>)
- **逻辑链**：固定长度 chunk 与单一 dense 索引会破坏工程条款结构，也难利用引用、定义、摘要和表图关系。论文用五类节点和 property graph 保留文档结构，以风险导向子查询、关系扩展和受界关键词校正共同检索，再让 GPT-4O 基于节点生成答案。整体系统在基本问答、复杂风险识别和开放生成上优于固定 dense baseline，但低质量 baseline RAG 在复杂任务上甚至低于无检索模型。这项负结果说明检索上下文只有相关性足够高时才可能是增益。
- **创新/价值亮点**：“摘要召回、原文作答”区分 discovery unit 与 evidence unit；风险导向 transformation 也比机械分解更贴合工程核查。检索与回答指标联合报告，能观察召回改进是否传到任务输出。
- **证据边界与 PDF 页码**：只比较完整系统包且没有模块消融，样本小、人工协议和统计不确定性不足；表图仅靠 caption 间接召回。节点与关系见 pp. 4–6，query transformation 和融合检索见 pp. 7–9，三项任务及负结果见 pp. 10–13。

#### 014

- **题名**：[Know When to Fuse: Investigating Non-English Hybrid Retrieval in the Legal Domain](<../papers/Know When to Fuse: Investigating Non-English Hybrid Retrieval in the Legal Domain.pdf>)
- **逻辑链**：词法、稀疏、单向量 dense 和多向量检索器只有在错误非重合时才有融合价值。法语法律 zero-shot/OOD 中，BM25 与神经检索器保留明显互补，88 个配置多数改善 recall；少量域内监督使强 DPR 的点估计明显提升后，多数等权融合反而稀释其信号。因此“何时融合”的判据应是当前分布中的剩余互补性，而不是模型标签是否异构。
- **创新/价值亮点**：同一研究内的 zero-shot/in-domain 对照清楚显示融合收益会随域适配反转；88 配置穷举、分数互补图和效率测量把效果、机制与资源代价连接起来。
- **证据边界与 PDF 页码**：zero-shot 的 R-precision 未随融合改善，in-domain 权重在 dev 调参又在 dev 报主结果；证据只来自单一比利时法条数据集。单路与 OOD 融合见 pp. 3–6，域内反转见 pp. 6–8，成本见 pp. 3–4，信号趋同与调权细节见 pp. 18–20。

#### 015

- **题名**：[LLM-Confidence Reranker: A Training-Free Approach for Enhancing Retrieval-Augmented Generation Systems](<../papers/LLM-Confidence Reranker: A Training-Free Approach for Enhancing Retrieval-Augmented Generation Systems.pdf>)
- **逻辑链**：直接让 LLM 判断 relevance 之外，文档加入后多次回答是否收敛也可作为 helpfulness 代理。LCR 用最大语义簇占比定义 query 与 query-document confidence，只在 query confidence 低时按 high/medium/low 桶稳定调整原排序。弱 reranker 的平均增益较大，强 reranker 的收益小且需要保守 gating；confidence 与 relevance 的分箱关系并非所有数据集单调。
- **创新/价值亮点**：MSCP 只依赖黑盒输入输出，gated residual reranking 又保留原排序的档内次序，降低噪声 confidence 的破坏性；阈值曲线和 MSCP-vs-entropy 分析使机制比单一主表更可追踪。
- **证据边界与 PDF 页码**：主表取 best-of-threshold 且未说明独立验证集，“无退化”不构成未见数据保证；每个 query-document 的多次生成和双向 NLI 成本未报告。MSCP 与算法见 pp. 6–8，实验和调参见 pp. 8–12，强弱基线及阈值结果见 pp. 11–16，非单调关系和生成端边界见 pp. 16–17。

#### 016

- **题名**：[Language Model Re-rankers are Fooled by Lexical Similarities](<../papers/Language Model Re-rankers are Fooled by Lexical Similarities.pdf>)
- **官方来源**：[出版页](https://aclanthology.org/2025.fever-1.2/)
- **逻辑链**：LM reranker 成本高于 BM25，但整体 P@1 无法说明它在何种候选关系上失效。论文以 gold 与最强 non-gold 的 BM25 分离度刻画 lexical distractor 压力；低分离组中，BGE 跨三个数据集、六个 LM 在 DRUID 上都一致更易失准。标题和任务化 prompt 只在结构规整或任务语义明确时有效，生成式上下文在长科学文献上还可能退化。
- **创新/价值亮点**：ΔP@1 同时观察 gold alignment 与 BM25 alignment，揭示绝对准确率略升时模型仍可能复现词法排序偏好；`D_BM25` 提供简单、可替换相似度函数的离线难例坐标。
- **证据边界与 PDF 页码**：`D_BM25` 依赖 gold，不能在线路由；低分离度与失败只是关联，阈值没有敏感性分析，因而 `fooled` 仍是偏强措辞。定义和主结果见 pp. 1–4，数据、运行与分组结果见 pp. 5–10，替代相似度见 pp. 11–13，具体干扰案例见 pp. 14–16。历史快照另有一个字节级重复副本，其 604,585 bytes、16 页和 SHA-256 均与主文件完全相同；2026-09-06 保全后已去重，现使用上方主文件链接。副本 OCR 缺失不改变实体内容。

### 4.2 证据卡 017–036

#### 017｜MMTEB

- **题名**：[MMTEB: Massive Multilingual Text Embedding Benchmark](<../papers/MMTEB: Massive Multilingual Text Embedding Benchmark.pdf>)
- **逻辑链**：既有 embedding benchmark 的语言、任务和领域覆盖有限，大规模评测成本又对低资源语言社区尤其不利。MMTEB 先建立 500+ 任务的多语言 registry，再用任务间可预测性删除冗余任务，并以语言×任务类别 guard 保留代表性。结果显示 instruction tuning 普遍有益，但模型优劣依 benchmark 子集而变，多语言、欧洲、Indic、英语和代码榜单没有同一赢家。
- **创新/价值亮点**：把 benchmark 从固定总榜升级为可组合、版本化且带任务元数据的公共基础设施；同时量化 clustering、retrieval、bitext 等任务的降本幅度与模型排序保留程度。
- **证据边界与 PDF 页码**：`1000+ languages` 主要受 bitext language-pair 口径推动，低资源语言的任务类型仍严重不均；子集保序也主要在参与设计的有限模型集合上验证。任务池与子集选择见 pp. 2–6，主结果 pp. 7–11，降本与保序 pp. 42–45，语言覆盖 pp. 46–48，子基准清单 pp. 51–57。

#### 018｜MTEB

- **题名**：[MTEB: Massive Text Embedding Benchmark](<../papers/MTEB: Massive Text Embedding Benchmark.pdf>)
- **逻辑链**：单一 STS 或分类得分无法说明 embedding 能否迁移到检索、聚类和重排，评测 pipeline 差异又会混入模型比较。MTEB 以统一 encode 接口连接 8 类任务、58 个数据集和 112 种语言，并规定各任务 evaluator 与主指标。33 个模型没有一个在全部英文任务上最优，symmetric similarity 与 asymmetric retrieval 出现系统性分化。
- **创新/价值亮点**：论文把多种 embedding 使用方式置于同一可复现框架，并同时报告速度、参数量与存储成本；任务相关矩阵和多语言结果把“模型偏科”从零散现象变为可比较结构。这里不据此作优先权主张。
- **证据边界与 PDF 页码**：总平均按数据集聚合异质量纲，任务与语言分布不均；长文档、多语言检索、代码任务、训练污染和统计不确定性均未充分处理。设计与任务定义见 pp. 1–5，模型与主结果 pp. 5–9，限制 pp. 9–10，数据构造 pp. 14–20，完整结果 pp. 21–24。

#### 019｜MoR

- **题名**：[MoR: Better Handling Diverse Queries with a Mixture of Sparse, Dense, and Human Retrievers](<../papers/MoR: Better Handling Diverse Queries with a Mixture of Sparse, Dense, and Human Retrievers.pdf>)
- **官方来源**：[出版页](https://aclanthology.org/2025.emnlp-main.601/)
- **逻辑链**：同一领域内不同 query 对 sparse、dense 和粒度配置的偏好不同，固定检索器或固定权重会浪费这种互补性。MoR 用召回前 query–corpus familiarity 与召回后结果结构，为八个检索器及四类语义粒度做零样本逐 query 软加权。四个英语科学检索集上的宏平均优于最佳组件与两种 7B 基线，但 SciFact 上仍明显落后于 GritLM。
- **创新/价值亮点**：把 resource selection、query performance prediction、粒度选择和 rank fusion 写进同一混合公式；子集穷举与预拒绝实验揭示互补组合比简单堆叠全部检索器更重要。
- **证据边界与 PDF 页码**：默认方案仍执行全部检索器和多粒度索引；`Human` 只是域内 oracle、域外随机的模拟，固定权重、显著性和真实总成本不透明。互补动机与 oracle 见 pp. 3–4，方法 pp. 4–6，主结果 pp. 6–8，消融与效率 pp. 16–19。

#### 020｜Multi-CPR

- **题名**：[Multi-CPR: A Multi Domain Chinese Dataset for Passage Retrieval](<../papers/Multi-CPR: A Multi Domain Chinese Dataset for Passage Retrieval.pdf>)
- **逻辑链**：中文特定领域缺少大规模人工相关性数据，通用域或点击标签不能替代电商、娱乐视频与医疗搜索的语义判断。Multi-CPR 从真实商业日志构造三域百万 passage 基准，以五人标注和专家抽检筛选高一致性正对。域内监督 DPR 和 BERT 重排均明显改善结果，但电商中 BM25 仍胜过通用 DPR，显示精确词项匹配的条件性优势。
- **创新/价值亮点**：在同一数据构造框架内比较三个差异明显的中文生产搜索域，并保留 sparse/dense 各自失败的反例；域内监督、继续预训练和重排形成递进诊断链。
- **证据边界与 PDF 页码**：每域仅来自单日单平台日志，候选受点击预筛，最终只保留单一正例且语料未穷尽标注；正文还有若干百分比与表值不一致。来源与标注见 pp. 2–5，规模与基线 pp. 5–6，主结果 p. 7，案例、局限与未来方向 pp. 8–9。

#### 021｜Complementarity Objectives

- **题名**：[On Complementarity Objectives for Hybrid Retrieval](<../papers/On Complementarity Objectives for Hybrid Retrieval.pdf>)
- **逻辑链**：既有 residual 训练会把 dense 成功集整体增大与 dense 真正补足 sparse 缺口混为一谈。论文以有方向的 `RoC=|D-S|/|D|` 定义互补性，再用 lexical/semantic 表征正交和精确匹配 token 扰动训练 dense retriever。在三套英语 benchmark 与逐数据集融合调参下，两层代理提高 NQ 的 RoC，并伴随多项混合检索指标上升。
- **创新/价值亮点**：把互补性从直觉改写为可观测的成功集合比例，并明确惩罚 dense 与 sparse 的重复成功；用表征级与输入级两个代理分别对应“减交集”和“增 residual”。
- **证据边界与 PDF 页码**：RoC 非对称、cutoff 敏感且不是融合性能本身；代理损失到集合互补性的桥接是启发式，RoC 的系统验证主要集中于 NQ。RoC 定义与目标见 pp. 1–3，损失与融合 pp. 3–5，主结果与消融 pp. 6–8，限制 p. 9，长度分析 p. 10。

#### 022｜QuDAR

- **题名**：[QuDAR: Query-Wise Dual-Perspective Adaptive Retrieval](<../papers/QuDAR: Query-Wise Dual-Perspective Adaptive Retrieval.pdf>)
- **官方来源**：[出版页](https://aclanthology.org/2026.acl-long.1791/)
- **逻辑链**：稀疏/稠密配比与原始/扩展查询配比都会随 query 改变，而且两个适应轴存在交互。QuDAR 构造原始–稀疏、原始–稠密、扩展–稀疏、扩展–稠密四路结果，再用等权、分数间隔或 LLM 可答性评分逐 query 融合。多数主实验指标提升，但 Climate-FEVER Recall 和若干替换组件设置仍由最佳单视角胜出。
- **创新/价值亮点**：在给出可部署启发式前，先用静态与逐 query oracle 网格量化双轴适应空间；confidence、LLM、RRF 与 Equal 形成清晰的效果—成本退化路径。
- **证据边界与 PDF 页码**：top-1 代表整路质量、分数间隔未校准，关键温度与归一化细节缺失；`training-free` 仍需查询扩展与 LLM 评分成本。双轴动机见 pp. 2–5，方法 pp. 5–7，主结果 pp. 7–9，oracle 细节 pp. 12–14，组件替换 pp. 15–18。

#### 023｜Redundancy-Aware RARE

- **题名**：[RARE: Redundancy-Aware Retrieval Evaluation Framework for High-Similarity Corpora](<../papers/RARE: Redundancy-Aware Retrieval Evaluation Framework for High-Similarity Corpora〔ACL 2026〕.pdf>)（另见 [arXiv 2604.19047v2](<../papers/RARE: Redundancy-Aware Retrieval Evaluation Framework for High-Similarity Corpora〔arXiv 2604.19047〕.pdf>)）
- **官方来源**：[出版页](https://aclanthology.org/2026.acl-long.923/)
- **逻辑链**：高相似企业语料中，同一事实可散布于多个近重复 passage，单一 canonical qrel 会误罚等价证据并掩盖多跳覆盖瓶颈。RARE 将 chunk 拆为 atomic facts、追踪跨 chunk 等价关系，先执行有效性与零容忍逻辑过滤，再由 CRRF 分别排序 atomic units 和候选问题；多跳问题由 LLM 另行生成。结果显示企业域多跳 PerfRecall@10 急剧下降；相似度更像混淆源，而冗余既会占位也可能提供替代路径。
- **创新/价值亮点**：把 similarity、fact redundancy、等价证据 qrels 与多跳完美覆盖放入同一 benchmark 构造框架；数据流程、成本、通过率、prompt 和逐 hop 结果披露较完整。
- **证据边界与 PDF 页码**：等价链接未做独立人工 precision/recall 审计，四域比较也不是控制实验；hop 增加本身会机械降低全部证据同时命中的概率。定义与流程见 pp. 1–6，检索与 RAG 结果 pp. 6–9，限制 p. 10，构造统计 pp. 12–14，逐 hop 与 CRRF pp. 17–19。两版均 26 页且预检 `PASS`，但 SHA-256 不同；正式版带 ACL 页眉、版权和印刷页码，arXiv 版带 arXiv 侧栏。

#### 024｜Retrieval-Aware RARE

- **题名**：[RARE: Retrieval-Aware Robustness Evaluation for Retrieval-Augmented Generation Systems](<../papers/RARE: Retrieval-Aware Robustness Evaluation for Retrieval-Augmented Generation Systems.pdf>)
- **逻辑链**：静态通用 QA 容易被参数记忆答对，既有鲁棒性评测也很少统一覆盖查询、文档与真实检索扰动。RARE-Get 构造专业多跳 QA，RARE-Set 汇集金融、经济和政策文本，RARE-Met 再依据无上下文探针规定正确证据、缺失证据与真实检索下的答对或拒答行为。模型规模总体有益但不单调，多跳和经济域更弱，文档扰动最能暴露拒答倾向造成的排名逆转。
- **创新/价值亮点**：用模型自身参数知识探针条件化目标行为，区分“保持已知正确答案”与“证据不足时安全拒答”；查询表层/高级扰动、文档答案状态和真实检索被纳入同一分解指标体系。
- **证据边界与 PDF 页码**：计分规则随模型自身探针改变且奖励拒答，跨模型可比性与用户效用存在歧义；LLM 全链路构造缺人工质量审计。构造管线见 pp. 4–7，鲁棒指标 pp. 8–9，主结果 pp. 9–11，扰动实现 pp. 14–16，完整分析 pp. 28–32。本实体与 023 只是缩写同为 RARE，不能合并。

#### 025｜ReG-RAG

- **题名**：[ReG-RAG：融合查询重写与图谱增强的大模型问答生成方法](<../papers/ReG-RAG：融合查询重写与图谱增强的大模型问答生成方法.pdf>)
- **逻辑链**：专业查询的含糊表达会降低文本检索覆盖，单纯图谱检索又难提供完整细节。ReG-RAG 先用领域伪样本微调 T5-large 重写查询，再并行检索向量文本与知识图谱子图，最后由 GLM-4 融合生成。油菜集和 WikiEval 的四项 RAGAS 点估计均高于五个基线，但各组件贡献没有通过消融识别。
- **创新/价值亮点**：将领域监督重写、文本/图谱双通道与查询条件化融合串成完整垂直领域系统；元数据、三元组提示和整体数据流展示直观。
- **证据边界与 PDF 页码**：319 条油菜问答可能同时进入重写监督与评测，存在泄漏风险；图谱规模、路由训练、judge 配置、统计检验和成本报告不足。架构见 pp. 2–5，数据与指标 pp. 5–7，主结果 pp. 7–8，案例与自陈限制 pp. 8–9。

#### 026｜Reciprocal Rank Fusion

- **题名**：[Reciprocal Rank Fusion outperforms Condorcet and Individual Rank Learning Methods](<../papers/Reciprocal Rank Fusion outperforms Condorcet and Individual Rank Learning Methods.pdf>)
- **逻辑链**：多排序器融合若依赖监督标签或原始分数校准，会增加训练与跨系统适配成本。RRF 仅按 `Σ1/(k+rank)` 累积名次贡献，并以 pilot 选定 `k=60`。在多组 TREC 和 LETOR 3 实验中，RRF 大多胜过最佳单系统、Condorcet 和单独 rank learner，但并非总胜 CombMNZ 或人工结果。
- **创新/价值亮点**：公式极简、免训练、免分数校准，并能把多个 learned ranker 再融合为 meta-learner；高排名贡献与 `k` 的平滑提供直观的异常系统缓冲机制。
- **证据边界与 PDF 页码**：两页论文没有定义截断榜单和缺失文档处理，统计样本很小，`k=60` 来自同一 pilot；现代神经检索外推需独立验证。公式、pilot 与 TREC 设计见 p. 1，全部结果、统计与讨论见 p. 2。

#### 027｜ReflectiveRAG

- **题名**：[ReflectiveRAG: Rethinking Adaptivity in Retrieval-Augmented Generation](<../papers/ReflectiveRAG: Rethinking Adaptivity in Retrieval-Augmented Generation.pdf>)
- **逻辑链**：固定 top-k 既不能发现证据不足，也会把重复或离题 chunk 无条件送入生成器。ReflectiveRAG 由小模型判断证据充分性并触发自然语言改写，再以 query 相关性减 chunk 冗余裁剪上下文。在两个公开 QA 的 50M 噪声设置中，点估计优于四个基线；消融方向支持反思检索与去冗余各有贡献。
- **创新/价值亮点**：把欠检索与过检索拆为串联的 SRR 和 NR，并使检索深度成为可观察控制流；同时报告 EM/F1、冗余率和端到端延迟，形成精度—紧凑度—成本对照。
- **证据边界与 PDF 页码**：正文公式、公开 prompt 与伪代码在条件输入、候选数和停止规则上不一致，且没有检索过程指标、统计检验或跨组件复现。框架见 pp. 2–4，设置与主结果 pp. 4–6，限制与 prompt pp. 6–8。

#### 028｜Regulatory DOC2DOC IR

- **题名**：[Regulatory Compliance through Doc2Doc Information Retrieval: A case study in EU/UK legislation where text similarity has limitations](<../papers/Regulatory Compliance through Doc2Doc Information Retrieval: A case study in EU／UK legislation where text similarity has limitations.pdf>)
- **官方来源**：[出版页](https://aclanthology.org/2021.eacl-main.305/)
- **逻辑链**：法律转置关系要求恢复正式制度关联，而主题相似、修订相关或事实有用的文档仍可能是严格负例。论文构造 EU2UK/UK2EU 长文档检索集，并比较 BM25、法律 BERT、EUROVOC 辅助训练 C-BERT、融合与神经重排。C-BERT+BM25 的点估计明显提高首阶段召回，但神经重排常被相似文本的相反标签牵制；年份过滤只在较难的 EU2UK 方向明显有效。
- **创新/价值亮点**：明确建立 DOC2DOC regulatory IR 任务，并以真实法律转置关系而非主题相似度作真值；将非文本时间结构、监督冲突和关系方向非对称性纳入检索诊断。
- **证据边界与 PDF 页码**：EU/UK 转置只是企业 control–regulation 匹配的代理，标题对齐可能残留噪声，年份窗口也可能删去真实提前或延迟转置。任务与数据见 pp. 2–4，方法 pp. 4–6，预取结果 pp. 6–7，重排与时间过滤 pp. 8–9，清洗 pp. 12–13。

#### 029｜R³AG

- **题名**：[R³AG: Retriever Routing for Retrieval-Augmented Generation](<../papers/R³AG: Retriever Routing for Retrieval-Augmented Generation.pdf>)
- **逻辑链**：不同 query 需要不同检索器，参数知识足够时检索反而可能引入冲突或噪声。R³AG 将“不检索”与八个候选检索器统一为动作，用独立监督学习 Retrieval Quality 与 Generation Utility，再做 query 条件化融合和 hard routing。三项英语 QA 上主结果领先所列固定与路由基线，但零重训换生成器后平均略低于最佳固定检索器。
- **创新/价值亮点**：把检索质量与生成可用性明确拆开，并把空检索器作为 routing 的自然特例；检索器 token 化使在线路由不依赖实时采样轨迹，监督成本与延迟也有补充报告。
- **证据边界与 PDF 页码**：只能选单一检索器，RQ 依赖单一 LLM judge，GU 对生成器敏感；表间数值、消融标记与关键训练超参数还有不一致或缺失。问题与定义见 pp. 1–4，训练目标 pp. 4–6，主结果 pp. 7–9，部署与成本 pp. 13–16。

#### 030｜SA-RAG

- **题名**：[SA-RAG: Structured and Adaptive Retrieval-Augmented Generation for Multi-Hop Question Answering](<../papers/SA-RAG: Structured and adaptive retrieval-augmented generation for multi-hop question answering.pdf>)
- **逻辑链**：平铺 top-k 上下文难以表达跨文档关系，固定轮数或手工停止又会造成欠检索与过度检索。SA-RAG 增量维护局部知识图谱，并用只训练轻量策略头的 REINFORCE 在 Retrieve、Search、Complete、Correct、Answer 间路由。六组 QA 上多数答案与覆盖指标领先常规 RAG，KG/RL 消融和 1–5 hop 分层支持结构与策略的贡献，但并非全面超过超大 DeepSeek。
- **创新/价值亮点**：图加边/删边、证据链刷新和动作选择形成结构—控制闭环；准确、覆盖和终止三种奖励直接约束答对、找全与及时停止的冲突目标。
- **证据边界与 PDF 页码**：平均约 191 秒/查询，Complete 与 Correct 可由同一骨干生成和裁决事实；训练样本口径、在线动态性和零样本独立性有限。框架与奖励见 pp. 3–7，主结果与消融 pp. 9–11，效率与限制 pp. 11–13，实现与统计 pp. 14–20。

#### 031｜SafeRAG

- **题名**：[SafeRAG: Benchmarking Security in Retrieval-Augmented Generation of Large Language Model](<../papers/SafeRAG: Benchmarking Security in Retrieval-Augmented Generation of Large Language Model.pdf>)
- **逻辑链**：传统随机噪声、参数冲突和直接拒答指令容易被现有 filter 或强模型绕过，不能代表知识注入链路的真实攻击面。SafeRAG 基于 100 组中文新闻问答构造银噪声、上下文间冲突、软广告和白色 DoS，并分别注入知识库、检索结果或过滤结果。不同 retriever、filter 和 generator 对四类攻击呈现方向不同的脆弱性，攻击越接近生成器通常越有效。
- **创新/价值亮点**：每类攻击针对一种既有防线的具体盲区，并用跨阶段注入区分组件暴露面；RA、事实选择 F1 与 AFR 同时覆盖黄金召回、攻击抑制和载荷进入回答。
- **证据边界与 PDF 页码**：数据仅 100 组且来自单一新闻源；攻击权限、子集规模、evaluator 身份和统计不确定性不清，轻量模型“更安全”混合了拒答与正常能力。攻击动机见 pp. 1–3，数据与构造 pp. 4–5，指标与实验 pp. 5–8，限制 p. 9，完整构造与结果 pp. 11–13。

#### 032｜T²Ranking

- **题名**：[T²Ranking: A large-scale Chinese Benchmark for Passage Ranking](<../papers/T2Ranking: A large-scale Chinese Benchmark for Passage Ranking.pdf>)
- **逻辑链**：中文 passage ranking 同时缺少真实大规模查询、细粒度人工标签和低假阴性的检索/重排统一基准。T²Ranking 汇集 30.7 万查询、230 万段落与约 240 万条四级标注，并用语义分段、训练集聚类去重、主动学习和测试候选尽量全标控制质量。稠密检索的点估计明显高于 BM25，cross-encoder 使用 dense 候选又优于 BM25 候选，说明第一阶段召回继续限制重排上限。
- **创新/价值亮点**：在中文规模、graded relevance、多正例与检索/重排双任务之间取得较完整平衡；将 pooling 假阴性、段落完整性和人工预算分配直接纳入 benchmark 工程。
- **证据边界与 PDF 页码**：查询来自单一搜索引擎，测试全标只覆盖 pool；分段、聚类、主动学习与标注一致性缺少关键参数、消融和统计检验。问题与任务见 pp. 1–3，构造与四级标签 pp. 4–6，统计与基线 pp. 6–8，主结果 pp. 8–9。

#### 033｜The Distracting Effect

- **题名**：[The Distracting Effect: Understanding Irrelevant Passages in RAG](<../papers/The Distracting Effect: Understanding Irrelevant Passages in RAG.pdf>)
- **官方来源**：[出版页](https://aclanthology.org/2025.acl-long.892/)
- **逻辑链**：“无关 passage”不是同质类别：有些文本虽不含答案，却会强烈诱使回答模型不拒答或误答。论文定义 `DE=1-P(NO-RESPONSE|q,p)`，并从标准检索、答案偏斜检索、重排和四类合成修辞中寻找硬干扰。高位与重排后的错误通常更具干扰性；金证据加入硬干扰后七个模型下降约 6–11 点，硬干扰微调主要改善无 gold 场景。
- **创新/价值亮点**：将干扰连续化且只需读取拒答首 token 概率，随后用金证据+硬/弱干扰验证分数的下游区分效度；多源候选的互补胜出率说明单一 hard-negative 生成方式覆盖不足。
- **证据边界与 PDF 页码**：DE 混入指令遵循、参数记忆与首 token 校准，跨模型相关最低仅 0.47；微调还对部分 grounded 样本有小幅代价。定义见 p. 3，候选构造 pp. 4–5，主分布与相关性 pp. 6–7，下游验证 pp. 7–9，模型差异与训练细节 pp. 12–14。

#### 034｜The Power of Noise

- **题名**：[The Power of Noise: Redefining Retrieval for RAG Systems](<../papers/The Power of Noise: Redefining Retrieval for RAG Systems.pdf>)
- **逻辑链**：RAG top-k 中，含答案的 relevant、语义近但无答案的 distracting 与完全无关 random 文档对生成器的作用不同。Oracle 实验显示 distractor 数量增加会大幅伤害准确率，gold 位于中间最弱；足量 random 在 gold 靠近问题的部分设置中反而提高准确率。真实 Contriever/BM25 返回加 random 也出现部分收益，但少量 random、某些模型和位置会先降分或完全无益。
- **创新/价值亮点**：把文档类型、数量、位置和检索现实性放入统一实验矩阵，直接挑战“相似度越高越适合填满上下文”的直觉；Wikipedia、Reddit 与随机词三种 noise 的一致迹象削弱了单一文体解释。
- **证据边界与 PDF 页码**：仅覆盖 NQ-open、短答案和四个 2.7B–7B 量化模型；位置、长度和 token 数混杂，注意力熵机制也只有探索性证据。定义与设置见 pp. 2–5，oracle distractor/random p. 6，真实检索 pp. 7–9，机制与结论 pp. 8–9。

#### 035｜Reliable Legal Retrieval

- **题名**：[Towards Reliable Retrieval in RAG Systems for Large Legal Datasets](<../papers/Towards Reliable Retrieval in RAG Systems for Large Legal Datasets.pdf>)
- **逻辑链**：法律语料的模板化条款会使局部 chunk 检到内容相似却来自错误文件的证据，答案表面相关也无法满足来源可追溯性。论文定义文档级检索错配 DRM，并用 SAC 将每篇文档的短摘要前置到所有局部 chunk 后再建向量索引。四类英文法律文本上，150 字符摘要与 500 字符 chunk 的配置兼顾最低 DRM 与最高精确率；更长或专家摘要并未更好。
- **创新/价值亮点**：将“错误来源”从一般相关性失败中分离，并以 DRM、字符精确率和字符召回率刻画双层可靠性；SAC 只需每文档一次摘要，不改 retriever 或训练模型即可注入文档身份。
- **证据边界与 PDF 页码**：只评检索阶段且残余 DRM 仍高，没有端到端答案、引用忠实或法律专家任务成功；模型、法域、语种和统计报告有限。问题与指标见 pp. 2–5，方法与主结果 pp. 5–8，限制 p. 9，超参数与混合检索 p. 12，模型/提示 pp. 13–14。

#### 036｜Towards Robust Ranker

- **题名**：[Towards Robust Ranker for Text Retrieval](<../papers/Towards Robust Ranker for Text Retrieval.pdf>)
- **官方来源**：[出版页](https://aclanthology.org/2023.findings-acl.332/)
- **逻辑链**：Cross-encoder 无法在全集按自身分布挖负例，只能依赖外部 retriever；单一路 hard negatives 对高容量排序器又常不够多样。R²ANKER 联合 BM25、dense coCondenser 与 learned-sparse SPLADE 的 top 候选，采样 40 个负例训练 ERNIE-base 排序器。MS MARCO/TREC DL 结果领先多项表列基线，但堆叠更多生成器、更强单体或近似 ranker-aware 采样均没有继续提升。
- **创新/价值亮点**：把 hard-negative 来源的匹配范式多样性变成可控变量，并用组合矩阵同时检查训练负例与测试候选分布；进一步把 ranker 蒸馏回 bi-encoder，展示跨阶段教师价值。
- **证据边界与 PDF 页码**：“开放集噪声提高鲁棒性”主要是分类理论类比，未实测假负例率或操纵模型容量；实验集中于英语 MS MARCO 且只有点估计。问题与理论见 pp. 1–5，主结果 pp. 5–8，案例与限制 p. 9，噪声形式化与训练细节 pp. 11–13。

### 4.3 证据卡 037–045

#### 037

- **题名**：[《基于混合检索增强的双塔模型研究》](<../papers/基于混合检索增强的双塔模型研究.pdf>)
- **逻辑链**：军事专业书籍、论文和训练日志在语义深度与词项精确性上需求不同，单一检索通道既难覆盖全部资料，也会在扩大候选后引入排序噪声。方法以定制 BGE-M3 和 BM25+TextRank 分别执行语义与关键词召回，再用 BiLSTM+TextCNN 双塔按 Pairwise Ranking Loss 重排，最后交给通义千问生成。两路混合相对 BGE-M3-only 的 EM 从 0.653 升至 0.681，加入双塔后升至 0.832；双塔相对 BiLSTM/TextCNN 单塔分别高 0.050/0.078 EM。数值说明该闭集设置中的主要增益来自重排而非单纯增加召回通道，但只测最终答案 EM。
- **创新/价值亮点**：召回—重排—生成三段职责清楚，消融能辨认混合召回与双塔重排的相对贡献；BiLSTM 长依赖与 TextCNN 局部模式形成多尺度排序表示。
- **证据边界与 PDF 页码**：语料、60,000 个问答的构建与文档级训测隔离不透明，融合算子、统计不确定性、跨域泛化、成本和军事安全未验证。研究动机与架构见 pp. 2–3，混合检索 p. 4，双塔与生成 p. 5，数据、超参数和 Tables 1–2 见 p. 6。使用 `../LinkRag/.venv` 复检后预检为 `PASS`（7/7 页且无解析告警）；全文、方法图和表格均已另行核对。

#### 038

- **题名**：[《基于混合检索重排序策略的大模型增强方法》](<../papers/基于混合检索重排序策略的大模型增强方法.pdf>)
- **逻辑链**：固定字符切块会破坏自然段落，长上下文模型又可能因正确证据离问题过远而无法利用，即“检索到”与“用得到”并非同一问题。论文先比较固定长度与段落切分，再人为把正确块放在首、中、末位估计位置效应，最后以语义 top-k 内的关键词排名交集加分实现无训练混合重排。段落切分在三个主模型上均优于所测固定切分；ChatGLM3 的 k=50 混合逆序相对语义逆序和混合正序分别高 2.47 与 3.24 个百分点。逆序并非普遍最优：它依赖 `Context + Question` 布局和较长输入，GLM-4 上差异近乎消失，Qwen2 在 k=20/30 时末位反而更差。
- **创新/价值亮点**：把切分、理想位置和现实重排拆成连续实验，区分召回覆盖与生成可利用性；Prompt 顺序消融将“逆序技巧”还原为证据—问题距离效应，并主动展示模型条件性和反向结果。
- **证据边界与 PDF 页码**：自建 1000 题只覆盖中文事实短答，子串判分、三轮均值无方差、混合算法并非标准并集 RRF，完整端到端对照主要集中在 ChatGLM3。设计见 pp. 4–6，数据和指标 pp. 6–7，Tables 1–4 见 pp. 7–10，Prompt/模型消融及负结果见 pp. 11–12。

#### 039

- **题名**：[《忠实性增强的国防政策检索增强生成方法》](<../papers/忠实性增强的国防政策检索增强生成方法.pdf>)
- **逻辑链**：国防政策要求保留官方措辞和章节语境，同时需要防止外部时效信息把错误、冲突或过时内容带入答案。SV-RAG 将章节元数据与内容分别编码，以最高内容相似度动态调节两者权重，再用权威库核查网络与专业文献两条外部信息流。生成阶段固定输出“逐字核心引文 + 受限阐述”；在 494 对问答上，Qwen 3-8b 的忠实度/语境准确性由 Naive RAG 的 3.71/3.65 升至 4.75/4.68。去结构主要损害语境准确性，去验证和去引文主要损害忠实度，但每个消融同时改变多项处理。
- **创新/价值亮点**：将权威措辞、层级语境和外源知识核查统一为端到端目标，并让引文成为答案的显式可审计部分；QAAWR 用查询内容匹配强度自适应分配内容与元数据权重。
- **证据边界与 PDF 页码**：缺少检索 qrels、核查混淆矩阵、引用准确率、评审一致性与显著性检验；显式引文可能影响人工观感，知识安全也未覆盖提示注入或权威库冲突。问题与理论见 pp. 1–2，结构检索、核查和提示见 pp. 3–5，数据/量表 pp. 5–7，对比与消融 pp. 7–8，参数边界 p. 9。

#### 040

- **题名**：[《知识驱动的混合检索增强生成方法在罕见病领域的应用研究》](<../papers/知识驱动的混合检索增强生成方法在罕见病领域的应用研究.pdf>)
- **逻辑链**：罕见病指南既含药名、基因分型和诊断标准等精确实体，也面对同义、口语和描述性查询，BM25 与稠密检索具有互补误差。Med-HyRAG 以 2019/2025 年国家指南覆盖 207 种疾病，并行运行 BGE-large-zh-v1.5 与 BM25，再以无训练 RRF 融合名次并用受限提示要求依据不足时拒答。其 Precision@1/Recall@10/mAP@10/NDCG@10 为 0.53/0.88/0.65/0.71，四项表内最高；相对 BM25 的绝对增益仅 0.02–0.04。相对 HyDE 的主要优势是 Recall@10 +0.10，而首位精度和 NDCG 只高 0.02/0.01；没有量化最终答案正确性、忠实度、拒答或幻觉。
- **创新/价值亮点**：用相对名次融合避免异构分数标定，并为每个问题标注原始文本块，匹配标注 Cohen's κ=0.87；权威指南、可追溯 qrel、混合检索与证据不足拒答提示形成完整原型链。
- **证据边界与 PDF 页码**：问答总量、划分、qrel 口径、中文分词、top-k 和验证集隔离未披露；所谓跨三模型稳定没有数值，生成优势只凭单个案例，不能推出临床安全。互补动机见 pp. 1–2，切块/BGE/BM25/RRF p. 3，提示和标注 p. 4，Tables 3–4 见 p. 5，生成个案与边界 p. 6。

#### 041

- **题名**：[《自适应混合检索增强大模型的农作物病虫害智能问答方法》](<../papers/自适应混合检索增强大模型的农作物病虫害智能问答方法.pdf>)
- **逻辑链**：农业知识分散且异构，病虫害问题又包含口语术语、单实体事实与多实体关系推理，固定分块和单一检索难以同时覆盖。AHR-RAG 先用重叠定长分块和主题向量过滤入库，再以术语映射、规则和 UIE 路由查询；论文一处写成多跳在 SQL 与 DVR 之间选择，另一处又写成两路经 RRF 融合，因此只能确定它结合了结构化检索与向量检索，无法唯一还原控制流。自建数据上 Qwen1.5-7B-Chat 的 Precision/F1 达 0.896/0.884；去检索后 F1 降至 0.829，是三项管线消融中最大降幅。单跳 F1 为 0.908、多跳为 0.735；K=8 的 Precision/Recall 又低于 K=5，但所谓 Recall 会随 K 下降，显示它可能混入生成噪声而非纯召回。
- **创新/价值亮点**：查询路由结合农业术语归一化、触发规则与实体/关系识别，是面向领域口语和复杂度差异的可解释控制设计；系统联合使用结构化字段定位与稠密语义背景，并按基座、问题类型和组件分组比较。
- **证据边界与 PDF 页码**：路由准确率、知识抽取质量、qrels、开放式答案评分、基线复现和文档级去泄漏缺失；多跳“二选一”与“两路融合”的文字冲突也限制复现。PubMedQA 设置不透明，且未单测农药剂量与拒答安全。数据与知识库见 pp. 1–3，分块/路由/检索/提示 pp. 3–5，指标与 top-k p. 6，总体/迁移/复杂度/消融 pp. 7–8。

#### 042

- **题名**：[《面向五运六气理论的图增强混合检索方法研究》](<../papers/面向五运六气理论的图增强混合检索方法研究.pdf>)
- **逻辑链**：五运六气问答既要精确识别规范术语，又要恢复“运气—病机—证候—治法”的跨层理论链，并约束模型不混入参数记忆。FMSQ-GAR 将 BM25、BGE 稠密和 TF-IDF/N-Gram 稀疏检索以加权 RRF 融合，再用 Louvain 社区知识图谱补充结构候选，并经关键词筛选和 BGE-Reranker 两阶段重排。四个基座加入完整系统后五项指标同向上升；Qwen3-32B 综合分从 0.4078 升至 0.5124，禁用图增强后降至 0.4620。三个“仅单路”变体仍保留图、重排和受控生成，因此只能证明完整配置优于替代配置。
- **创新/价值亮点**：将词项、稠密语义、稀疏局部模式与图社区结构放进分层召回链，使术语命中和关系邻域恢复成为两个明确目标；图增强消融有 5.04 个百分点差值，四个不同基座均获同向端到端增益。
- **证据边界与 PDF 页码**：400 个问答与知识库高度同源，图抽取质量、检索机制、引用定位和统计显著性未验证；综合分权重主观，回算值与表值有小幅差异。问题与架构见 pp. 1–3，图/RRF/重排/引用提示 pp. 4–5，图谱统计 pp. 5–6，对比与消融 pp. 7–8，未完成的引用验证和临床边界 p. 9。

#### 043

- **题名**：[《面向工艺规范的树结构检索增强生成方法研究》](<../papers/面向工艺规范的树结构检索增强生成方法研究.pdf>)
- **逻辑链**：工艺参数常写在子段落，而对象、条件和出处写在父级标题；朴素固定块会失去归属信息并召回表面相似但数值错误的参数。TSR 把规范名、全部祖先、当前段落和线性邻近兄弟段落恢复为最小子树，并以“检索前/检索后 × 有/无兄弟”构造四种变体。最佳 TSR_b 在八个 6B–14B 模型上相对 RAG_250 的 ACC、ROUGE-L、BLEU-4 平均约高 3.80、3.29、2.97 分；检索前结构化明显优于检索后补树。父段落和兄弟段落消融均为正，但 TSR_b 提示长度约为 RAG_250 两倍，且没有检索命中率证明结构改善初召回。
- **创新/价值亮点**：直接利用规范原生章节编号恢复树，无需训练结构模型或由 LLM 生成摘要；二维变体与逐层消融把结构介入时机、父级限定和兄弟关联分开比较。
- **证据边界与 PDF 页码**：数据仅含单一型号飞机的 5 本规范和 311 个同源问答；树解析准确率、qrels、显著性、提示与索引参数、存储及更新成本未充分报告。错误案例和动机见 pp. 1–3，树对象与四种 TSR pp. 4–7，主对比/时机实验 pp. 8–9，层级消融与 token pp. 9–10，时间结果 p. 11。

#### 044

- **题名**：[《面向检索粒度的检索增强生成技术研究综述》](<../papers/面向检索粒度的检索增强生成技术研究综述.pdf>)
- **逻辑链**：RAG 检索单元存在基本张力：粗粒度保留上下文却增加冗余和成本，细粒度提高定位精度却可能割裂推理所需关系。综述把文档/段落归为粗粒度，把句子/三元组/实体归为细粒度，再把跨粒度组织归纳为并列融合、级联处理与自适应调度。文献地图显示粒度越细越需要通过上下文建模、子图或推理链恢复语境，而混合粒度把困难转移到融合、调度和置信度校准。作者提出命题级检索、动态粒度选择和结构化—非结构化协同议程，但没有统一基准证明任何粒度普遍更优。
- **创新/价值亮点**：将“粒度”提升为一级分类轴，用完整性—精确度权衡统一解释分块、图检索、压缩、过滤和动态调度；区分基本检索单元与跨单元组织方式，七张比较表提供高密度导航。
- **证据边界与 PDF 页码**：这是叙述性综述，缺少完整检索式、初检/去重/排除流程、双人筛选、质量/偏倚分级和统一效果量，不能据此排序方法成熟度或效果。定义和图 2 框架见 pp. 1–3，文档/段落 pp. 3–7，句子/三元组/实体 pp. 7–11，混合粒度与议程 pp. 11–13。

#### 045

- **题名**：[A Reality Check on Context Utilisation for Retrieval-Augmented Generation（ACL 2025 正式版）](<../papers/A Reality Check on Context Utilisation for Retrieval-Augmented Generation〔ACL 2025〕.pdf>)；[arXiv:2412.17031v2](<../papers/A Reality Check on Context Utilisation for Retrieval-Augmented Generation〔arXiv 2412.17031〕.pdf>)
- **逻辑链**：RAG 获益既需要检索器取得有用证据，也需要生成模型真正利用证据；合成上下文可能遗漏真实检索的噪声、信息不足和来源差异。DRUID 以 1,329 条真实事实核查声明和 5,490 个检索证据样本进行人工相关性/立场标注，ACU 衡量加入证据后三标签概率是否朝期望立场移动。真实样本中约 49.7% 证据不足；合成数据中的支持偏好和反驳排斥未稳定迁移到 DRUID，且 Llama/Pythia、zero-shot/三样本提示差异很大。没有单一相似度、长度或风格特征能稳定解释真实上下文利用，组合属性更有解释力，但结果只是相关。
- **创新/价值亮点**：将真实检索重新纳入上下文利用研究，并用充分/四类方向性不足/反驳标签保留现实证据的连续结构；ACU 区分“答案变化”与“变化方向符合证据”，使上下文利用成为独立于最终正确率的被测层。
- **证据边界与 PDF 页码**：结论限于英语事实核查、单条证据和两种 7B/8B 模型，商业检索快照、来源/时间泄漏与提示调优影响外推；ACU 主文 `[-1,1]` 与附录 `[-3,3]` 尺度不一致。数据与特征见 pp. 1–6，ACU 和主结果 pp. 7–10，检索/标注细节 pp. 16–21，提示 pp. 22–23，尺度矛盾 pp. 24–28，完整相关热图 pp. 29–30。两版均 40 页且预检 `PASS`，SHA-256 不同；正式版带 ACL 页眉、版权和 19691–19730 印刷页码，arXiv 版带 arXiv 侧栏。

### 4.4 外部来源 E01–E03（尚未纳入本地 PDF）

#### E01｜Temporal Validity in Retrieval Memory

- **题名/DOI**：*Temporal Validity in Retrieval Memory: Eliminating Stale-Fact Errors for AI Agents over Evolving Knowledge*；DOI `10.48550/arXiv.2606.26511`。
- **已核验逻辑链**：官方摘要报告，在校准数据上余弦相似度区分 contradicted fact 与 duplicated fact 的 AUROC 约为 0.59，矛盾事实可能与原事实比改写后的重复事实更相似；论文使用 subject–relation–object supersession 和双时间账本淘汰旧事实。
- **对本研究的边界**：它直接压缩“相似度无法区分事实冲突”的新颖性，但研究的是演化知识记忆与确定性旧事实替换，不是静态固定候选池中的 Reranker 排序交互、等价对照或三路融合。当前未逐页阅读，除官方摘要信息外不引用方法细节或结果。

#### E02｜FinSAgent

- **题名/DOI**：*FinSAgent: Corpus-Aligned Multi-Agent RAG Framework for Evidence-Grounded SEC Filing Question Answering*；DOI `10.48550/arXiv.2607.18102`。
- **已核验逻辑链**：官方摘要将 prior-corpus misalignment 表述为问题驱动的 query generation 与 semantic ranking 共同造成的管线级错位，明确指出 semantic reranking 会偏爱主题相近但 evidentially invalid 的 false-positive Chunk，并提出 multi-path retrieval 与 learned feature-gated reranker。摘要未足以支持对具体特征类型、训练细节或消融设计的进一步描述。
- **对本研究的边界**：它压缩“首次观察主题相似但证据无效候选被重排晋升”以及同类 feature-gated remedy 的主张；当前摘要未证明本文的等价—冲突受控交互、固定池因果隔离、可识别性分区，或相对 LTR-v3/D3/A0 的同题增量。未逐页阅读前不引用摘要以外细节。

#### E03｜Risk–Reward Trade-offs in Rank Fusion

- **来源**：[Risk–Reward Trade-offs in Rank Fusion](https://doi.org/10.1145/3166072.3166084)。
- **原记录范围**：旧证据表 C12 将其作为融合的查询级风险依据，提醒总体平均可能掩盖部分查询的损失。
- **阅读与使用边界**：旧表没有附逐页阅读记录，本次仅迁移已有来源，没有重新核验全文；它不证明当前候选方法有效，也不替当前研究确定指标或实验门槛。

## 5. 覆盖与版本附录

### 5.1 历史盘点：48 个物理文件归并为 45 个论文实体

| 实体 | 物理文件关系 | 核验结果 |
| --- | --- | --- |
| 016 *Language Model Re-rankers are Fooled by Lexical Similarities* | 主文件 + `〔重复副本〕` | 两文件均为 604,585 bytes、16 页，SHA-256 均为 `1e80e5bfc6352d932f7ccbd72e9b9ac13bfedda501bf0a52256c5c745cbe95d6`；字节级完全重复，只计一个实体 |
| 023 *RARE: Redundancy-Aware Retrieval Evaluation Framework for High-Similarity Corpora* | ACL 2026 正式版 + arXiv 2604.19047v2 | 两版均 26 页，但 SHA-256 分别为 `13dedadcffcb291377788ac08d55adc77df00e09e05ade623d9fd210ad377c63`、`bf6574c16cb48e24d516b31753b45b5ea22c8da7c7701b498c0560098b8c12c2`；版式与出版标记不同，只计一个实体 |
| 045 *A Reality Check on Context Utilisation for Retrieval-Augmented Generation* | ACL 2025 正式版 + arXiv 2412.17031v2 | 两版均 40 页，但 SHA-256 分别为 `da62552e6b28b42bf2cf38efeafbbd0e88bf69d0ee815f33d12e0b2714cf54e7`、`dc55c0cdd287cc304a8fdb6e3df8b6c36c28f0b5421f68d3e27682623f621259`；版式与出版标记不同，只计一个实体 |

归并公式：`48 - 1（完全重复的额外副本）- 1（023 的版本对）- 1（045 的版本对）= 45`。

### 5.2 同缩写但不同论文的 RARE

- **023**：*Redundancy-Aware Retrieval Evaluation Framework for High-Similarity Corpora*，对象是高相似/高冗余语料、等价事实证据、RedQA 构造与 PerfRecall。
- **024**：*Retrieval-Aware Robustness Evaluation for Retrieval-Augmented Generation Systems*，对象是查询、文档与真实检索扰动下的条件化答对/拒答鲁棒性。

两者不是版本关系，也不是同一方法的后续稿；除缩写相同外，题名展开、作者、数据、任务、指标和结论均不同。

### 5.3 历史文件覆盖核对（2026-08-28）

- 42 个实体各对应 1 个 PDF。
- 016 对应 2 个字节级相同 PDF。
- 023 与 045 各对应 2 个不同版本 PDF。
- 合计 `42 + 2 + 2 + 2 = 48` 个物理文件；证据卡为连续的 001–045，共 45 个实体。
- 当时快照没有未映射 PDF、缺卡实体、引用不存在 PDF、未说明的重复文件或被误拆成两项证据的版本对。
- E01/E02/E03 不属于上述本地快照，故不改变 `48 个物理文件 / 45 个本地实体` 的覆盖分母；待取得全文并完成逐页核验后，再决定是否并入本地编号卡和覆盖统计。
