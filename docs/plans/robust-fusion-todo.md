# 高相似度干扰下检索增强生成的多路来源感知鲁棒融合方法研究：研究推进清单

> 用途：本文档是该研究主题的任务管理与证据台账，不替代科研或工程协议。
> 科研协议：[robust-fusion-research.md](robust-fusion-research.md)
> 工程协议：[robust-fusion-engineering.md](robust-fusion-engineering.md)
> 文献依据：[robust-fusion-literature.md](robust-fusion-literature.md)
> 证据收束：[robust-fusion-evidence.md](robust-fusion-evidence.md)
> 发表规划：[robust-fusion-publication.md](robust-fusion-publication.md)
> 研究记录：`ROBUST-FUSION-PROGRESS-2026-08-29-v28`
> 当前阶段：`P2 构念、标注与指标效度`
> 当前任务：`P2-01 冻结核心构念与操作化规则`
> 最近更新：2026-08-29

## 1. 使用规则

1. 任何时候只允许一个 `[-]` 任务；对话默认只讨论该任务和最多两个后续任务。
2. 每个任务必须同时写明“产出物”和“完成标准”；没有可核验证据时不得标记完成。
3. 研究设计、数据或分析口径变更时，必须记录原因、变更时间和是否已经看过结果。
4. `Gate A` 和 `Gate B` 只能由预先冻结的证据规则判定，不因为点估计“看起来不错”而通过。
5. 工程测试只能证明测量工具可信，不能代替对 RQ 和假设的科学检验。
6. 本清单由当前研究对话持续维护；每次推进后至少更新当前任务、完成证据、决策记录和下一任务。

> **状态说明**：`[x]` 表示已完成并有证据；`[-]` 表示当前正在推进；`[ ]` 表示尚未开始；`[！]` 表示受阻，且必须写明阻塞原因。

### 1.1 Gate A 前的职责分类

| 代码 | 类型 | 处理方式 |
| --- | --- | --- |
| `A` | 我可独立完成 | 进入当前任务后直接做，提交文档、数据、代码或分析产物 |
| `J` | 需要我们讨论 | 我先提供推荐方案、备选方案和取舍，你确认后冻结 |
| `U` | 完全需要你/学生团队 | 我可准备表格和操作材料，但关键输入必须由你们提供 |

### 1.2 Gate A 前的实际分工

| 阶段 | `A` ：我直接完成 | `J` ：我们讨论后冻结 | `U` ：你/团队提供 |
| --- | --- | --- | --- |
| P0 逻辑收口 | 修订 Gate A 前流程、数据用途表、样本量、停止规则、数据集分母时间戳和变更台账 | 当前无待讨论项；若未来改变 Gate 角色或允许第二研究周期，必须重新讨论并换研究 ID | 无 |
| P1 文献证据 | 建立主张—证据—空缺表，核验最相近工作，起草研究缺口 | 确定最近强基线清单和最终新颖性声称 | 无 |
| P2 构念与标注 | 起草操作化定义、标注手册、样例、仲裁表和指标规范 | 确定边界案例、不确定标签处理和一致性目标 | 安排两名标注者；按手册完成独立校准和规定比例复核 |
| P3 数据与模型 | 先审计仓库现有非 Blind 开发材料；再下载/审计公开数据，生成文件摘要，分析 qrels/corpus，建议 Reranker 候选 | 选择两个 Reranker，冻结计算预算和数据纳入/排除规则 | 只在现有非 Blind 材料审计后仍有缺口时，补充最少的内部 Query/文档/正确证据；如有外部 API/算力限制，告知可用额度 |
| P4 测量工具 | 完成快照生成器、离线实验器、EG 指标、数据视图隔离、重放一致性和工具校准 | 仅在实际运算成本或 LinkRag 口径存在多个合理方案时讨论 | 如必须使用当前不可用的外部服务，提供访问条件 |
| P5 校准与预注册 | 运行校准分析、估计方差/效应量/可构造率，做功效分析，起草预注册 | 冻结最小实际效应、功效目标、样本量上限和 Gate A 规则 | 确认团队能承担的最大 Query/标注/计算预算 |
| P6 Gate A 研究 | 验证并只读加载 P5 已封存快照，运行两个 Reranker 和基线，完成统计、异常审计和报告 | 处理预注册未覆盖的异常；最终判定 `Go / Inconclusive / No-Go` | 完成候选内容复核、false negative 审计和分层双人复核 |

### 1.3 默认协作方式

- 大部分工作是 `A`：我会按当前任务直接做，不把所有细节反过来让你执行。
- 只在 `J` 节点暂停：每次最多讨论 1—3 个对后续有实质影响的选择。
- `U` 任务集中在现有材料审计后仍缺失的内部样本、资源上限和人工复核；我会在真正需要时给出最小操作包。

## 2. 当前推进窗口

### [x] P1-04 形成引言所需的问题链和研究缺口段落草稿

**目的**

把已经冻结的证据链转成可直接进入论文初稿的引言问题链，使已有发现、研究空缺和本文研究动作逐段对应。

**完成结果**

- 按“候选分布条件性 → 相似不等于事实有效 → 等价/冲突对照 → 多路互补与污染 → 近邻工作边界 → 已有方法边界 → 本文研究动作”形成七步引言骨架；
- 所有已有发现均指向已核验来源，研究空缺限定为截至 2026-08-28 的定向检索范围；
- Gate A/B 前只使用计划式研究动作，不预写方法有效或跨域稳健等结果结论。

**输入**

- [主张—证据—空缺表第 2—4 节](robust-fusion-evidence.md)
- [定向文献地图](robust-fusion-literature.md)

**产出物**

- 七步引言问题链草稿；
- 一段受限的研究空缺表述；
- 一条 Gate A/B 前的结果措辞护栏。

**职责分工**

- `A`：我已完成问题链组织、段落起草和证据边界检查。
- `J`：当前任务不需要新增研究决策。
- `U`：当前任务没有。

**完成标准**

- [x] 每段只推进一个判断，并能追溯到主张表中的证据或待检验空缺。
- [x] 没有使用“全球首次”“尚无任何研究”等无边界否定。
- [x] 引言目的段与 RQ1—RQ3、Gate A/B 的实际研究动作一致。

**本任务暂不做**

- 不根据尚未产生的实验结果撰写摘要或贡献结论；
- 不扩展文献检索范围；
- 不改动已经冻结的 RQ1—RQ3。

### [-] P2-01 冻结核心构念与操作化规则

**已冻结的第一项决策**

实验相似度固定测量待测压力/对照 Chunk 与其唯一目标等价组的 Clean 正确参照 Chunk 集之间的最大余弦相似度 \(S_{qg}(c)\)，不是 Query—Chunk 相似度，也不与方法特征中的候选—近邻相似度混用。H2 以连续的候选—目标正确参照相似度×事实关系交互作为主检验；预注册低/高相似分带只用于 2×2 受控复核，不声称为学界通用阈值。等价与冲突候选共用同一组分带边界，中间模糊区保留给连续分析，分带不得依据被测方法结果调整。连续交互只在等价与冲突样本均有实际覆盖的共同支持区间内估计，避免把两类样本所在相似度范围不同误写成事实关系效应。

**已冻结的第二项决策**

Query—Chunk 人工真值固定拆成 `relevance_status`、`target_relation`、`adjudicability` 三个正交字段，候选对另用 `candidate_pair_relation`。真值未知排除确认性分析；评价真值已知但 method view 不可识别的样本保留为 C2 边界。原始 qrel 永不覆盖，人工复核另存证据定位、理由、人员、状态和手册版本。

**完成标准**

- [x] 冻结实验相似度的测量对象为“待测 Chunk—正确参照 Chunk”，并与方法近邻相似度分离；
- [x] 冻结“连续交互主检验 + 2×2 分带复核”的实验角色，避免 H2 取决于单一切点；
- [x] 冻结等价/冲突共用分带边界、中间模糊区保留给连续分析、不按方法结果调整分带的原则；
- [x] 冻结连续交互只在等价/冲突共同支持区间内估计，并报告覆盖率与排除尾部；
- [x] 冻结每个确认性候选唯一锚定 `target_equivalence_group_id`，相似度与事实关系使用同一参照组；
- [x] 冻结正交关系 schema、四类原子冲突、事实等价/普通错误边界，以及“真值未知”与“方法不可识别”的区分；
- [x] 冻结原始 qrel 不覆盖、人工 adjudication layer 独立存储和公开未判断 pair 不自动作负例；
- [x] 建立[实验相似度 manifest](robust-fusion-similarity-manifest.md)，冻结必填字段、逐值重放规则和 Gate A 拒绝条件；
- [x] 完成并关闭 BGE-M3 候选审计：历史官方制品曾完成资格核验，但研究负责人在 Gate A 前明确淘汰；真实 Learned Sparse 是 Ark/豆包在线 API，BGE 不得进入 route、\(S_{qg}(c)\) 或独立审计；
- [x] 在不读取研究数据时完成两个非 BGE 编码器的资格预选，冻结模型/tokenizer exact revision 与摘要、输入前缀、截断、pooling、维度、向量归一化、余弦精度和固定探针重放；
- [ ] 完成相似度测量最终冻结：两个 Reranker 与预选相似度编码器无制品复用已经确认；下一步以 v5 Dev route evidence 固定 \(A_{qg}\)，完成长短文本分层的 E5/DistilUSE—盲人工效度，并封存成员 ID、内容/向量摘要、计算代码与配置摘要，使正式分数可逐值重算；
- [ ] 在 `v6-Dev` 冻结数据源内标准化参数、共同支持区间规则及最低覆盖率、主模型形式、低/高分带、相邻敏感性边界和独立相似性审计量表，并于 Gate A 前锁定；
- [x] 冻结事实等价、事实冲突、良性冗余、错误共识和疑似 false negative 的操作边界。

## 3. 研究总路线

### P0 研究逻辑与治理收口

- [x] **P0-01 冻结题目、边界、RQ 和贡献结构**
  - 证据：科研协议 v26 保持题目和 RQ1—RQ3，并将贡献收束为主要 C1、诊断 C2 和条件性 C3。
- [x] **P0-01A 将高成本候选图收缩为 Top-M 局部统计**
  - 证据：主文档已排除持久化候选图、GNN、聚类、Route Fragility、学习门控和 RL 干扰生成。
- [x] **P0-01B 建立本研究推进清单**
  - 证据：本文档。
- [x] **P0-01C 全面重构当时的总研究协议**
  - 证据：科研协议前身 v8 已按“问题—构念—数据—仪器—实验—方法—统计—门禁”重排，删除重复和高成本偏题内容，并把术语解释放在首次使用处及概念速查中。
- [x] **P0-01D 拆分科研协议与工程实施协议并缩短文件名**
  - 证据：该次拆分形成科研协议 v9 与工程协议 v1；当前分别演进为[科研协议 v26](robust-fusion-research.md)和[工程协议 v17](robust-fusion-engineering.md)，职责边界保持不变；本研究专题文档统一使用 `robust-fusion-*` 短文件名。
- [x] **P0-02 重构 Gate A 前的研究阶段**
  - 证据：主文档第 5.2、9 节已将内部母池分为 `v6-Dev / v6-GateA / v6-Blind`，并将“≤100 Query”限定为校准先导预算；Gate A 样本量改由功效分析冻结。
- [x] **P0-02A 闭合第二轮审稿提出的 Gate 治理缺口**
  - 证据：科研协议 v26 沿用 v12 已明确的 Gate A 停止规则、正向单元、层级比较家族、分阶段实际效应、确认性 pooled estimand、反伪影组合、Track B 后果和无环外部时间戳，并保留 v13 的正交标签 schema；工程协议 v17 已把 current-HEAD 契约复验、provider-managed 路由的单次生成/结构校验/哈希封存、CI 重钉、公开正文 ID/hash 对账、DuRetrieval 完整保留、cMedQA2 本地全文治理、v6-Dev 双审锁定/仲裁、三路证据完整性与 Gate 人口拒绝列为硬前置。
- [x] **P0-03 建立研究决策与变更记录模板**
  - 证据：本清单第 6 节固定“日期、决策、依据、是否已观察结果、影响”五列，并已用于全部协议变更；Gate A 准入审计另以 outcome-blind JSON 固定完成项与阻塞项。

### P1 文献证据与新颖性边界

- [x] **P1-01 建立“主张—证据—空缺”文献表**
  - 证据：[独立证据台账](robust-fusion-evidence.md)已形成 21 条核心主张、证据等级、未证空缺和研究响应。
- [x] **P1-02 逐篇核验最相近工作的一手论文与实际方法边界**
  - 证据：证据台账第 4、8 节与文献地图；已核对 Hagström、HybRank、RARE、Regulatory、Contextual Relevance、MoR、QuDAR、R²ANKER、Hard Negatives、DocReRank 等一手页面和本地全文边界。
- [x] **P1-03 冻结最低强基线范围与可声称的新颖性**
  - 证据：Gate A 前不训练 D3/A0/M1，也不复现 HybRank/QuDAR；Gate A = `Go` 后，D3 与 A0 作为和 M1 同步实现的最低容量匹配基线，完整近邻强基线再单独审批计算预算。
- [x] **P1-04 形成引言所需的问题链和研究缺口段落草稿**
  - 证据：主研究文档第 2.4 节已形成七步引言骨架，并对已有发现、待检验空缺和研究动作作分层表述。
- [x] **P1-05 纳入时间有效性与金融问答近邻工作并收紧新颖性**
  - 证据：科研协议、证据台账和文献地图已记录两项 2026 近邻工作；不再把一般现象发现或长合取空缺作为创新，C1/C2/C3 分别承担独立贡献。

### P2 构念、标注与指标效度

- [-] **P2-01 冻结核心构念与操作化规则**（当前任务，见第 2 节）
- [x] **P2-02 编写 Query—Chunk 关系、等价组和四类冲突的标注手册**
  - 证据：[标注手册 v2](robust-fusion-annotation-handbook.md)已覆盖正交 schema、标注顺序、四类冲突、false-negative/unknown、候选对标签、证据要求和仲裁，并在 P2-05 通过后正式冻结。相对 v1 只增加确定性算术/单位/日历规则与 `detectable_only` 边界澄清。
- [x] **P2-03 设计双人校准、一致性统计和仲裁流程**
  - 完成证据：[标注手册 v2 第 9.4 节](robust-fusion-annotation-handbook.md)保留了人工结果产生前冻结的小样本计数准入线、关键构念零容忍项、facilitator key 对照、失败重放和解锁规则；alpha/macro-F1 保留为诊断量，不在 13 条记录上设不稳定的单点门槛。
- [ ] **P2-04 冻结 EG-nDCG、EG-MRR、翻转率和相似度分带的测量规则**
- [x] **P2-05 在小规模 Tune 样本上完成标注者校准并修订手册**
  - 完成证据：v2 首轮失败记录完整保留，5 个制品缺陷案例以 `ROBUST-FUSION-P2-CALIBRATION-PATCH-2026-08-29-v3` 一对一替换；A/B 在隔离目录重新盲标。最终合并 12 例、13 条候选、9 条事实冲突和 1 条候选对：资格 12/12、`target_relation` 13/13、冲突类型 9/9 三方一致；冲突可裁决性 A–B 8/9、A–key 9/9、B–key 8/9；格式与零容忍构念错误均为 0。唯一旧分歧按发包前已澄清的确定性算术规则仲裁。最终机器结论 SHA-256 `fe906b9e755135cfe4fe6607297aec5c5a0c2b2c0a0a5118e4c38ada9a01ef1c`，提交锁 SHA-256 `9d743fb23d4d88d128229a81d381aab444550e2663e11eacbe296cad0c722f82`；Gate A/B 均未运行。
- [ ] **P2-06 冻结 Gate A 硬资源包和越界缩减顺序**
  - 需与用户讨论并写死：最大唯一 Query、单 Query 人工候选上限、双审条数/人时、API token/费用、GPU 小时；功效需求越界时按 `n=100 饱和敏感性 → 第二种子 → 额外数据集/第三 Reranker → 完整 HybRank/QuDAR` 顺序缩减。`n=50` 是保留 C3 时不可删的主剂量；仍无法承担时在 Gate A 前收缩为 C1/C2。核心 H2、两个 Reranker、两个以上数据集和 false-negative 审计不先删除。

### P3 数据、样本与模型冻结

- [x] **P3-00 恢复并盘点现有真实评测资产**
  - 证据：[SQLite 与检索资产对账报告](../reports/sqlite_share_restore_and_asset_reconciliation_2026_08_28.md)；已恢复三份工作副本，并确认主 SQLite、BM25、Alt Embedding 和当前 eval Qdrant 的覆盖关系。
  - 边界：这是工程资产盘点，不替代 P3-01—P3-04 所需的正式 corpus/query/qrels revision 和三分研究样本；确认性快照不得混合当前与历史 Qdrant collection。
- [x] **P3-01 下载并审计 T2Retrieval、MedicalRetrieval、DRUID 与替代数据实体**
  - 完成证据：[Gate A 数据覆盖审计 v10](../reports/robust_fusion_gate_a_data_coverage_audit_2026_08_28.md)已记录原始 T2Ranking、C-MTEB T2、原始 Multi-CPR Medical、C-MTEB Medical、Lo/DRUID，以及 DuRetrieval、上游 cMedQA2/C-MTEB Cmedqa 的固定 revision、许可、实际 schema、SHA-256、行数、唯一键和跨实体 provenance 对账；v2 ID/hash-only 制品同时锁定 DuRetrieval 100,001/2,000/9,839 三实体零删减，并把 C-MTEB Cmedqa 的 100,001 条拆为 88,242 条 Du-only、7,137 条 cMedQA2-only、2,086 条 both、2,536 条统一未解析审计记录。
  - 边界：完成的是实体摄取、替换选择与资格规则，不表示最终 Gate A/B 样本分母已经封存。
- [ ] **P3-02 固定 revision、许可证、文件摘要、corpus/qrels 结构和纳入排除规则**
  - 已有进度：`ROBUST-FUSION-GATE-A-ELIGIBILITY-2026-08-28-v1` 已生成 ID/hash-only 资格清单并重放全部 pinned 文件摘要：T2 Train 258,042 个 Query 的资格上界完整保留，Dev 24,831 个 Query 全部 exposed-only；cMedQA2 排除 80 个跨 split family 后，Train/Test 资格上界为 99,894/3,954；DuRetrieval 100,001/2,000/9,839 三实体零删减且只作辅助分析。Internal v6 的 30-family 首批机械结构产率为 24/30，恢复后的 30 个提案完成双审仲裁，人工接纳 28/30。该 Dev 结果不是最终分母。剩余工作是 document/version/template family 扩展排除、自然来源构造率、功效预估和 Internal v6 确认性人口，再封存三数据集最终分母。
- [ ] **P3-03 按 Query、文档族和反事实模板完成分组划分**
- [ ] **P3-04 准备并物理隔离 Internal Stress v6-Dev、v6-GateA 与 v6-Blind**（正式骨架与 Dev 合成先导完成，确认性人口未完成）
  - 已有进度：[Internal Stress v13 数据协议](robust-fusion-internal-stress-v6.md)、初始化脚本和本地 `data/robust_fusion/internal_stress_v6/` 已建立唯一数据 ID、三个独立目录/cohort manifest、GateA/Blind 方法访问锁、source/exposure 台账、四张摄取模板与 `manifest.sha256`。DeepSeek 首批 30 次调用得到 24 个结构合格提案；四段恢复链累计 43 次调用后形成 30 个结构合格提案。A/B 各完成 30+90+90 行，六份提交先锁后比，机械错误与 unresolved 为 0；候选级标签全部一致、候选对 89/90 一致，唯一分歧已仲裁。最终接纳 28/30（93.33%）并物化 28/112/112/28 release。Dev 三路 v2/v3 失败和 v4 完整性拒收均保留；独立 v5 已完成 28 Query、112 Chunk、3,056 候选，三路各 28/28 非空，112/112 已标注候选及 28/28 gold target 入候选并集。plan/manifest/content root、SQLite/FTS5 与真实 Qdrant 112 点已独立核验。C2 8 槽空白补充 manifest SHA-256 `ff4e00d857641a2d48e0ece509c29bf357f28918757dc4a1980f9906a681f347` 已独立核验。
  - 未完成边界：C2 补充仍为 0 正文/0 人工标签。分享包、旧 eval MySQL 与服务器仍没有可继承的 Query/qrel 行；GateA/Blind 仍无独立自然来源锚点人口并保持 `NOT_ELIGIBLE`。28 个 Dev family 和 v5 route evidence 不得迁移进确认性 cohort。仍需扩展 family 语义零交集、自然候选配额、构造率/功效分母和正式 seal。
- [ ] **P3-05 选择并冻结两个独立家族的语义 Reranker**
  - 已有进度：研究负责人已在结果不可见时正式冻结 `Qwen/Qwen3-Reranker-0.6B@e61197ed…`（生成式、Apache-2.0）与 `jinaai/jina-reranker-v2-base-multilingual@9cfeff2d…`（跨编码器、CC-BY-NC-4.0）。`ROBUST-FUSION-RERANKER-QUALIFICATION-2026-08-28-v2` 已复核精确权重/config/tokenizer/custom code、1024-token 合成探针、正逆序 float32 分数重放、基本中英文相关性以及与 E5/DistilUSE 无制品复用。Jina 还被独立 FEVER 2025 多 Reranker 研究采用（DOI `10.18653/v1/2025.fever-1.2`），但不据此声称其天然最优。
  - 未完成边界：P2-06 尚未冻结 batch size、推理精度、硬件/GPU 小时和成本上限；Dev 的 1024-token 覆盖与正式快照逐值重放也未完成。因此 `p3_05_complete=false`，不得按 Dev 效果换家族，也不得据合成探针分数声称研究现象成立。
- [ ] **P3-06 估计自然干扰、等价冗余和反事实干扰的可构造率**
  - 已有进度：受控合成 Dev 的首批机械结构产率为 24/30（80%）；恢复链后的 30/30 只表示结构合格提案齐备；双审仲裁后的人工接纳率为 28/30（93.33%）。v5 已测得本批合成 Dev 的已标注候选与 gold target 候选并集覆盖均为 100%，但这不是自然候选产率，也不能替代 GateA/Blind 的自然来源构造率。

### P4 研究测量工具

- 工程契约统一见[工程实施协议第 5—10 节](robust-fusion-engineering.md)；本节只维护任务状态和完成证据。
- [ ] **P4-00 完成 current-HEAD LinkRag/LinkRag-Eval 候选契约复验与 CI 重钉**（独立工程 preflight，可与当前 P2 并行，不等待 P3 样本）
  - 已完成部分：Eval 薄适配已去除 `BucketRouter`/旧参数，显式解析 eval collection；CI 与依赖说明已重钉 LinkRag `861f2481…`；Python 3.11 非集成全测、import-lint、`candidate_hits/route_hits`/缺路/截断契约、LTR-v3 三个固定向量以及 SSH 隧道真实 Qdrant 集成均通过。真实 Learned Sparse route 已确认是 Ark/`doubao-embedding-vision-251215`，BGE 被 preflight 排除；协议 v18 下 Dense/Sparse 四探针曾逐值重放通过。
  - 历史重放证据：协议 v19 联动刷新时，在线 `text-embedding-v4` 在 `zh_short` 首项出现一次只知 hash 不同、未测幅度的 exact mismatch。负责人随后授权唯一一次只测量诊断；四条探针全部 float32 exact。正式 v2 三路 preflight 又一次通过：Dense/Sparse 四探针均 exact、BM25=`sqlite_fts5`，manifest SHA-256 为 `640e3d52a2f7cfc6f991cefe4d111ae18d09ba3260626a2e927988b5cd17a38a`。这些不可变制品只证明当时的模型/schema/连通性，不再提供数值接纳门槛。
  - 当前在线路由治理：`ROBUST-FUSION-PROVIDER-ROUTE-SNAPSHOT-POLICY-2026-08-29-v2` 不为 Dense/Sparse 设数值误差或 exact 重放标准；获授权快照单次生成，结构校验后哈希封存，禁止因数值差异重跑或择优。本地确定性计算仍须 exact。
  - 剩余硬条件：当前工作区包含既有和本轮未提交修改，双仓不满足正式 `dirty=false`；本轮也尚无远端绿色 CI run ID 和 `contract-lock.json`。在线路由治理不再阻塞，但 P4-00 仍未完成。
  - 最终产出物：`runs/robust_fusion/contracts/contract-lock.json`、本地完整测试报告、绿色 CI run ID/report、双仓 clean commit/tree 与环境摘要。dirty 预检只能诊断，不能完成此任务。
- [x] **P4-01 审计现有候选缓存与快照契约的字段缺口**
  - 完成证据：[候选快照字段缺口审计 v1](../reports/robust_fusion_candidate_snapshot_field_gap_audit_2026_08_28.md)逐层核对 `RecallRequest/RecallResponse`、Eval `StageOutput/Snapshot`、历史 LTR cache 与 SQLite，确认生产 `candidate_hits/route_hits` 足够作为上游入口，并冻结专用双视图快照的根、Query/family、方法候选、评价关系、压力链和访问边界。P4-02 只在 Eval 侧实现，不修改生产 LinkRag。
- [ ] **P4-02 实现最小 Candidate Snapshot Generator**
  - 必须持久化 `target_equivalence_group_id`、`relation_condition`、`pressure_pool_id`、`replacement_chain_id`，并保证这些 evaluator-only 字段不进入 M1。
  - Dev-only 先导：Internal v6 的专用 runner 已由 v5 实证持久化不截断候选并集、逐路 raw score/rank/retrieved flag 和物理双视图，并通过 manifest/content root、SQLite/FTS5、Qdrant 与禁止字段核验；但仍明确写 `formal_p4_02_snapshot=false`。它没有正式压力池/替换链、clean 双仓、绿色 CI 或 `contract-lock.json`，所以不能据此勾选 P4-02。
- [ ] **P4-03 实现最小 Offline Fusion and Reranking Experimenter**
- [ ] **P4-04 实现等价组封顶指标和 Clean/Stress 配对分析**
  - 配对校验必须拒绝相关等价组集合、组级 gain 或 IDCG 发生变化的 Clean/Stress 组合。
- [ ] **P4-05 实现 `method_view` / `evaluation_view` 隔离与泄漏检查**
  - Dev-only 先导已加入禁止字段递归扫描、source ID 不透明映射和双目录输出，并有本地单测；正式 P4-05 仍须在通用快照生成器上完成 evaluation-view 删除/置换不变性与全方法入口验收。
- [ ] **P4-06 完成测量工具的契约、重放一致性和指标校准**
  - 边界：此项只证明实验仪器可靠，不支持 RQ1—RQ3 的研究结论。

### P5 校准先导与预注册

- [ ] **P5-01 冻结校准样本的分层抽样方案**
- [ ] **P5-02 仅在 Tune 上校准相似度分带、Top-M、冲突阈值和抽取规则**
- [ ] **P5-03 估计效应量、方差、代理正类率、可构造率和标注成本**
- [ ] **P5-04 完成 Gate A 的功效分析并冻结独立样本量**
- [ ] **P5-05 预注册 H1—H3、主对比、主指标、CI、共同支持、`q/g/p/a` 重复测量结构、排除规则和 Go/No-Go 条件**
  - 必须逐项冻结：`epsilon_int`、最终 `epsilon_phen`、Gate A 两个诊断量纲的 `epsilon_surf,A(det/adj)`、自然-only 反向界 `delta_nat`、Gate B nAUDC 量纲的 `epsilon_M1`、Top1 翻转非劣界 `delta_flip`、正向单元定义、C1 intersection–union gate、自然样本最低覆盖、置换容差和 Track B 失败后的主张边界。
  - C2 比较家族固定为 `2 个任务 × 5 个比较器 = 10` 项，Gate B nAUDC 固定为 11 项，Top1 安全家族固定为 LTR-v3/D3/A0 三项；冻结各自主终点、Query-family cluster bootstrap、Holm-adjusted 单侧 p 值、分别用于确认和明确低效/非劣判定的 Bonferroni family-wise 95% 单侧同时下界/上界、bootstrap 次数和种子。
  - 冻结所有 pooled estimand 的唯一权重：C1 对六个 `Reranker×数据集` 单元等权；C2、Gate B nAUDC 和 Clean 非劣使用 `Query 内→family 等权→数据集等权` 宏平均；每个 bootstrap 重算同一估计量。
  - Gate B 主 Stress population 固定为高相似 verified factual-conflict 链，冻结每个数据集非零自然候选的 natural/synthetic 配额与取整规则；其他关系、相似带、origin 分层和 `n=100` 不提供备用 Gate 路径。
  - Top1 确证量固定为 5/10/20/50 个干扰中的最坏合并翻转率差，且四个剂量共用同一成对 Clean-correct 风险集；`rho_min,flip` 的覆盖率固定为“family 内共同 Clean-correct Query 比例→数据集内 family 等权平均”，`F_min,flip` 计数至少含一条该类 Query 的 family。冻结两个门槛与 `F_min,nAUDC`，任一已冻结数据集/基线风险集不足时记 `Inconclusive`，不得跳过。
  - H2 每行固定为 `Query × target group × relation × matched pressure chain × Reranker`；20 个候选的目标组相似度先取均值并按数据集 Dev 参数标准化，不得把同一池级伤害复制到候选行。
  - Top1 方法特异翻转率只作描述；等价/冲突比较使用同一方法的 Clean 正确风险集，M1/基线比较使用两方法 Clean 都正确的共同风险集，再做配对检验。
  - `epsilon_M1` 的数值或确定性选取规则必须在训练 M1/D3/A0、观察其 Dev 差值之前冻结，只能依据外部可解释性与基线方差。
- [ ] **P5-06 冻结 Gate A 停止规则和数据集分母**
  - `No-Go` 对当前研究 ID 为终局；只有 Gate A `Inconclusive` 最多允许一次功效支持的预注册追加；Gate B 一次性 Blind 结果失败或不确定均撤回 C3，不得补样后合并。新定义或新样本周期必须作为新研究，不能挽救本研究。
- [ ] **P5-07 生成并资格复核 Gate A 固定候选快照**
  - 只核对样本资格、字段完整性、候选池配对和内容摘要，不运行或读取确认性排序结果；产出只读快照及 manifest。
- [ ] **P5-08 封存 root manifest 并取得外部时间戳**
  - 顺序固定为：冻结快照与协议/代码/配置 root manifest → clean commit/tag → root SHA-256 → 外部时间戳 root hash → 保存不进入 root hash 的 receipt sidecar。数据集分母变化必须先重做功效并重走该顺序。

### P6 Gate A：独立现象与机制研究

- [ ] **P6-01 验证 root hash 与 receipt、解锁并只读加载 Gate A 固定候选池**
- [ ] **P6-02 运行 Clean、`n=20` 的 `(q,g,p)` 成对连续相似度×事实关系交互、2×2 分带复核和 `n=0/5/10/20/50` 剂量研究**
- [ ] **P6-03 运行两个 Reranker、Fixed Fusion、RRF 和 LTR-v3**
- [ ] **P6-04 验证不读取人工真值的初版 Top-M 冲突代理**
- [ ] **P6-05 完成 false negative、截断、顺序、API 失败与上游召回解释审计**
- [ ] **P6-06 按预注册生成效应量、置信区间、跨数据集方向和标注质量报告**
- [ ] **P6-07 形成 Gate A 正式研究报告**

### Gate A 决策点

- [ ] **GA-01 由预注册规则判定 `Go / Inconclusive / No-Go`**
  - `Go`：允许进入 P7，开发唯一方法 M1。
  - `Inconclusive`：只允许一次功效分析支持的预注册追加样本，或收缩为机制/评测论文。
  - `No-Go`：对当前研究 ID 终止新方法路线，不得反复调整冲突定义、数据集或分带以追求正结果；未来新协议不得与本次失败合并为一次成功验证。

### P7 M1 方法开发与冻结

- [ ] **P7-01 基于 Gate A 证据冻结 M1 特征和可用输入边界**
- [ ] **P7-02 实现 D1 density-only、D2 query-constraint-only、D3 matched-capacity untyped-local 和 A0 matched-capacity surface-only**
- [ ] **P7-03 实现 M1 local-conflict-route**
- [ ] **P7-04 仅在 Train/Tune/OOF 上完成训练、调参和消融**
- [ ] **P7-05 冻结 M1→D3 逐特征替换表和 M1→A0 表面信息对照表，并与简单局部去重/配额及硬约束过滤完成解释性对照**
- [ ] **P7-06 冻结特征签名、模型包、配置、随机种子、预先冻结的 `epsilon_M1/delta_flip` 引用、`数据集×基线×nAUDC` Gate B 判定矩阵、3 项 Top1 安全矩阵和分析代码**

### P8 Gate B：方法贡献确证

- [ ] **P8-01 确认 Stress Blind v6 的封存状态与一次性运行清单**
- [ ] **P8-02 一次性运行 Blind 及跨数据集确证实验**
- [ ] **P8-03 逐格运行 M1 相对 Fixed Fusion、RRF、两个 Reranker、LTR-v3、D1—D3、A0、B9/B10 的 11 项 `nAUDC_{0:50}` 判定矩阵，并运行相对 LTR-v3/D3/A0 的 3 项共同风险集 Top1 翻转非劣矩阵**
- [ ] **P8-04 完成 Clean 非劣性、跨数据集方向、泄漏与简单解释审计**
- [ ] **P8-05 形成 Gate B 正式研究报告**
- [ ] **P8-06 运行较小的 Track B 索引级外部有效性研究**
  - 若与轨道 A 方向不一致，保留经 Gate 支持的固定候选池结论，但撤回索引级、端到端和部署泛化主张；Track B 未完成时同样不得使用这些措辞。

### Gate B 决策点

- [ ] **GB-01 判定“方法贡献成立”或“收缩为退化机制/评测论文”**

### P9 论文形成、完整性审计与发表

- [ ] **P9-01 冻结最终可主张的贡献边界**
- [ ] **P9-02 整理方法、实验、统计、负结果和局限性**
- [ ] **P9-03 完成英文主稿及目标渠道格式草稿**
- [ ] **P9-04 执行引用、数据、统计与声称完整性审计**
- [ ] **P9-05 执行独立同行评审、修订和复审**
- [ ] **P9-06 按[发表路径与投稿治理](robust-fusion-publication.md)完成预印本与正式投稿流程**

## 4. 阶段准入准出

| 阶段 | 准入条件 | 必要产出物 | 准出条件 |
| --- | --- | --- | --- |
| P0 | 已有主研究方案 | 冻结的研究阶段、证据角色与变更纪律 | 逻辑链不再混用校准、确证和 Blind |
| P1 | P0 完成 | 主张—证据—空缺表 | 最近工作边界可核验，不声称未证明的“首次” |
| P2 | P1 完成 | 构念规范、标注手册、指标规范和校准报告 | 核心标签可重复判定，分歧有可执行仲裁规则 |
| P3 | P2 规则可用 | 数据审计表、分组划分、Reranker 卡片和快照输入 | 数据集来历可追溯，开发/确证集无文档族或模板泄漏 |
| P4-00 | Python 3.11 与真实环境可用；不依赖 P2/P3 样本 | Eval 薄适配、精确 CI pin、绿色 run/report、clean `contract-lock.json` | 当前 LinkRag 候选契约与 LTR-v3 小样例可重放；旧 CI pin 不再是依据 |
| P4-01 | 现有候选缓存/契约可读；可与 P2/P3/P4-00 并行 | 候选字段缺口审计 | 快照 schema 的已有/缺失字段和责任来源可核验 |
| P4-02—P4-06 | P3 已提供最小样本，且 P4-00/P4-01 已完成 | 可重放快照、离线实验器和指标校准报告 | 同条件同候选池，无评价字段泄漏，重复运行一致 |
| P5 | P2—P4 完成 | 校准报告、功效分析、Gate A 预注册和封存样本 | 所有阈值、排除规则和样本量在 Gate A 运行前冻结 |
| P6 | Gate A 预注册已封存 | Gate A 正式研究报告 | 可依预注册无二义地判定 Go/Inconclusive/No-Go |
| P7 | Gate A = Go | 冻结的 D1—D3、A0、M1 和 Gate B 配置 | 方法未看 Blind 结果而完成冻结，且 `epsilon_M1` 未由方法差值反向选择 |
| P8 | Stress Blind v6 封存完好 | Gate B 正式研究报告 | 方法贡献成立或依预案收缩论文类型 |
| P9 | Gate B 结论已冻结 | 论文、完整性报告、评审与修订记录 | 已按独立发表规划完成目标稿件与正式投稿流程 |

## 5. 完成证据台账

| 任务 | 完成日期 | 产出物/证据 | 备注 |
| --- | --- | --- | --- |
| P0-01 | 2026-08-09 | [科研协议](robust-fusion-research.md) | 当前 v15 保持题目和 RQ1—RQ3，并记录 C1/C2/C3 的最终贡献层级与排除项 |
| P0-01A | 2026-08-09 | [科研协议第 0.3、4.3、11 节](robust-fusion-research.md) | 候选图已收缩为 Top-M 局部统计 |
| P0-01B | 2026-08-09 | 本研究推进清单 | 建立单一当前任务与准入准出制度 |
| P0-01C | 2026-08-28 | [科研协议](robust-fusion-research.md) | 前身 v8；全面重构信息架构，保留冻结决策并收束高成本扩展 |
| P0-01D | 2026-08-28 | [科研协议](robust-fusion-research.md)、[工程协议](robust-fusion-engineering.md) | 科研/工程职责分离；五份专题文档使用短文件名；当前版本为科研 v25、工程 v16 |
| P0-02 | 2026-08-09 | [科研协议第 5.2、9 节](robust-fusion-research.md) | 三分内部数据；校准、Gate A、Gate B 分离；样本量由功效分析冻结 |
| P1-01 | 2026-08-09 | [主张—证据—空缺表](robust-fusion-evidence.md) | 19 条核心主张及措辞护栏；其中 C18/C19 为 2026-08-28 新增近邻边界 |
| P1-02 | 2026-08-09 | [主张表第 4、8 节](robust-fusion-evidence.md) | 最相近工作的一手页面与实际方法边界已核验 |
| P1-03 | 2026-08-10 | [科研协议第 7.3—7.4、10.1、11 节](robust-fusion-research.md) | Gate A 前不复现近邻系统；D3/A0 进入最低包；GPU 训练另行决策 |
| P1-04 | 2026-08-10 | [科研协议第 2.4 节](robust-fusion-research.md) | 七步引言问题链、受限研究空缺和实验前措辞护栏 |
| P2-01A | 2026-08-10 | [科研协议第 4.1、6.3、8.3、9.3 节](robust-fusion-research.md) | 冻结待测 Chunk—唯一目标等价组参照的连续相似度为 H2 主检验；2×2 改为预注册分带复核；连续模型限于共同支持并显式记录重复测量；Gate A 仅绑定科学前提与代理效度 |
| P2-01B | 2026-08-28 | [科研协议 v18 第 4.2 节](robust-fusion-research.md)、[相似度 manifest](robust-fusion-similarity-manifest.md) | 冻结三层正交标签、候选对关系、两种 unknown 边界、qrel 不覆盖和相似度逐值重放字段；精确编码器与 Dev 参数仍待填 |
| P2-01C | 2026-08-28 | [相似度 manifest v3](robust-fusion-similarity-manifest.md)、真实 route preflight | BGE-M3 历史候选资格已由负责人在 Gate A 前撤销；真实 Learned Sparse 是 Ark/`doubao-embedding-vision-251215`，固定无标签在线探针按请求顺序重放一致。主相似度编码器和独立审计编码器均回到非 BGE 重新选择门禁 |
| P2-01D | 2026-08-28 | [相似度 manifest v5](robust-fusion-similarity-manifest.md)、`ROBUST-FUSION-SIMILARITY-ENCODER-QUALIFICATION-2026-08-28-v3` | 候选集合与标准先固定、研究数据不读取；`multilingual-e5-base@d1287505…` 和 multilingual DistilUSE `@bfe45d07…` 的权重/config/tokenizer、输入与正逆序向量重放通过，并复核与已冻结 Qwen/Jina Reranker 无制品复用。只关闭模型身份/确定性与家族选择，Dev 人工效度、分带和参照集合仍阻塞 Gate A |
| P3-05A | 2026-08-28 | [Reranker 资格脚本](../../scripts/qualify_robust_fusion_rerankers.py)、本地 `runs/robust_fusion/contracts/reranker-qualification-v1/manifest.json` | 预推荐 Qwen3 0.6B 生成式 reranker + Jina v2 multilingual 跨编码器；精确 revision/许可/权重/remote code 与固定无标签重放通过。透明记录缺 `einops`、Transformers 5.x 不兼容和 tokenizer regex 三次未合格尝试；最终固定隔离运行是 ST 5.7.0、Transformers 4.57.6、einops 0.8.1；该 v1 制品是负责人确认前的历史资格记录 |
| P3-05B | 2026-08-28 | `ROBUST-FUSION-RERANKER-QUALIFICATION-2026-08-28-v2`、本地 `runs/robust_fusion/contracts/reranker-qualification-v2/manifest.json` | 负责人在结果不可见时确认 Qwen/Jina 两家族；v2 记录固定 revision、非商业许可确认、独立学术采用 DOI、家族独立性与“采用不等于最优”边界。选择项已关闭，但资源/Dev 契约未完成，故 P3-05 仍不标完成 |
| P2-02 | 2026-08-28 | [标注手册 v1](robust-fusion-annotation-handbook.md) | 已形成四类原子冲突、false-negative、证据、双审仲裁、机器校验和 12 案例校准包规则 |
| P2-02A | 2026-08-28 | [确定性构建脚本](../../scripts/prepare_robust_fusion_p2_calibration.py)、本地 `data/robust_fusion/derived/p2_calibration_v1/manifest.json` | 从精确 T2/DRUID revision 生成盲化 12 案例包；四个输入 SHA-256 全量重算通过，连续两次构建输出逐文件 hash 一致；Gate A/B 授权字段均为 false |
| P2-02B | 2026-08-29 | [v2 冻结构建器](../../scripts/prepare_robust_fusion_p2_calibration_replay.py)、[人工交付生成器](../../scripts/materialize_robust_fusion_p2_human_delivery.py)、本地 `data/robust_fusion/derived/p2_calibration_v2/manifest.json` | 审计发现 v1 的 `quota_cell` 与类别过度对应，故 v1 与既有模型/工具试填均退出准入；v2 使用不复用 v1 的 12 案例并移除数据集、split、配额、来源/qrel/期望标签等管理员字段。正式空白 A/B 交付自检通过、答案键不存在、Gate A/B 授权均为 false |
| P2-03 | 2026-08-28 | [标注手册 v1 第 9.4 节](robust-fusion-annotation-handbook.md) | 在人工提交前冻结逐字段计数准入线、facilitator key 对照、关键构念零容忍项与失败重放规则；小样本 alpha/macro-F1 只作诊断 |
| P2-05 | 2026-08-29 | [标注手册 v2](robust-fusion-annotation-handbook.md)、`ROBUST-FUSION-P2-FACILITATOR-PATCH-REVIEW-2026-08-29-v2`、本地 `runs/robust_fusion/internal_v6_deepseek_pilot_v1/human_calibration_patch_v3/facilitator_review/` | v2 首轮失败与 v3 五例替换重放全部保留；最终合并 12/13/9/1 设计通过全部冻结准入线，格式与零容忍错误为 0。主持人预先知道 v3 key 的事实已披露，不声称主持人盲态；A/B 独立盲标和先锁后比成立。最终机器结论 SHA-256 为 `fe906b9e755135cfe4fe6607297aec5c5a0c2b2c0a0a5118e4c38ada9a01ef1c` |
| P3-00 | 2026-08-28 | [SQLite 与检索资产对账报告](../reports/sqlite_share_restore_and_asset_reconciliation_2026_08_28.md) | 真实评测资产可用；不等同于已具备确认性 Query/qrels 或完整统一索引 |
| P3-01 | 2026-08-28 | [Gate A 数据覆盖审计 v10](../reports/robust_fusion_gate_a_data_coverage_audit_2026_08_28.md) | 计划实体与替代数据均已固定 revision 落盘审计；cMedQA2 已正式替换 MedicalRetrieval 并冻结资格方向；DuRetrieval 三实体完整独立保留；C-MTEB Cmedqa 四类来源已逐 ID/hash 剥离，三数据集最终分母仍归 P3-02 |
| P3-01A | 2026-08-28 | [确定性来源与完整性审计脚本](../../scripts/audit_cmedqa_corpus_provenance.py)、本地 `data/robust_fusion/derived/cmedqa_provenance_peel_v2/manifest.json` | DuRetrieval 的 100,001 corpus/2,000 Query/9,839 qrel 全量零删减；Cmedqa 100,001 个 compact passage 全量四分类，2,536 条统一留在未解析审计类；3,999 Query 与 7,449 qrel 只生成一般上游 crosswalk，不建立 qrel 关联专项子集；制品只输出 ID/hash，不输出正文，也不把剥离子集当作正式 cMedQA2 corpus |
| P3-02A | 2026-08-28 | [资格清单生成器](../../scripts/prepare_robust_fusion_gate_a_eligibility.py)、本地 `data/robust_fusion/derived/gate_a_eligibility_v1/manifest.json` | 全量校验 T2/cMedQA2/DuRetrieval pinned 输入；生成 390,873 条 ID/family-hash 资格记录；冻结 Dev 暴露与 80 个跨 split family 排除，明确只是资格上界、不是最终 Gate 分母 |
| P4-00A | 2026-08-28 | Eval 薄适配、CI pin、候选/LTR 契约测试、`ROBUST-FUSION-ROUTE-CONTRACT-PREFLIGHT-2026-08-28-v1` | 本地非集成全测和真实栈已通过；`text-embedding-v4` Dense 与 Ark/豆包 Sparse 均以四条固定输入完成正逆序在线重放并只保存输入/向量摘要，不保存密钥或端点。clean 双仓与远端绿色 CI 尚缺，所以只记部分完成证据 |
| P4-00B | 2026-08-28 | `runs/robust_fusion/contracts/route-contract-preflight-v1-refresh-v19/failure.json` | 科研协议 v19 联动复放在 Dense `zh_short` 首项发现 float32 exact drift；无 manifest、无自动重试、Gate A 未运行。旧 v18 PASS 不能冒充 current-protocol 合格证据 |
| P4-00C | 2026-08-29 | `ROBUST-FUSION-DENSE-REPLAY-DIAGNOSTIC-2026-08-29-v1`、工程协议 v10、`ROBUST-FUSION-DENSE-REPLAY-POLICY-2026-08-29-v1` | 获授权的唯一一次诊断以两次请求复放四条固定文本，全部 4096 个 float32 分量 exact，自动重试为 0，未读取候选/qrel/排序/Gate 结果；manifest SHA-256 为 `3606a60aca87d41f959214c121b402a1c0ea303d228629cfac622d5648ec9081`。五项容差上界按结果前固定值正式封存；这关闭判定规则，但不替代尚未运行的正式 v2 三路 preflight |
| P4-00D | 2026-08-29 | `ROBUST-FUSION-ROUTE-CONTRACT-PREFLIGHT-2026-08-29-v2`、本地 `runs/robust_fusion/contracts/route-contract-preflight-v2/manifest.json` | 在冻结容差不变、零自动重试下执行一次正式三路 preflight；Dense 四探针和 Sparse 四探针均 exact，BM25=`sqlite_fts5`，BGE/Alt 继续排除。manifest SHA-256 为 `640e3d52a2f7cfc6f991cefe4d111ae18d09ba3260626a2e927988b5cd17a38a`；`gate_a_executed=false`、`outcome_data_read=false`。在线重放阻塞关闭，P4-00 仅余 clean/CI/lock 治理条件 |
| P4-00E | 2026-08-29 | 科研协议 v26、工程协议 v17、`ROBUST-FUSION-PROVIDER-ROUTE-SNAPSHOT-POLICY-2026-08-29-v2` | 负责人在 Gate A/Reranker/M1 均未运行时撤销在线 Dense 五项容差与 Sparse exact 重放 Gate。当前 Dense/Sparse 统一为一次生成、结构校验、哈希封存；跨运行数值差异只作描述，禁止据此重跑或择优。本地确定性环节仍须 exact。历史 v1/v2/诊断制品不覆盖，v5 无需重跑 |
| P0-03A | 2026-08-28 | [决策与变更记录](#6-决策与变更记录)、[Gate A 准入审计脚本](../../scripts/audit_robust_fusion_gate_a_readiness.py)、本地 `runs/robust_fusion/gate_a/readiness-preflight-v1.json` | outcome-blind 审计只读取协议、控制 manifest、checksum、Git 状态和制品存在性；当前 13 项高层检查中 6 项通过、7 项阻塞，明确保持 `NOT_READY_FOR_GATE_A` |
| P0-03B | 2026-08-29 | `ROBUST-FUSION-GATE-A-READINESS-PREFLIGHT-2026-08-29-v2`、本地 `runs/robust_fusion/gate_a/readiness-preflight-v2.json` | 审计已识别 Dense policy 为 `FROZEN_BEFORE_GATE_A`、诊断与正式 v2 manifest checksum 有效，三路 preflight 为 `PASS`。整体为 13 项中 7 项通过、6 项阻塞，`gate_a_unlocked=false`、`outcome_data_read=false` |
| P0-03C | 2026-08-29 | `ROBUST-FUSION-GATE-A-READINESS-PREFLIGHT-2026-08-29-v3`、本地 `runs/robust_fusion/gate_a/readiness-preflight-v3.json` | 将 P2 输入资格切换到无泄漏 v2 管理员包与正式空白人工交付，并机器拒绝模型/工具试填；P2 输入 PASS、人工结果仍 `BLOCKED_HUMAN`。整体仍为 13 项中 7 项通过、6 项阻塞，Gate/结果读取均为 false。为避免自引用，制品 SHA 只写项目状态页，不回写本审计所读取的推进清单 |
| P4-01 | 2026-08-28 | [候选快照字段缺口审计 v1](../reports/robust_fusion_candidate_snapshot_field_gap_audit_2026_08_28.md) | `candidate_hits/route_hits` 可直接复用；通用 StageOutput、Snapshot、历史 LTR cache 与 SQLite 均不能直接作为确认性快照；P4-02 的双视图最小字段、禁止字段、责任来源和物理隔离已冻结 |
| P3-04A | 2026-08-28 | [Internal Stress v6 数据协议](robust-fusion-internal-stress-v6.md)、[初始化脚本](../../scripts/initialize_robust_fusion_internal_v6.py)、本地 root manifest | 正式建立 v6 ID、三分目录、访问锁、摄取 schema 与来源资格；人口为空且 `NOT_ELIGIBLE`，所以是 P3-04 部分完成证据而非 Gate 解锁证据 |
| P3-04B | 2026-08-29 | [Internal Stress v7 数据协议](robust-fusion-internal-stress-v6.md)、[科研协议 v20](robust-fusion-research.md) | 在查看任何 30-family 结果前，将负责人已授权的 DeepSeek 合成路径正式限制为 v6-Dev 受控微型事实先导；保留 GateA/Blind 的独立自然来源锚点、非零自然候选配额、family 零重合和人工真值要求，不授权 Gate |
| P3-04C | 2026-08-29 | [Internal Stress v8 数据协议](robust-fusion-internal-stress-v6.md)、生成器与双审包生成器、本地 `runs/robust_fusion/internal_v6_deepseek_pilot_v2*` | 首批 30 次调用全部留痕，24/30 通过冻结结构门禁；四段恢复链只补拒绝 ID，43 次总调用后取得 30 个待人工复核提案。五段 manifest 与 A/B 盲审交付 manifest 全部校验通过；历史 v5 精确全文重合为 0。当前仍 `accepted_family_count=null`、`NOT_ELIGIBLE`，Gate A/B 未运行 |
| P3-04D | 2026-08-29 | [Internal Stress v9 数据协议](robust-fusion-internal-stress-v6.md)、[双审主持人脚本](../../scripts/review_robust_fusion_internal_v6_human.py)、[Dev 物化脚本](../../scripts/materialize_robust_fusion_internal_v6_adjudicated_dev.py)、本地 `facilitator_review/final_v1/` 与 `dev/releases/adjudicated_synthetic_v1/` | A/B 六份答案先锁后比；机械错误 0，候选级标签 90/90 一致、候选对 89/90 一致，唯一分歧完成条款级仲裁。人工接纳 28/30，2 个表面控制失败 family 被拒绝；接纳项已形成 28/112/112/28 四张 Dev 摄取表，最终仍为 Dev-only、`NOT_ELIGIBLE` |
| P3-04E | 2026-08-29 | [Internal Stress v10 数据协议](robust-fusion-internal-stress-v6.md)、[Dev 三路证据执行器](../../scripts/run_robust_fusion_internal_v6_route_evidence.py)、本地 `internal-v6-dev-route-evidence-v2-20260829/plan.json` | 固定 adjudicated release、隔离 eval collection/SQLite、同编码器写读、当前候选契约、方法/评价双视图和首次远端探测即消费唯一尝试；v1 零尝试计划已 supersede。v2 plan SHA-256 `4e1e279b12e23436421b4b6166b261451000cd0e86817ada5d77ccd0cea98144`，仍为 `PREPARED`/0 次执行，未调用外部 API、未写 Qdrant、未读取检索结果，且不是正式 P4-02 |
| P3-04F | 2026-08-29 | [Internal Stress v11 数据协议](robust-fusion-internal-stress-v6.md)、v2/v3 `run_state.json`、SSH tunnel healthz 与 collection existence 复核 | 负责人确认 v2 精确命令后，首次 Qdrant existence probe 发生 `ReadTimeout`；按预定规则封存为 `FAILED_NO_AUTORETRY`/1 次尝试。失败早于编码器构造，Dense/Sparse 请求为 0；经隧道复核 v2 collection 不存在。根因是 Qdrant 仅监听 `linkcv:127.0.0.1:6333` 而本地当时无转发；本地 36333 隧道恢复后 healthz=200，另备 v3 plan SHA-256 `14ee97c428b3a0ed460ff29cf2063e0cfd45c6d4969ebdac1d9d44feb5798818`，当前 `PREPARED`/0 次尝试，等待新确认 |
| P3-04G | 2026-08-29 | [Internal Stress v13 数据协议](robust-fusion-internal-stress-v6.md)、[v5 独立核验报告](../reports/internal_v6_dev_route_evidence_v5_verification_2026_08_29.md)、Dev 三路执行器与回归测试 | v3 因本地 storage 父目录缺失失败，v4 因 manifest 纳入瞬态 SQLite sidecar 而完整性拒收，均保持原状态；修复后独立 v5 一次执行完成。核验确认 28 Query/112 Chunk/3,056 候选、三路各 28/28 非空、112/112 已标注候选与 28/28 gold target 入并集，manifest/content root、SQLite/FTS5 和真实 Qdrant 112 点一致。v5 仍是 Dev-only、`NOT_ELIGIBLE`、`formal_p4_02_snapshot=false` |
| P2-05A | 2026-08-29 | [C2 三分边界最小补充方案](robust-fusion-c2-boundary-supplement.md)、[空白包初始化器](../../scripts/initialize_robust_fusion_c2_boundary_supplement.py)、本地 `dev/supplements/c2_boundary_calibration_v1/` | 根据既有 Dev 标签分布 1/1/7 与 Internal 28 个 detectable-only，冻结 numeric/version 两条三段匹配链及两个额外 conditional 案例，共 8 槽。manifest SHA-256 `ff4e00d857641a2d48e0ece509c29bf357f28918757dc4a1980f9906a681f347`；当前 0 正文、0 答案键、0 人工标签，Dev-only、`NOT_ELIGIBLE` |
| P0-02A | 2026-08-28 | [科研协议 v12](robust-fusion-research.md)、[工程协议 v4](robust-fusion-engineering.md) | 闭合重复 Gate、multiplicity、pooled estimand、Top1 剂量/风险集、正向单元、Track B、CI pin、数据集分母时间戳、术语和反伪影组合规则 |
| P1-05 | 2026-08-28 | [证据台账](robust-fusion-evidence.md)、[文献地图](robust-fusion-literature.md) | 纳入两项已核验 2026 近邻工作；新颖性改为 C1/C2 自立、C3 条件性 |

## 6. 决策与变更记录

| 日期 | 决策 | 依据 | 是否已观察结果 | 影响 |
| --- | --- | --- | --- | --- |
| 2026-08-09 | 保持原题目和 RQ1—RQ3，不另立图学习研究问题 | 图工程、全量边标注和额外模型训练对学生团队成本过高 | 否（方法尚未实施） | 方法收缩为 Top-M 局部统计 |
| 2026-08-09 | Gate A 是第一阶段正式科研决策，不是软件测试门槛 | 需要先区分构念校准、仪器校准和独立假设研究 | 否 | 主文档第 9 节已分离校准、Gate A 和 Gate B |
| 2026-08-09 | 内部母池分为 `Internal Stress v6-Dev / v6-GateA / v6-Blind`；最终 Blind 只用于 Gate B | 避免校准、现象判定和方法确认共用同一批题；研究负责人已确认三分结构 | 否 | 主文档第 5.2、9 节已落实三个独立角色 |
| 2026-08-09 | “≤100 Query”只作为校准先导起始预算；Gate A 由功效分析冻结样本量 | Gate A 是确认性研究，固定低成本上限不能代替统计功效 | 否 | 允许预注册的一次独立扩样；超过资源上限则记 `Inconclusive` 或收缩研究 |
| 2026-08-10 | Gate A 前不复现 HybRank/QuDAR；若后续需要显卡训练则单独决策 | 完整复现不回答 Gate A 的现象与代理门禁，且会提前引入额外 GPU、数据接口和调参成本 | 否 | 最低包保留 D3；仅 Gate A = `Go` 后评估一个完整近邻强基线 |
| 2026-08-27 | 发表路线已冻结，具体渠道与优先级转由[发表路径与投稿治理](robust-fusion-publication.md)维护 | 研究负责人明确调整目标渠道与优先级 | 否 | 本清单只保留论文形成与投稿任务，不重复维护路线细节 |
| 2026-08-28 | 真实 SQLite、BM25、Alt Embedding 和当前 eval Qdrant 只作为研究工程资产；不自动视为确认性研究样本 | 主 SQLite 没有 Query/qrels，各检索资产覆盖范围不同，历史 collection 还包含额外记录 | 是，仅观察资产结构与覆盖统计，未观察新论文实验结果 | P3/P4 可直接复用已有正文和部分检索产物；正式数据 revision、Query/qrels、三分样本和单一冻结索引口径仍须完成 |
| 2026-08-28 | 当时的总研究文档重构为 v8，但不改变已冻结题目、RQ1—RQ3 和方法开发门禁 | 原文重复较多，工程事实、研究设计和任务推进混在同一层级 | 否（未产生 Gate A/B 结果） | 为后续拆分科研协议和工程协议建立统一逻辑结构 |
| 2026-08-28 | 将总协议拆为科研协议 v9 和工程协议 v1，并将五份专题文档改为 `robust-fusion-*` 短文件名 | 文件名前缀过长，且科学定义与环境/实现事实需要独立维护 | 否（未产生 Gate A/B 结果） | 科研协议维护 RQ、构念、设计和 Gate；工程协议维护环境、资产、快照、实验器和验收；任务证据仍统一进入本清单 |
| 2026-08-28 | 接受第二轮审稿中关于停止规则、multiplicity、正向单元、Track B 后果、CI pin、外部时间戳和术语定义的批评 | 这些问题不改变核心 RQ，但会决定 Gate 能否无二义执行并防止跨周期选择性报告 | 否（尚未运行 Gate A） | 科研协议最终收口为 v12、工程协议为 v3；P4-00 改成独立 preflight，P5-07/P5-08 形成无环 Seal 顺序，新增 P8-06，并冻结确证性 pooled 权重与 Top1 最坏剂量终点 |
| 2026-08-28 | 将 C1 定为主要科学贡献、C2 定为诊断贡献、C3 定为条件性方法贡献；放弃长合取式新颖性论证 | 新近工作已独立观察相似度与证据有效性分离；真正未被替代的是等价—冲突受控交互和可识别性分区 | 否（仅核验外部论文元数据与摘要） | 题目和 RQ 不变；即使 M1 失败，C1/C2 仍可按门禁独立判定 |
| 2026-08-28 | 将单一四值 Query—Chunk 关系改为来源相关性、目标事实关系、方法可裁决性三个正交字段，候选对关系独立标注 | 数据覆盖审计显示原字段会把普通错误混入 factual-conflict，并混淆真值未知与方法不可识别 | 否（Gate A/B 未运行；未查看确认性结果） | 科研协议升为 v13，生成标注手册 v1；不改变 RQ、Gate estimand、比较家族或门槛 |
| 2026-08-28 | P3 数据摄取与 P2 手册并行，但先穷尽公开和既有资产，只有语义缺口确证后才请求人工标注 | 研究负责人确认继续推进；公开标签与既有资产可显著缩小送审范围 | 否（仅审计数据/资产覆盖） | T2、Medical 与 DRUID 计划实体已全部落盘并审计；人工包维持最小化，不重标全 corpus |
| 2026-08-28 | 历史 T2 子池只用于曝光恢复和工程追溯，正式 T2 候选必须回到原始 230 万 corpus | SQLite `993101/993103` 都是由已揭盲 Query 条件化构造的 10k 子池，不能代表原始负例分布 | 是，仅观察历史资产结构与官方 qrels，不是 Gate A/B 结果 | 生成 800 个 v4 精确 QID、502 个 v5 保守 QID 和 1,302 项并集排除制品；后续用整个 Dev 排除规则覆盖未恢复的 11 项残余风险 |
| 2026-08-28 | BGE-M3 曾通过官方制品资格审计，但主相似度编码器保持未冻结（历史决定，已由后续淘汰决定覆盖） | 当时可复核模型 revision、许可和部分文件摘要；旧 sidecar 始终缺完整指纹 | 否；只核验外部制品和接口定义，未查看 Gate A/B 结果 | 从未授权 Gate A；后续不再据此继续实现或复用 20,772 条旧向量 |
| 2026-08-28 | 12 案例桌面校准包只从 pinned T2/DRUID 生成，Medical 与历史 Blind 不进入 | Medical 许可尚未闭合；Blind v4/v5 已曝光；T2/DRUID 足以覆盖本轮手册边界案例 | 否；仅生成校准输入和 facilitator 预期，没有人工校准结果或 Gate 结果 | 双人结果锁定前隐藏 origin/qrel/stance/变换和 facilitator key；该包永不并入 Gate A/B |
| 2026-08-28 | P2 桌面校准采用逐条计数准入线，并新增独立案例资格表 | 13 条候选上的 alpha 容易受小样本和类别分布影响；原空白表又无法记录手册要求的目标参照有效性与目标组唯一性 | 否；准入线和字段均在人工提交前冻结 | 两人须先完成 12 条案例资格，再标候选/候选对；关键构念错误不能被总准确率抵消，失败须仲裁并重放受影响字段 |
| 2026-08-28 | T2 残余曝光改用 split-level 保守关闭，不猜测丢失的 11 个 source record | 存活历史脚本/制品均来自 C-MTEB T2，而它恰好是原始 Dev 正例投影；原始 Train 258,042 个 QID 与 Dev 交集为 0 | 否；只审计来源、split 与 qrels，Gate A/B 未运行 | Dev 整体 calibration/exposed-only；GateA/Blind 候选只从 Train 按 family 再分；Seal 后才发现 Train 曝光则 cohort 失效 |
| 2026-08-28 | 不把 SQLite `990126/990127` 正文或 C-MTEB Cmedqa 混合 corpus 当作权威研究文本 | 两个 SQLite 集各 800 个 ID 全部对上官方实体，但正文完全一致数均为 0 且可见乱码；C-MTEB Cmedqa 100,001 个 passage 中 90,328 个与 DuRetrieval 完全一致（后续剥离确认其中 2,086 个也与上游 cMedQA2 answer 一致） | 否；只进行实体与字段对账 | 历史资产仅复用 ID/provenance/索引覆盖；正式文本回到 pinned 上游文件；不修改 SQLite |
| 2026-08-28 | 将上游 cMedQA2 作为 MedicalRetrieval 的优先替代候选，但在用户确认前不冻结分母 | 上游有完整问题/回答/candidate 标签和可存档许可，保留医疗域角色；但只允许 non-commercial research 且仓库为 GPL-3.0 | 否；只进行公开数据审计，未运行 Gate | 待研究负责人接受“本地研究、不重分发全文”边界后再版本化科研协议；拒绝时转审 DuRetrieval |
| 2026-08-28 | 确认项目属于非商业科研，以固定上游 cMedQA2 正式替换 MedicalRetrieval | 研究负责人明确接受非商业本地使用与不重分发全文的保守治理；上游实体保留医疗术语/条件密集角色，且有完整问题、回答和 candidate 标签 | 否；Gate A/B 均未运行，未观察 cMedQA2 排序结果；只审计 split、文本 family 与正例 ID | 科研协议升为 v15、工程协议升为 v6；Dev 全部 exposed-only，Train/Test 分别作为 Gate A/Gate B 资格母池，80 个跨 split Query family 全排除；最终分母仍须先导与功效封存 |
| 2026-08-28 | 将 DuRetrieval 明确为独立数据集，并对 C-MTEB Cmedqa compact corpus 做四类精确来源剥离 | 逐条正文 hash 显示 88,242 条 Du-only、7,137 条 cMedQA2-only、2,086 条 both、2,536 条 unresolved；原 90,328 条总重合不能表达共同文本与未解析边界 | 否；只看公开实体来源映射，未运行排序 | 来源剥离只作 provenance/exposure crosswalk；`both` 不强制单归因，`unresolved` 不自动判负；正式主数据使用 pinned 上游 cMedQA2，医学域只作分层属性 |
| 2026-08-28 | 分享包固定为研究假设与工程可行性的正式起点，并建立 Internal Stress v6 正式空骨架 | 分享包与旧 eval MySQL/检索资产真实对账，足以证明历史工程链路和预算基础；但两端 query/qrel 都为 0，历史 Blind 已曝光 | 是，仅观察资产结构/计数与公开来源映射；没有 Gate A/B 结果 | 科研协议升为 v16、工程协议 v7、进度 v15；建立 v6 ID、目录、访问锁和摄取模板，但保持 `NOT_ELIGIBLE`，不能把空骨架或历史聚合结果写成确认性数据 |
| 2026-08-28 | 完整、独立保留 pinned C-MTEB DuRetrieval；2,536 条 Cmedqa 未解析记录不再细分或处理 | 研究负责人明确要求不对其中的 qrel 关联项作专项标记，优先保证 DuRetrieval 作为独立数据集的完整性 | 否；Gate A/B 均未运行，只复核固定文件摘要、schema 与实体计数 | 科研协议升为 v17、工程协议 v8、进度 v16、数据审计 v8；DuRetrieval 100,001/2,000/9,839 零删减并固定为辅助稳健性数据，当前六单元 Gate 不变；Cmedqa 的 2,536 条全部统一为仅审计类，不回配、不专项标注、不删除、不作正式语义输入 |
| 2026-08-28 | 淘汰 BGE-M3，按真实环境冻结 Learned Sparse 为 Ark/`doubao-embedding-vision-251215`；医学只作数据分层属性 | 负责人指出 BGE 已退出；`.env.eval` 与 live API 契约均确认豆包 sparse，历史代码注释/示例已过时；研究问题关注相似干扰而非医学 | 否；Gate A/B 均未运行，只核对配置、代码和固定无标签 API 探针 | 科研协议升为 v18、工程协议 v9、相似度 manifest v3、进度 v17；BGE 不得进入 route/相似度/审计，新的 dense 相似度编码器须无结果重选；cMedQA2 仍是主数据但不设医学专门终点 |
| 2026-08-28 | 预选两个非 BGE 相似度编码器，但不据此授权 Gate A | 候选和标准先固定；两个本地公开制品有中英文覆盖、精确 revision/许可/权重摘要，且架构不同、成本可控 | 否；只运行固定合成文本的模型身份、数值和正逆序重放检查，`outcome_data_read=false` | 相似度 manifest 升为 v4、进度 v18；主 E5 与审计 DistilUSE 进入 Dev 资格阶段，仍须 Reranker 家族独立性、长短文本分层人工效度、共同支持和分带冻结 |
| 2026-08-28 | 冻结 Qwen3-Reranker-0.6B 与 Jina v2 multilingual 为 Gate A 两个独立 Reranker 家族 | Qwen 是项目真实测评模型；Jina 是独立生产者的传统跨编码器，固定公开制品可本地复现，并被 FEVER 2025 多 Reranker 研究采用（DOI `10.18653/v1/2025.fever-1.2`） | 否；Gate A/B 与 Dev 排序效果均未读取，只重放固定合成探针并核对许可、权重和学术采用 | 相似度 manifest 升为 v5、进度 v19、Reranker 资格制品升为 v2；选择后不得按 Dev 效果换家族，P3-05 仍待资源和 Dev 长度/重放契约 |
| 2026-08-28 | 协议 v19 路线刷新因在线 Dense exact replay 漂移而失败，不自动重试或静默放宽 | provider-managed 在线权重/数值可能不保证跨请求 float32 逐值相等；既有脚本把任何 bit-level 差异视为失败 | 否；只运行四条固定无标签输入，未读取候选、qrel、排序或 Gate 结果 | current-protocol route preflight 转为阻塞；保留旧 v18 PASS 作历史证据和 v19 失败记录，等待预先决定 exact 或容差判定后才可再次调用 API |
| 2026-08-29 | 冻结 provider-managed Dense 的 `exact OR 五项数值容差交集`，但不重写先前未测量异常 | 负责人确认若仅为尾数误差则应在实验前冻结合理容差；为避免看结果定阈值，诊断脚本在调用前写死 `1e-6` 最大分量差、`1e-5` relative/normalized L2、`1e-8` cosine distance 和 `1e-5` 单候选分数扰动上界 | 否；唯一获授权诊断只使用四条固定无敏感文本，两次请求、零自动重试；本次实测全部 float32 exact，未读取任何候选、qrel、排序或 Gate 结果 | 工程协议升为 v10、进度升为 v20；冻结策略允许 exact 或逐探针五项全过，任一超界即失败。历史 mismatch 仍记为幅度未知；正式 v2 三路 preflight、clean/CI/lock 仍未完成 |
| 2026-08-29 | 在冻结 Dense 容差不变后执行一次正式 v2 三路 preflight | 诊断已关闭判定规则，负责人明确要求继续推进；正式 preflight 需要同时确认当前 Dense、Ark/豆包 Sparse、SQLite FTS5 和 BGE 排除 | 否；只使用四条固定无敏感文本，零自动重试，未读取候选、qrel、排序或 Gate 结果 | 正式 v2 manifest 一次通过，Dense/Sparse 全部 exact；在线重放阻塞关闭。P4-00 仍须 clean 双仓、远端绿色 CI 和 `contract-lock.json`，不据此解锁 Gate A |
| 2026-08-29 | P2 正式人工入口从泄漏 `quota_cell` 的 v1 切换到无类别提示的 v2，并排除所有模型/工具试填 | v1 的配额字段与目标类别直接对应；现有已填写 A/B 文件又来自工具会话，不能代表团队人工独立判断 | 是，仅观察 P2 开发校准试填及其机械审查；未观察 Gate A/B 或正式人工结果 | v1 与旧试填只作开发记录；新建 `runs/robust_fusion/p2_human_calibration_v2/` 空白双人交付，每人仍只需 12+13+1 条。只有两名真实标注员提交、锁定、仲裁和机器 PASS 才能关闭 P2-05 |
| 2026-08-29 | P2-05 按 v2 保留 7 例 + v3 替换 5 例的合并设计判为通过，标注手册升级为 v2 | 首轮制品缺陷没有通过事后改 key 修补；五例替换重放零分歧，合并设计的全部冻结计数门槛和零容忍项通过，唯一旧算术分歧有发包前规则依据 | 是，已观察 P2 人工校准结果；未观察 30-family、Gate A/B、Reranker 或方法结果 | 允许进入 v6-Dev 30-family 构造率先导；不授权 Gate A/B。主持人预知 v3 key 的事实、A/B 独立性范围和全部原始提交均保留 |
| 2026-08-29 | DeepSeek 生成路径正式限定为 Internal v6-Dev 受控合成微型事实先导 | 研究负责人已明确授权使用项目配置的 DeepSeek、人工审核和 completion-first 预算；此前权威文档仍写“必须真实 Query”，与已确认方案冲突 | 已观察 P2 校准是否通过；尚未生成或查看 30-family 与任何 Gate 结果 | 科研协议升为 v20、Internal 协议升为 v7；LLM Query 永远标 synthetic，30-family 只估计合成构造率。GateA/Blind 仍要求独立自然来源锚点、非零自然候选配额、family 零重合和双审仲裁，不改变 Gate estimand 或阈值 |
| 2026-08-29 | 执行 30-family Dev 生成并建立不可覆盖恢复链与双人盲审包 | v20 已在结果前授权；首批默认思考模式造成 6 条正文截断，严格门禁又拒绝不逐字/非原子提案，需在不放宽构念的前提下只补失败 ID | 是，仅观察 Dev 生成、token/费用、结构门禁与精确全文重合；尚未观察人工标注、检索/Reranker、Gate A/B 或方法结果 | 科研协议升为 v21、工程协议 v12、Internal 协议 v8、进度 v23；固定首批结构产率 24/30，总调用 43，恢复后 30 个仅为待审提案。A/B 提交、仲裁、人工接纳率、自然来源人口与 Gate 均保持未完成 |
| 2026-08-29 | 完成 Internal v6-Dev 30-family 双审锁定与主持人裁定 | 模型构造角色不是真值；只有先锁后比、条款级仲裁与接纳台账完成后才能估计人工构造率 | 是，已查看 Dev 人工标签与构造角色偏差；未运行检索/Reranker、Gate A/B 或方法结果 | 科研协议升为 v22、工程协议 v13、Internal 协议 v9、进度 v24；固定人工接纳 28/30，拒绝两个控制失败 family。28 个主冲突全为 detectable-only，C2 三分边界仍未覆盖，GateA/Blind 保持空与锁定 |
| 2026-08-29 | 将 Internal v6-Dev 三路证据改为两阶段一次性执行，并另建 C2 三分边界最小补充 | 28 个接纳 family 已可进入真实 Dev 重算，但外部调用必须在执行前锁定输入、配置、成本和失败边界；既有 C2 校准分布 1/1/7 且 Internal 主冲突全为 detectable-only，需要单独补齐 method-view 可识别性边界 | 是，只查看既有 Dev 标签分布和本地契约测试；真实三路检索、C2 新正文/标签、Gate A/B 与方法结果均未查看 | 科研协议升为 v23、工程协议 v14、Internal 协议 v10、进度 v25、全量标注指南 v6；三路 v2 计划保持 `PREPARED`/0 次尝试，C2 8 槽包保持 `PLANNED_EMPTY`。二者只属于 Dev，不改变 Gate 估计量、阈值、人口或正式 P4-02 状态 |
| 2026-08-29 | v2 三路 transport 失败后不重跑原计划，恢复 SSH 隧道并另备 v3 | 一次性规则要求任何首次远端探测失败都消费计划；只读诊断显示 Qdrant 仅在 `linkcv` 本机 6333 监听，而执行时本地无隧道 | 是，只观察 Qdrant transport failure、healthz 和目标 collection 不存在；未发出 Dense/Sparse 请求，未观察候选、Reranker、Gate A/B 或方法结果 | 科研协议升为 v24、工程协议 v15、Internal 协议 v11、进度 v26；v2 永久保持 `FAILED_NO_AUTORETRY`，不改写为未执行。健康隧道下的新 v3 仍须精确命令再确认，Gate 和正式 P4 状态不变 |
| 2026-08-29 | 保留 v3 运行失败与 v4 完整性拒收，以独立 v5 完成 v6-Dev 三路证据 | v3 暴露本地 storage 父目录前置缺陷；v4 暴露 SQLite `-wal/-shm` 不应进入封存清单。一次性治理要求旧制品不覆盖、不重签，只能修复执行器后使用新 run ID | 是，已查看 Dev 三路候选、分数/排名、标签覆盖及 v4/v5 数值差异；未运行 Reranker、Gate A/B 或 M1 | 科研协议升为 v25、工程协议 v16、Internal 协议 v12、进度 v27、全量标注指南 v8；v5 固定为 `VERIFIED/NOT_ELIGIBLE`。只关闭 Dev route-evidence 缺口，不改变 Gate estimand、阈值、确认性人口或正式 P4-02 状态 |
| 2026-08-29 | 不再为 provider-managed Dense/Sparse 设置数值误差或 exact 重放标准 | 在线服务的浮点差异不改变同一封存候选快照内的方法比较；设定任意尾差门槛不能增加论文构念效度，反而可能诱发因数值差异重跑或择优 | 是，已观察 v6-Dev v4/v5 的在线数值差异、候选集合和排名稳定性；未运行 Reranker、Gate A/B 或 M1 | 科研协议升为 v26、工程协议 v17、Internal 协议 v13、进度 v28；在线路由单次生成、结构校验、哈希封存，数值差异仅描述。旧容差历史保持原样，本地确定性计算仍 exact；不改变 Gate estimand、效应阈值、人口或 v5 接纳结论 |

## 7. 阻塞项

- 当前研究任务 P2-01 的构念边界、两个非 BGE 编码器的身份/确定性资格和两个 Reranker 家族选择均已关闭；仍须在 v6-Dev 完成长短文本分层的独立编码器—盲人工效度，以及数据源内统计、共同支持和分带。这些项目均不得由 Gate A 结果反推。真实 Learned Sparse route 已确认是 Ark/豆包在线 API，它不是相似度编码器的替代品。
- P3-05 已冻结 `Qwen3-Reranker-0.6B + jina-reranker-v2-base-multilingual`，不再开放备选模型比较。剩余阻塞是 P2-06 的 GPU/批量/精度预算，以及 Dev 的 1024-token 覆盖与逐值重放；Dev 只能检查可运行性和契约，不能按效果换家族。
- P3-02 的当前六单元数据集选择已关闭：T2 使用 Dev-exposed/Train-resplit，cMedQA2 使用 Dev-exposed/Train-GateA/Test-GateB 资格方向且医学只作分层属性，Internal v6 已得到 28/30 的合成 Dev 人工接纳率、完成 Dev 摄取物化，并由 v5 形成经核验的真实三路证据。DuRetrieval 以 100,001/2,000/9,839 的完整 pinned 实体独立保留，只作预先声明的辅助稳健性数据，不提供备用 Gate 路径。ID/hash-only split/exclusion 资格 manifest 已生成；当前缺口已收缩为 document/version/template family 扩展排除、自然来源构造率、功效预估与 T2/cMedQA2/Internal v6 最终分母封存。
- P2-05 已关闭，标注手册 v2 已冻结。P3-04 的数据 ID、三分目录、访问锁、摄取 schema、来源资格和 30-family Dev 双审仲裁已经建立；接纳的 28 个合成 family 只允许用于 Dev。C2 的 8 槽补充目前只是空白管理员包，尚未生成或发放。GateA/Blind 的独立自然来源锚点人口仍未建立，不能由 Dev 合成样本替代。
- P4-00 的在线路由模型/schema/结构证据和“无数值 Gate、单次封存”治理规则已经关闭；正式候选快照仍受双仓非 clean、缺本轮远端绿色 CI run ID 与正式 `contract-lock.json` 的治理阻塞。该阻塞不妨碍 P2/P3 数据准备，但必须在 P5-07 前解除。
