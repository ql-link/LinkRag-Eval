# Gate A 事实关系与冲突标注手册

> 记录：`ROBUST-FUSION-ANNOTATION-HANDBOOK-2026-08-28-v1`
> 对应科研协议：`ROBUST-FUSION-RESEARCH-2026-08-28-v19`
> 状态：P2-02 工作草案；无类别提示的 12 案例 v2 盲化桌面校准包及正式人工交付副本已生成，须完成双人独立人工标注、仲裁与重放后才能冻结为正式标注版本。
> 结果边界：本手册形成时 Gate A/B 均未运行；不得用确认性排序结果反向修改标签。

## 1. 目的与适用范围

本手册用于标注本研究中的：

- Query—Chunk 来源相关性；
- 候选与唯一目标等价组的事实关系；
- 四类原子事实冲突；
- method view 下的可检测/可裁决边界；
- Top-M 候选对冲突代理的人工审计真值。

它不用于评价网页作者或机构权威性，不评价生成答案质量，也不把 Dense、Learned Sparse、BM25 的分数当成人工真值。

同一套关系与证据规则适用于全部数据集。cMedQA2 的医学域只作为预先记录的分层属性，不增加“医学正确性”标签、专门终点或额外 Gate；专业事实缺少可核验证据时与其他领域一样进入 `unresolved`。

> **概念解释｜正交标签**：正交表示把不同问题分开记录。本研究分别回答“候选是否满足 Query”“它与目标事实是什么关系”“方法能否从推理期信息判断”，避免一个标签同时承担三种含义。

## 2. 标注单位、角色与视图

### 2.1 两种标注单位

1. 候选级：`Query × target_equivalence_group_id × candidate_chunk_id`；
2. 候选对级：`Query × candidate_i × candidate_j`，只用于代理效度审计。

每个确认性候选必须且只能锚定一个 `target_equivalence_group_id`。无法唯一锚定的候选记为 unresolved，不得由标注员自行挑选“最像”的目标组。

### 2.2 标注角色

| 角色 | 可做事项 | 不可做事项 |
| --- | --- | --- |
| 标注员 A/B | 独立阅读 Query、候选、目标参照和允许证据；提交标签、证据定位与理由 | 查看另一人的标签、Reranker/LTR 输出、方法名或确认性排名结果 |
| 仲裁员 | 只处理分歧与低置信案例；记录采用哪条规则 | 为追求类别均衡而改标签 |
| 数据管理员 | 导入原始 qrel、版本、hash 和盲化包；运行格式校验 | 用自动预标注覆盖人工结论 |

### 2.3 两个视图

- `method_view`：Query/Chunk 正文、生产可见文档元数据、三路分数/排名/命中和冻结的确定性特征；
- `evaluation_view`：原始 qrel、Gold/等价/冲突真值、目标组、证据定位、变换记录和人工标签。

标注可以读取 evaluation view；任何排序方法只能读取 method view。标注界面不得显示 Reranker、LTR-v3、M1、分路分数、当前排名或候选构造来源。

## 3. 必填字段与合法值

### 3.1 来源字段

| 字段 | 要求 |
| --- | --- |
| `dataset_id` / `dataset_revision` | 固定数据实体与精确 revision |
| `query_id` / `candidate_chunk_id` | 保留官方 ID；本地 ID 另存，不覆盖官方 ID |
| `source_qrel` | 原始值或 `unjudged`，永不覆盖 |
| `target_equivalence_group_id` | 唯一目标组；不能判定时为空并转 unresolved |
| `candidate_origin` | `natural` / `synthetic`；标注界面盲化，管理层保留 |
| `content_hash` | 规范化前原始内容的 SHA-256 |

### 3.2 人工判断字段

案例资格先单独记录，不把目标参照缺陷挤进候选关系标签：

```text
target_reference_status:
  valid
  invalid
  unresolved

target_group_status:
  unique
  non_unique
  unresolved
```

任一字段不是 `valid + unique` 时，停止该案例的候选级和候选对级标注；不得用 `target_relation=unresolved` 掩盖目标参照本身的缺陷。

```text
relevance_status:
  relevant_gold
  relevant_equivalent
  verified_incorrect_distractor
  unresolved_possible_false_negative

target_relation:
  equivalent
  factual_conflict
  other_incorrect
  unresolved

conflict_type:
  not_applicable
  version_or_time
  numeric
  negation_or_direction
  applicability_or_condition
  unresolved

adjudicability:
  not_applicable
  detectable_only
  conditionally_adjudicable
  unidentifiable

candidate_pair_relation:
  not_annotated
  same_fact
  factual_conflict
  insufficient_context
  unresolved
```

每条人工判断还必须填写：

- `evidence_locator`；
- `rationale`；
- `reviewer_id`；
- `confidence`：`high / medium / low`；
- `adjudication_status`：`single / agreed / disputed / adjudicated / unresolved`；
- `handbook_version`。

`confidence` 不是关系标签。低置信不能自动变成错误，High 也不能替代证据定位。

## 4. 候选级标注流程

标注员必须按下列顺序作答，不能先看“冲突类型”再倒推相关性。

### 步骤 1：确认 Query 与目标组

1. 写出 Query 的核心实体、待回答事实槽、时间/版本、方向和适用条件；
2. 核对给定目标参照是否真正满足 Query；
3. 核对所有目标组成员能否互相替代且不改变答案；
4. 目标参照自身存在错误、过时或多义时，停止该案例并标记 `target_reference_invalid`，不继续标候选。

### 步骤 2：标 `relevance_status`

| 标签 | 纳入条件 | 排除条件 |
| --- | --- | --- |
| `relevant_gold` | 是原始目标证据，且其正确性与适用范围已经满足本研究复核要求 | 仅因官方 qrel 为正、但无法确认是否回答目标事实 |
| `relevant_equivalent` | 对同一事实槽给出相同/相容答案，在 Query 条件下可替代 Gold | 只主题相关、只补充背景、依赖缺失上下文 |
| `verified_incorrect_distractor` | 有可定位证据确认其不满足 Query | 只是 qrels 未列出、相似度高或模型排名低 |
| `unresolved_possible_false_negative` | 无法排除实际相关、证据冲突、语境不足或漏标 | 已有充分证据确认正确或错误 |

### 步骤 3：标 `target_relation`

1. `equivalent`：候选与目标组在实体、事实槽、时间和条件上相同或相容；
2. `factual_conflict`：候选对同一可比事实给出不相容结论；
3. `other_incorrect`：候选确实错误，但不是同事实冲突；
4. `unresolved`：证据不足，不能稳定落入前三类。

以下均属于 `other_incorrect`，不属于事实冲突：

- 只讨论同一主题但没有回答事实槽；
- 实体、对象或事件不同；
- 只有背景信息，缺少答案；
- 语义不完整或文本损坏；
- 纯关键词重合、模板重合或同文档近重复。

### 步骤 4：仅为事实冲突标 `conflict_type`

#### `version_or_time`

同一实体/事实槽在可比时间口径下，候选使用错误版本、年份、生效期、截至日期或把历史状态写成当前状态。若 Query 明确询问历史值，历史材料不能因“不是最新”而判错。

#### `numeric`

同一量、单位、统计口径与适用范围下，候选给出错误数字、范围、比例、序号或量级。单位换算后相等属于 equivalent；统计口径不同且无法对齐属于 `unresolved` 或 `other_incorrect`，不强判数字冲突。

#### `negation_or_direction`

候选把允许/禁止、增加/减少、支持/反对、存在/不存在、真/假等方向反转。只缺少否定词但整体语义未反转，不据表面 token 判冲突。

#### `applicability_or_condition`

候选省略、替换或违反决定答案成立范围的前提，如人群、地区、产品型号、疾病阶段、法律辖区或触发条件。无关修饰语的缺失不算条件冲突。

#### 原子性规则

- 合成候选一次只允许一个主事实单元变化；
- 自然候选若多类冲突不可拆分，标注主类必须有明确决定性依据，否则转探索性多标签池；
- 纠正标点、语序或无关背景后答案仍相同，不是冲突；
- 相似度、检索路和排序结果不能参与冲突判定。

### 步骤 5：标 `adjudicability`

仅当 `target_relation=factual_conflict`：

1. `conditionally_adjudicable`：method view 中存在冻结规则可使用的显式约束，能在不读取 qrels/Gold 身份的情况下选择正确成员；
2. `detectable_only`：能从候选间同槽不一致判断“有冲突”，但 Query 未给正确值或允许信息不足以选择哪方正确；
3. `unidentifiable`：评价侧通过外部证据知道真值，但 method view 看不到决定性版本、来源上下文或事实差异，连稳定识别/处置该冲突都不可能；
4. 其他 `target_relation` 固定 `not_applicable`。

不能因为人类拥有常识就标 `conditionally_adjudicable`。必须指出 method view 中哪一个字段或文本片段使正确侧可被规则化选择。

## 5. 候选对标注流程

候选对顺序先按确定性 ID 排序，界面不显示哪个候选排名更高。

| 标签 | 判定规则 |
| --- | --- |
| `same_fact` | 同一事实槽、实体、时间和条件下陈述相同或相容；包括两条候选重复同一个错误值 |
| `factual_conflict` | 同一可比事实下陈述互斥；不要求标注哪一方正确 |
| `insufficient_context` | 可以明确指出缺失了哪一项实体/时间/条件/指代，导致无法进行同事实比较 |
| `unresolved` | 已按规则查证和仲裁，仍无法稳定决定前三类 |

`insufficient_context` 描述的是“缺什么已经明确”；`unresolved` 描述的是“完成规定核验后仍无法分类”。

## 6. False negative 与 unknown 处理

> **概念解释｜False negative 审计**：未被公开 qrels 标为相关的候选可能实际能回答 Query。审计的目标是避免把漏标正确证据误当困难负例。

出现以下任一情况，优先使用 `unresolved_possible_false_negative + target_relation=unresolved`：

- qrels 未判断，候选看起来可能完整回答 Query；
- 两份可信证据互相矛盾且不能确定适用时间/范围；
- 候选需要上文、表格标题、图注或外部指代才能解释；
- 任何专业领域或强时效事实缺少合格证据；
- 目标参照本身疑似错误或过时。

unresolved 不进入 C1/C2 确认性主分析，不得为凑足每 Query 的 20 个冲突候选而强制裁决。其数量、相似度分布和原因必须单独报告。

## 7. 各公开数据的初始映射边界

### 7.1 T2Ranking

- 原始 grade 2/3 只提供 relevant 起点；仍须确认是否属于目标等价组；
- 原始 grade 0/1 是已判断不满足检索需求的起点，可筛选 `other_incorrect`，但不能自动变成 `factual_conflict`；
- qrels 外 passage 是 unjudged；
- `qrels.retrieval.dev.tsv` 只作正例索引，不覆盖四级 qrel。

### 7.2 cMedQA2

- Train triplet 和 Dev/Test `0/1` 只提供 answer-selection 正负标签；`label=0` 不自动等于 `factual_conflict`；
- 数据集用于提供条件、数字、否定等约束密集样本；医学域不是研究终点，标签和 Gate 规则与 T2/Internal v6 完全相同；
- 上游 Dev 整体 calibration/exposed-only，任何跨 split 的规范化问题文本 family 都不得进入 Gate A/B；
- Train/Test 分别只是 Gate A/Gate B 资格母池，最终案例仍须按 Query、回答/文档、版本和反事实模板 family 隔离；
- 涉及诊断、治疗、药物、剂量或时效的正确性必须有合格证据定位；
- 原始全文只在本地非商业研究环境使用；版本化或公开的标注/复现制品不得复制整段问题或回答正文，本地受控盲化标注包可按最小必要范围呈现正文。

### 7.3 MedicalRetrieval / Multi-CPR

- 因固定上游仓库与 C-MTEB card 均无明确数据许可，已被 cMedQA2 替换；
- 只保留许可审计和历史方案追溯，不制作本研究确认性标注包；
- 将来即使许可得到澄清，也不得在查看 Gate A 结果后替换当前数据集分母。

### 7.4 DRUID

- `chunk_stances` 是相对 claim 的 stance，不等于与本研究目标组的关系；
- `is_helpful_chunk` 不等于正确；
- `is_gold_chunk` 表示原事实核查来源身份，不自动映射为 `relevant_gold`；
- 只用于英文 RQ1/RQ2 复现和代理效度，不进入 C1 六单元或 Gate B。

## 8. 证据要求

`evidence_locator` 必须指向可复查的位置，优先级为：

1. 数据集内同一官方 record 的明确文本位置；
2. 数据集官方标注说明、正式 qrel 或原始出处；
3. 稳定的一手权威材料及其版本/日期；
4. 两名标注员均认可的限定性辅助来源。

仅写“常识”“模型判断”“搜索结果第一条”或“和 Gold 不同”不合格。证据只进入 evaluation view；涉及论文时记录 DOI，不把论文下载链接写入标注包。

## 9. 质量控制与仲裁

### 9.1 独立性

- 12 个桌面案例全部双人独立标注；
- P3 先导中，最高相似项、全部等价、全部冲突、模型/规则分歧、unresolved 和疑似 false negative 全部双审；
- 正式样本至少 20% 按数据集、相似度和冲突类型分层双审；最终比例由 P5 功效与资源包冻结。

### 9.2 分歧优先级

按下列顺序仲裁：

1. 目标参照是否有效、目标组是否唯一；
2. `relevance_status`；
3. `target_relation`；
4. `conflict_type`；
5. `adjudicability`；
6. `candidate_pair_relation`。

上游字段未解决时，不仲裁下游字段。仲裁员必须写明引用的手册条款；若条款不足，修订手册并重新标注所有受影响的校准案例，不能只修当前一条。

### 9.3 一致性输出

至少报告：

- 各字段原始一致率；
- `target_relation` 与 `conflict_type` 的 macro-F1；
- 多类别名义标签的 Krippendorff's alpha；
- 各数据集、各冲突类型和高相似分带的分层分歧率；
- unresolved 比例及原因分布。

### 9.4 P2 桌面校准准入线

下列规则在两名标注员提交前冻结。桌面包只有 12 案例、13 条候选，因此主准入线使用可逐条核验的计数；macro-F1 和 Krippendorff's alpha 仍完整报告，但不以该小样本上的不稳定单点阈值代替逐例审计。

初始独立标注必须同时满足：

1. 两人均提交 12 条案例资格、13 条候选和 1 条候选对记录；缺失、重复、非法枚举或非法字段组合均为 0；
2. 两人对 12 个目标参照均判断为 `valid`，对 12 个目标组均判断为 `unique`；任一 `invalid/non_unique/unresolved` 立即暂停并复核制品，不计算后续通过率；
3. `target_relation` 两人原始一致至少 12/13，且每人对锁定 facilitator key 至少 12/13；
4. 对 key 中 9 条事实冲突，`conflict_type` 两人原始一致至少 8/9，且每人对 key 至少 8/9；
5. 对同 9 条事实冲突，`adjudicability` 两人原始一致至少 7/9，且每人对 key 至少 7/9；
6. 唯一候选对的 `candidate_pair_relation=same_fact` 必须由两人独立判对；
7. `equivalent` 与 `factual_conflict` 之间不得发生任何互判；疑似 false negative 案例不得仅因公开 qrel 缺席/低等级被判为错误；证据定位不得只引用 qrel、相似度或排序。

第 7 条属于关键构念错误，不能由总准确率抵消。任一准入线未满足时，P2-05 不通过：先按分歧优先级仲裁，判断是手册、案例还是标注理解的问题；若修改手册或案例，则两人须在看不到旧答案与 facilitator key 的新副本上重做全部受影响字段，并把首轮与重放结果都保留。只有全部准入线满足、所有分歧完成条款级仲裁且机器校验为 0 错误，才可把手册升级为 v2 并进入 30-family 构造率先导。该结论只表示标注构念可操作，不是 Gate A 证据。

## 10. 12 案例桌面校准包

本手册先定义配额，再由确定性脚本从公开 pinned 数据生成实际案例。案例必须与 GateA/Blind family 隔离；任何桌面校准结果都不得并入 Gate A/B。

| 案例格 | 数量 | 必须覆盖 |
| --- | ---: | --- |
| 版本/时间冲突 | 2 | 一个可条件裁决、一个仅可检测/不可识别 |
| 数字冲突 | 2 | 单位可换算边界与真正不相容各一 |
| 否定/方向冲突 | 2 | 显式否定与语义方向反转各一 |
| 适用条件冲突 | 2 | 条件缺失与条件替换各一 |
| 事实等价 | 1 | 表述不同但可替代 |
| 普通错误 | 1 | 主题相似但不是同事实冲突 |
| 疑似 false negative | 1 | qrel 缺席/低等级但正文疑似或确实能回答，用于训练“源标签不覆盖人工层” |
| 错误共识/不可识别 | 1 | 候选对 `same_fact`，但共同给出错误值或 method view 无法处置 |

共 12 个案例、两名标注员，至少 24 次独立初始判断。校准包验收要求：

- 所有必填字段完整，合法组合校验为 0 错误；
- 每个分歧均完成条款级仲裁；
- 任何案例无法唯一落入 schema 时，先修手册再重标；
- 不根据类别比例、相似度分数或排序结果改变事实判断。

### 10.1 已生成的校准制品

最初的 `ROBUST-FUSION-P2-CALIBRATION-2026-08-28-v1` 只保留为历史开发包。后续盲化审计发现其 `annotation_cases.jsonl` 暴露了 `quota_cell`，该字段与待判类别过度对应；同时，旧工作目录中的已填表来自模型/工具先导，而非两名团队成员的人工提交。因此 v1 和这些试填结果均不得用于 P2-05 准入或一致性统计。

当前正式人工输入固定为 `ROBUST-FUSION-P2-CALIBRATION-REPLAY-2026-08-29-v2`：

- 管理员包：`data/robust_fusion/derived/p2_calibration_v2/`，manifest SHA-256 为 `a8eee3dba3e0a7fa5822039ce1f39b7a6b917dec0025d2b83e854ec3a4cb0df2`；
- 冻结构建器：[prepare_robust_fusion_p2_calibration_replay.py](../../scripts/prepare_robust_fusion_p2_calibration_replay.py)，文件 SHA-256 为 `1fd421ca7cfa9f315352166660d6f81cadb6917ee2a4f157c0838aa98234929f`；
- 正式人工交付：`runs/robust_fusion/p2_human_calibration_v2/`，交付 manifest SHA-256 为 `39139ac4a72d2dd2d5f63f347a99c91c49385220709860658de176db98714c12`；
- 输入仍是精确 revision 的 T2 Dev 与 DRUID，且 12 个 Query/claim 全部不复用 v1；Medical、历史 Blind v4/v5 及其 Query 条件化子池均不进入；
- 输出仍为 12 条案例资格、13 条候选级和 1 条候选对空白记录，不增加团队标注量；
- A/B 交付目录均不含 `facilitator_key.jsonl`，旧模型/工具试填被明确标记为无资格。

v2 的盲化 `annotation_cases.jsonl` 只保留稳定案例 ID、包版本、Query 正文、目标参照、候选正文和视图契约；`quota_cell`、数据集/split/原始 ID、目标组管理员 ID、origin、qrel/stance、变换和期望标签均只留在 facilitator 层。两位真实标注员必须各自使用正式空白副本独立作答，初始提交锁定前不得读取 facilitator key。

12 个案例仍覆盖：两个版本/时间冲突、一个单位换算等价与一个真正数字冲突、两个否定/方向冲突、两个适用条件冲突、一个自然等价、一个主题相关普通错误、一个公开 qrel 疑似漏标，以及一个错误共识候选对。该包只校准通用关系 schema，不进入 Gate A/B。

## 11. 机器校验规则

1. `target_relation=equivalent` 时，`relevance_status` 只能是 `relevant_gold/relevant_equivalent`；
2. `target_relation=factual_conflict/other_incorrect` 时，`relevance_status=verified_incorrect_distractor`；
3. `target_relation=unresolved` 时，`relevance_status=unresolved_possible_false_negative`；
4. 只有 `target_relation=factual_conflict` 才允许四类非空 `conflict_type` 与非 `not_applicable` 的 `adjudicability`；
5. 每个确认性候选必须有唯一目标组、非空 evidence locator、内容 hash 和完成状态；
6. 原始 qrel 与人工标签分列，任何写入覆盖原始值都拒绝；
7. `candidate_pair_relation` 的两个 candidate ID 必须不同并按确定性顺序存储；
8. unresolved、目标参照无效、跨多原子冲突或缺证据项不得进入确认性 chain。
9. 每个案例必须恰有一条资格记录；仅 `target_reference_status=valid` 且 `target_group_status=unique` 时才允许存在完成的候选级或候选对级记录。

## 12. 版本与冻结

本手册 v1 只冻结 schema、判断顺序、unknown 边界和校准包结构。校准输入包升级为 v2 是为了移除盲化字段泄漏并换用未复用案例，不表示手册已通过人工校准；手册只有在正式双人人工校准通过后才升级为 v2。任何会改变已标样本类别的修订必须记录时间、原因、是否看过相关结果、受影响案例清单，并重标受影响的全部 Dev 案例。

Gate A 快照封存后，手册不得因 Gate A 点估计或显著性结果修改。若发现未覆盖的语义缺陷，按预注册规则判定排除、Inconclusive 或新研究周期，不能回写标签挽救本研究。
