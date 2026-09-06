# 鲁棒融合研究标注全量操作手册

> 记录：`ROBUST-FUSION-ANNOTATION-FULL-GUIDE-2026-08-29-v8`
> 日期：2026-08-29
> 语言：简体中文
> 当前阶段：P2-05 校准已通过；v6-Dev 30-family 已完成 A/B 双审、提交锁定与主持人仲裁，人工接纳 28/30；Gate A/B 均未运行
> 用途：团队标注工作的单一执行入口
> 保密边界：本文不包含 `facilitator_key.jsonl` 中的案例答案

## Material Passport

| 项目 | 内容 |
| --- | --- |
| 制品类型 | 人工标注协议与操作手册 |
| 主要上游 | 科研协议 v26、标注手册 v2、Internal Stress v13 数据协议、C2 三分边界补充 v1、P2 v2 保留案例与 v3 五例替换包、Internal v6 Dev 双人盲审包 v1 |
| 当前标注 schema | `ROBUST-FUSION-ANNOTATION-HANDBOOK-2026-08-29-v2` |
| 当前 P2 组合 | v2 保留 7 例 + `ROBUST-FUSION-P2-CALIBRATION-PATCH-2026-08-29-v3` 替换 5 例 |
| 当前 v6-Dev 组合 | 30 个结构合格 family 全部双审；28 个接纳、2 个拒绝；A/B 各 30 条资格、90 条候选、90 条候选对 |
| C2 边界补充 | 8 个 Dev-only 管理员规划槽；当前 0 正文、0 答案键、0 人工标签，尚未发包 |
| v3 补包 manifest SHA-256 | `19807a373e6dee0f15fd747819a82fdde1334d5f6437adf5ce4a65b694f783bd` |
| Gate 资格 | 本文和 P2 校准结果均不构成 Gate A/B 证据 |
| 核验状态 | 已与当前字段模板、机器合法组合和 P2 准入线逐项对账 |

## 1. 这份文档解决什么问题

标注相关信息此前分散在下列位置：

- 核心科研定义：[科研协议](https://github.com/ql-link/LinkRag-Eval/blob/50f3a9b0ead581fb17fc3e4080c70361c9f24475/docs/plans/robust-fusion-research.md)；
- 详细语义规则：[事实关系与冲突标注手册](robust-fusion-annotation-handbook.md)；
- v6 数据资格：[Internal Stress v6 数据协议](robust-fusion-internal-stress-v6.md)；
- C2 类别平衡补充：[C2 三分边界最小补充方案](https://github.com/ql-link/LinkRag-Eval/blob/50f3a9b0ead581fb17fc3e4080c70361c9f24475/docs/plans/robust-fusion-c2-boundary-supplement.md)；
- 实际空白字段表：`data/robust_fusion/derived/p2_calibration_v2/` 下的三份 CSV；
- 正式双人人工工作副本：`runs/robust_fusion/p2_human_calibration_v2/`。
- 当前 v6-Dev 双人盲审包：`runs/robust_fusion/internal_v6_deepseek_pilot_v2_human_review_v1/`。

本文将规则、字段、合法组合、填写顺序、双人复核、仲裁、P2 准入线、v6 合成样本边界、文件位置和示例整合在一起。团队成员只需先读本文，再打开分配给自己的标注目录。

若文档间出现冲突，解释优先级为：科研协议最新冻结版本 → 标注手册当前版本 → 本执行手册 → 空白模板。发现冲突时不得自行选择有利标签，应暂停并交由研究负责人修订版本。

## 2. 标注对象与明确排除项

### 2.1 本研究标什么

本研究人工标注以下五类信息：

1. 目标参照是否有效；
2. 目标等价组是否唯一；
3. 候选 Chunk 是否满足 Query；
4. 候选与目标事实之间是等价、事实冲突、普通错误还是无法确定；
5. 候选对之间是否陈述同一事实、互相冲突或缺少比较上下文。

### 2.2 本研究不标什么

- 不评价网页作者、发布机构或组织的“权威性”；
- 不评价最终生成答案的文风或总体质量；
- 不把 Dense、Learned Sparse、BM25 的分数或排名当作人工真值；
- 不把 Reranker、LTR-v3、M1 的输出当作证据；
- 不把公开 qrel 中“未出现”自动视为负例；
- 不因为候选相似度高、看起来像 Hard Negative 就判定事实冲突；
- 不为了类别均衡、样本量或预期科研结论而修改标签。

> **概念解释｜正交标签**：正交表示把三个不同问题分开记录：“是否满足 Query”“与目标事实是什么关系”“方法在推理期能否判断”。一个字段不能替另外两个字段作答。

## 3. 标注角色、独立性与可见视图

| 角色 | 可以看到和执行 | 禁止事项 |
| --- | --- | --- |
| 标注员 A/B | Query、目标参照、目标组、候选正文、允许的证据材料；独立填写标签、证据位置和理由 | 看另一人的答案、`facilitator_key.jsonl`、Reranker/LTR/M1 输出、当前排名、候选构造来源 |
| 仲裁员 | 在两份初始提交锁定后查看分歧，按手册条款作最终处理 | 为提高一致率或类别均衡而改标签 |
| 数据管理员/主持人 | 生成盲化包、保存原始 qrel、版本与 hash、锁定提交、运行格式校验 | 用规则或模型预标注覆盖人工结论 |
| 研究负责人 | 批准手册修订、处理未覆盖的语义边界、冻结正式版本 | 查看 Gate 结果后回改语义规则 |

标注使用 `evaluation_view`，其中可以包含原始 qrel、目标组和证据定位。排序方法只能使用 `method_view`，其中只包含推理期可见的 Query、Chunk 正文、允许元数据和冻结特征。两种视图不得混用。

## 4. 标注单位与标识

### 4.1 案例资格单位

```text
case_id × Query × target_equivalence_group_id
```

它先回答“目标参照是否有效、目标组是否唯一”。资格不通过时，停止该案例后续标注。

### 4.2 候选级单位

```text
Query × target_equivalence_group_id × candidate_chunk_id
```

每个确认性候选必须且只能锚定一个目标等价组。无法唯一锚定时不得由标注员自行选择“最像”的目标组。

### 4.3 候选对级单位

```text
Query × candidate_id_a × candidate_id_b
```

候选对只用于 Top-M 冲突代理的效度审计，不替代候选级标签，也不直接作为 M1 输入。

## 5. 管理层来源字段表

### 5.1 管理层主表字段

以下字段由数据管理员维护，不要求标注员在当前三份 CSV 中重复填写：

| 字段 | 含义与规则 |
| --- | --- |
| `dataset_id` | 数据集稳定标识 |
| `dataset_revision` | 精确 revision、commit 或不可变版本 |
| `query_id` | 优先保留官方 Query ID；本地 ID 另存 |
| `candidate_chunk_id` | 优先保留官方 Chunk/Passage ID；本地 ID 另存 |
| `source_qrel` | 原始 qrel 值或 `unjudged`；永不被人工标签覆盖 |
| `target_equivalence_group_id` | 唯一目标等价组 ID；不能确定时留空并暂停确认性资格 |
| `candidate_origin` | `natural` 或 `synthetic`；标注界面盲化，管理层保留 |
| `content_hash` | 规范化前原始正文的 SHA-256 |
| family 标识 | `query_family_id`、`document_family_id`、`version_family_id`、`counterfactual_template_family_id` |
| 曝光状态 | 是否曾用于历史 v4/v5、开发、提示词或方法选择 |

### 5.2 标注输入文件 `annotation_cases.jsonl`

标注员读取的盲化输入每行代表一个案例，当前字段如下：

| 字段 | 内容 |
| --- | --- |
| `case_id` | 案例稳定 ID，与三份 CSV 对齐 |
| `package_version` | 当前盲化包版本，用于拒绝跨版本混填 |
| `query_text` | 标注员实际阅读的 Query 正文 |
| `target_references` | 目标参照数组；每项包含稳定局部 ID、`display_text` 和 evaluation-view 标记 |
| `candidates` | 待标候选数组；每项包含局部 ID、`display_text`、空的 method-view metadata 和视图标记 |
| `view_contract` | 明确 method view/evaluation view 的允许字段与禁止信号 |

盲化输入不包含 `quota_cell`、数据集/split/原始 ID、目标组管理员 ID、natural/synthetic 来源、源 qrel/stance、构造变换、预期标签或 facilitator key。缺少这些字段是独立校准设计的一部分，不是数据丢失。历史 v1 曾暴露 `quota_cell`，已退出正式人工入口。

## 6. 标注员实际填写的三张字段表

### 6.1 案例资格表 `case_qualification.csv`

| 字段 | 必填 | 填写说明 |
| --- | --- | --- |
| `case_id` | 是 | 模板已给出，不得修改 |
| `reviewer_id` | 是 | 标注员 A 填 `A`，标注员 B 填 `B` |
| `target_reference_status` | 是 | `valid` / `invalid` / `unresolved` |
| `target_group_status` | 是 | `unique` / `non_unique` / `unresolved` |
| `evidence_locator` | 是 | 指向判断目标参照与目标组资格的精确位置 |
| `rationale` | 是 | 简述为什么有效/无效、唯一/不唯一 |
| `confidence` | 是 | `high` / `medium` / `low` |
| `adjudication_status` | 是 | 初始保持 `single` |
| `handbook_version` | 是 | 保持模板给出的版本，不得自行改写 |

只有 `target_reference_status=valid` 且 `target_group_status=unique` 时，才允许继续填写该案例的候选级和候选对级记录。手册中的自然语言“target_reference_invalid”只表示这一情形，CSV 合法值必须写成 `target_reference_status=invalid`。

### 6.2 候选级表 `candidate_annotation.csv`

| 字段 | 必填 | 填写说明 |
| --- | --- | --- |
| `case_id` | 是 | 模板已给出，不得修改 |
| `candidate_id` | 是 | 模板已给出，不得修改 |
| `reviewer_id` | 是 | `A` 或 `B` |
| `relevance_status` | 是 | 候选是否满足 Query |
| `target_relation` | 是 | 候选与目标事实的关系 |
| `conflict_type` | 是 | 事实冲突时选四类之一；其他关系填 `not_applicable` |
| `adjudicability` | 是 | 事实冲突时选择可裁决边界；其他关系填 `not_applicable` |
| `evidence_locator` | 是 | 同时定位目标证据与候选关键片段 |
| `rationale` | 是 | 写明实体、事实槽、时间/版本、方向和条件的比较结果 |
| `confidence` | 是 | `high` / `medium` / `low` |
| `adjudication_status` | 是 | 初始保持 `single` |
| `handbook_version` | 是 | 使用当前冻结手册版本 |

### 6.3 候选对表 `pair_annotation.csv`

| 字段 | 必填 | 填写说明 |
| --- | --- | --- |
| `case_id` | 是 | 模板已给出 |
| `candidate_id_a` | 是 | 模板已给出，不得与 B 相同 |
| `candidate_id_b` | 是 | 模板已给出，按确定性 ID 顺序存储 |
| `reviewer_id` | 是 | `A` 或 `B` |
| `candidate_pair_relation` | 是 | 两候选之间的事实关系 |
| `evidence_locator` | 是 | 定位两候选的对应事实槽 |
| `rationale` | 是 | 说明实体、事实槽、时间和条件是否可比 |
| `confidence` | 是 | `high` / `medium` / `low` |
| `adjudication_status` | 是 | 初始保持 `single` |
| `handbook_version` | 是 | 使用当前冻结手册版本 |

## 7. 全部枚举值与定义

### 7.1 案例资格

| 字段 | 值 | 定义 |
| --- | --- | --- |
| `target_reference_status` | `valid` | 目标参照正确、完整并满足 Query 的时间、版本和适用条件 |
|  | `invalid` | 目标参照错误、过时、答非所问或不能承担目标真值 |
|  | `unresolved` | 按允许证据仍无法确认目标参照是否有效 |
| `target_group_status` | `unique` | 目标组边界唯一，组内成员可以互相替代且不改变答案 |
|  | `non_unique` | 存在两个以上无法合并的合理目标组，或目标组混入不相容答案 |
|  | `unresolved` | 无法稳定确定目标组边界 |

### 7.2 `relevance_status`

| 值 | 操作定义 |
| --- | --- |
| `relevant_gold` | 原始目标证据，且其正确性与适用范围已经通过本研究复核 |
| `relevant_equivalent` | 支持同一事实，在 Query 条件下可以替代 Gold 且不改变答案 |
| `verified_incorrect_distractor` | 有可定位证据确认其不满足 Query |
| `unresolved_possible_false_negative` | 无法排除实际相关、证据冲突、语境不足或公开 qrel 漏标 |

### 7.3 `target_relation`

| 值 | 操作定义 |
| --- | --- |
| `equivalent` | 同一实体、事实槽、时间和条件下给出相同或相容答案 |
| `factual_conflict` | 对同一可比事实给出互不相容的值、方向、版本或条件 |
| `other_incorrect` | 确实不满足 Query，但属于跑题、信息不足、实体错配或普通无关，不是目标事实冲突 |
| `unresolved` | 证据不足，不能稳定落入前三类 |

### 7.4 `conflict_type`

| 值 | 操作定义 |
| --- | --- |
| `version_or_time` | 使用错误版本、年份、生效期、截至日期，或把历史状态当作当前状态 |
| `numeric` | 在同一单位、口径和范围下给出错误数字、区间、比例、序号或量级 |
| `negation_or_direction` | 把允许/禁止、增加/减少、支持/反对、存在/不存在等方向反转 |
| `applicability_or_condition` | 省略、替换或违反决定答案成立的人群、地区、型号、阶段、辖区或触发条件 |
| `not_applicable` | 当前候选不是已确认的目标事实冲突 |
| `unresolved` | schema 中保留的枚举；当前 P2 机器合法组合不使用此值 |

当前可执行规则要求：当 `target_relation=unresolved` 时，`conflict_type` 仍填 `not_applicable`，而不是 `unresolved`。这是因为尚未确认存在事实冲突，不能先行指定冲突类型。

### 7.5 `adjudicability`

| 值 | 操作定义 |
| --- | --- |
| `conditionally_adjudicable` | method view 中有明确且冻结的版本、时间、数值、方向或适用条件，可在不读取 qrel/Gold 身份时选择正确成员 |
| `detectable_only` | 能发现同一事实槽存在冲突，但 method view 信息不足以选择正确侧 |
| `unidentifiable` | evaluation view 知道真值，但 method view 连稳定识别或处置冲突都做不到 |
| `not_applicable` | 候选不是已确认的目标事实冲突 |

不能因为标注员有常识就标 `conditionally_adjudicable`；必须在 `evidence_locator` 或 `rationale` 中指出 method view 的具体可用字段或文本。

### 7.6 `candidate_pair_relation`

| 值 | 操作定义 |
| --- | --- |
| `same_fact` | 两候选在同一实体、事实槽、时间和条件下给出相同或相容陈述；两者共同给出同一个错误值也属于此类 |
| `factual_conflict` | 两候选在同一可比事实下互相矛盾；此标签不判断哪一方正确 |
| `insufficient_context` | 可以明确指出缺少实体、时间、条件或指代上下文，因此无法比较 |
| `unresolved` | 完成规定核验与仲裁后仍无法稳定分类 |
| `not_annotated` | 占位或明确未标状态，不是完成后的有效判断 |

### 7.7 通用人工字段

| 字段 | 合法值或规则 |
| --- | --- |
| `evidence_locator` | 必须能回到具体 record、段落、句子、表格行、字段或稳定版本位置 |
| `rationale` | 必须写事实比较理由，不能只重复标签名 |
| `reviewer_id` | 当前校准使用 `A` / `B` |
| `confidence` | `high` / `medium` / `low`；只表示把握度，不改变类别 |
| `adjudication_status` | `single` / `agreed` / `disputed` / `adjudicated` / `unresolved` |
| `handbook_version` | 当前为 `ROBUST-FUSION-ANNOTATION-HANDBOOK-2026-08-29-v2` |

`single` 由标注员初始填写；`agreed`、`disputed`、`adjudicated` 和最终 `unresolved` 由主持人或仲裁流程在两份初始结果锁定后写入。科研协议中偶见的 `adjudicated_status` 不是当前 P2 CSV 字段；当前唯一可执行字段名是 `adjudication_status`，不得自行新增同义列。

## 8. 候选级合法组合矩阵

| `target_relation` | 合法 `relevance_status` | `conflict_type` | `adjudicability` |
| --- | --- | --- | --- |
| `equivalent` | `relevant_gold` 或 `relevant_equivalent` | `not_applicable` | `not_applicable` |
| `factual_conflict` | `verified_incorrect_distractor` | 四类冲突之一且只能一个 | `detectable_only` / `conditionally_adjudicable` / `unidentifiable` |
| `other_incorrect` | `verified_incorrect_distractor` | `not_applicable` | `not_applicable` |
| `unresolved` | `unresolved_possible_false_negative` | `not_applicable` | `not_applicable` |

下列组合一律非法：

- `equivalent + verified_incorrect_distractor`；
- `factual_conflict + relevant_gold/relevant_equivalent`；
- 非事实冲突却填写四类 `conflict_type`；
- 非事实冲突却填写非 `not_applicable` 的 `adjudicability`；
- 事实冲突没有唯一主 `conflict_type`；
- 用低置信度代替 `unresolved`，或用高置信度代替证据定位。

## 9. 标注员逐步操作流程

### 步骤 1：提取 Query 约束

先写清楚：

1. 核心实体是谁或是什么；
2. 待回答的事实槽是什么；
3. Query 是否指定时间、版本或截至日期；
4. Query 的方向是什么；
5. 是否存在人群、地区、型号、阶段、辖区或触发条件。

### 步骤 2：完成案例资格

核对目标参照是否真正满足 Query，并核对目标组成员是否可以互相替代。只有 `valid + unique` 才继续。

### 步骤 3：判断 `relevance_status`

先判断候选是否满足 Query，不要先看冲突类型。公开 qrel 是起点，不是人工结论。

### 步骤 4：判断 `target_relation`

按顺序比较实体、事实槽、时间/版本、方向和适用条件：

- 全部相同或相容：`equivalent`；
- 同一可比事实但答案不相容：`factual_conflict`；
- 确认错误但不是同事实冲突：`other_incorrect`；
- 证据不足：`unresolved`。

### 步骤 5：事实冲突才选择 `conflict_type`

一次合成变化只能改变一个主事实单元。单位换算后相等不是数字冲突；Query 明确询问历史状态时，旧版本不能因为“不新”而判错；缺一个否定词但整体语义不反转也不能机械判冲突。

### 步骤 6：事实冲突才选择 `adjudicability`

判断依据必须限制在 method view：

- 能选出正确侧：`conditionally_adjudicable`；
- 只能发现存在冲突：`detectable_only`；
- 连稳定识别或处置都不能：`unidentifiable`。

### 步骤 7：必要时填写候选对关系

候选对按确定性 ID 顺序阅读，不显示哪一条排名更高。候选对标签不要求判断哪一侧正确。

### 步骤 8：补齐证据、理由和置信度

每个结论必须能被另一名标注员复查。只写“与 Gold 不同”“模型认为错误”“相似度很高”均不合格。

## 10. `other_incorrect`、事实冲突和普通高相似的边界

以下情况属于 `other_incorrect`，不是 `factual_conflict`：

- 只讨论同一主题但没有回答相同事实槽；
- 实体、对象或事件不同；
- 只有背景信息，缺少答案；
- 正文损坏、语义不完整；
- 纯关键词重合、模板重合或近重复，但没有不相容事实；
- 统计口径不同且无法建立可比关系。

高相似度、同文档、近重复和同模板只是候选属性。相似候选既可能是等价证据，也可能是事实冲突，不能直接由相似度推出标签。

## 11. False negative 与 unknown 处理

> **概念解释｜False negative 审计**：公开 qrel 没有把某候选标为相关，但它实际上可能完整回答 Query。审计的目的，是避免把漏标正确证据误当成困难负例。

出现下列任一情况，优先使用：

```text
relevance_status=unresolved_possible_false_negative
target_relation=unresolved
conflict_type=not_applicable
adjudicability=not_applicable
```

适用情形包括：

- qrel 未判断，但候选似乎可能完整回答 Query；
- 两份可信证据互相矛盾，且无法确定时间或范围；
- 候选依赖缺失的上文、表格标题、图注或外部指代；
- 专业领域或强时效事实缺少合格证据；
- 目标参照自身疑似错误或过时。

`unresolved` 不进入 C1/C2 确认性主分析，不能为了补足每个 Query 的冲突候选数量而强制裁决。其数量、相似度分布和原因必须单独报告。

必须区分：

- 真值未知：`target_relation=unresolved`，排除确认性分析；
- 真值已知但方法不可识别：`target_relation=factual_conflict + adjudicability=unidentifiable`，作为 C2 边界样本保留。

## 12. 证据要求与优先级

`evidence_locator` 必须指向可复查位置，优先级如下：

1. 数据集内同一官方 record 的明确文本位置；
2. 数据集官方标注说明、正式 qrel 或原始出处；
3. 稳定的一手权威材料及其版本或日期；
4. 两名标注员均认可的限定性辅助来源。

不合格证据包括：

- “这是常识”；
- “模型判断如此”；
- “搜索结果第一条”；
- “和 Gold 不同”；
- 只有 qrel、相似度或排名，没有正文事实定位。

涉及论文时只记录 DOI，不在标注包中写论文下载链接。医学、法律、时效性事实若没有可靠版本化证据，应转为 `unresolved`，而不是凭常识强判。

## 13. 各数据集的映射边界

### 13.1 T2Ranking

- grade 2/3 只提供 relevant 起点，仍须确认是否属于目标等价组；
- grade 0/1 是已判断不满足检索需求的起点，可用于筛选普通错误，但不自动成为事实冲突；
- qrels 外 passage 一律是 `unjudged`；
- `qrels.retrieval.dev.tsv` 只作正例索引，不覆盖四级 qrel。

### 13.2 cMedQA2

- Train triplet 和 Dev/Test 的 0/1 只提供 answer-selection 标签；0 不自动等于事实冲突；
- 诊断、治疗、药物、剂量和时效事实必须有合格证据定位；
- 医学域只作为分层属性，不新增医学专用标签或 Gate；
- 上游 Dev 为 calibration/exposed-only；Train/Test 仍须按 Query、回答/文档、版本和反事实模板 family 隔离；
- 本地受控盲化包只呈现最小必要正文，版本化或公开制品不得复制整段原始问题/回答。

### 13.3 DRUID

- `chunk_stances` 是相对 claim 的 stance，不等于本研究目标关系；
- `is_helpful_chunk` 不等于正确；
- `is_gold_chunk` 表示原事实核查来源身份，不自动等于 `relevant_gold`；
- 只用于英文 RQ1/RQ2 复现与代理效度，不进入 C1 六单元或 Gate B。

### 13.4 DuRetrieval 与 C-MTEB Cmedqa

- DuRetrieval 是独立数据集，保持其固定 corpus、Query 和 qrel 完整性；
- C-MTEB Cmedqa 的来源剥离只用于 provenance 和历史曝光对账，不产生新的事实关系标签；
- `both_exact` 不强制单归因；
- 2,536 条 `unresolved_neither` 保持仅审计类别，不回配、不专项标注、不删除，也不作为正式语义输入。

### 13.5 MedicalRetrieval / Multi-CPR

当前因固定上游许可不清晰而被 cMedQA2 替换，只保留许可审计与历史追溯，不制作确认性标注包。

### 13.6 Internal Stress v6

- v5 只可作为已曝光的开发材料、prompt/schema 参考和构造成本依据；
- 新 v6 合成样本必须明确标记 `synthetic`，保存父事实、变更前后片段、冲突类型、生成模型和原始响应 hash；
- DeepSeek 提议的标签只用于筛选，不是最终真值；
- 最高相似候选、全部等价、全部冲突、模型/规则分歧、unresolved 和疑似 false negative 必须双审；
- 合成反事实一次只能改变一个事实单元；
- 生成样本必须与自然语料一样重新计算 Dense、Learned Sparse、BM25，不得手填分数、排名或命中路；
- Dev 先导不得进入 GateA/Blind。v6 合成 Query 路径已写入科研协议 v26 与 Internal Stress v13；30-family 已得到 28/30 的双审人工接纳率，但仍只估计受控合成 family 的构造流程，不估计自然候选产率，也不自动获得确认性资格。三路执行的 v2/v3 失败与 v4 完整性拒收均原样保留；独立 v5 已完成 28 Query/112 Chunk/3,056 候选的真实三路物化，112/112 已标注候选和 28/28 gold target 均进入候选并集。该结果只关闭 Dev route-evidence 缺口，不改变人工标签、不完成正式 P4-02，也不授予 Gate 资格。

### 13.7 C2 三分边界补充包

- 本包固定为 8 个 Dev-only 微案例：numeric/version 各一条 `conditionally_adjudicable → detectable_only → unidentifiable` 匹配链，另加 direction 与 applicability 两个条件可裁决案例；
- 当前管理员包只有 slot 与空模板，标注员不得据此开始填写；必须等待主持人完成正文生成、结构复核和新盲化目录分配；
- `quota_plan`、目标 `adjudicability`、matched-chain 身份、构造角色、origin 和 facilitator key 都是管理员字段，不进入 A/B 包；
- A/B 各固定填写 8 条案例资格、16 条候选和 8 条候选对；先锁后比，任何无法由具体 method-view 字段和确定性规则选边的条件可裁决案例必须拒绝，不得降类补数；
- 通过只表示 Dev 测量边界获得更均衡校准，不进入 C2 的 held-out 10 项比较家族，也不授权 Gate A/B。

## 14. 双人复核、仲裁和一致性统计

### 14.1 覆盖规则

- P2 的 12 个桌面案例：100% 双人独立标注；
- P3/构造率先导：最高相似项、全部等价、全部冲突、模型/规则分歧、全部 unresolved、全部疑似 false negative：100% 双审；
- 正式样本：进入确认性压力池的候选 100% 至少单人内容复核；至少 20% 按数据集、相似度和冲突类型分层双审；
- 最高相似分带、全部等价对照、全部分歧和疑似 false negative 即使已超过 20% 仍必须第二人复核。

### 14.2 仲裁顺序

1. 目标参照是否有效；
2. 目标组是否唯一；
3. `relevance_status`；
4. `target_relation`；
5. `conflict_type`；
6. `adjudicability`；
7. `candidate_pair_relation`。

上游字段没有解决前，不仲裁下游字段。仲裁员必须记录引用的手册章节；若发现手册缺口，应先修订手册，再让两名标注员在看不到旧答案和 facilitator key 的新副本上重标全部受影响字段。

### 14.3 一致性报告

至少报告：

- 每个字段的原始一致率；
- `target_relation` 与 `conflict_type` 的 macro-F1；
- 多类别名义标签的 Krippendorff's alpha；
- 适用时报告 Cohen's kappa；
- 各数据集、冲突类型和高相似分带的分层分歧率；
- unresolved 数量、比例和原因分布；
- 首轮与重放结果，不得只保留更好的一轮。

## 15. P2 桌面校准：团队实际怎么做

### 15.1 包内容

校准先从 v2 无类别提示包开始；首轮主持人审查发现 5 个案例的目标唯一性、原子性或可裁决措辞缺陷后，保留首轮失败记录，并使用 v3 五例补包一对一替换受影响案例，没有事后改 key 回算通过。

历史 v1 因盲化输入包含与答案类别过度对应的 `quota_cell` 已退出正式入口；旧 DeepSeek/工具目录中的已填表只作流程试演，不能计入人工一致性或 P2-05。v2 是首轮正式输入，v3 只替换首轮被主持人判定为制品缺陷的 5 例；两轮原始结果均保留。

```text
data/robust_fusion/derived/p2_calibration_v2/
├── README.md
├── annotation_cases.jsonl
├── case_qualification_template.csv
├── candidate_annotation_template.csv
├── pair_annotation_template.csv
├── facilitator_key.jsonl
├── manifest.json
├── manifest.sha256
├── view_contract.json
└── 标注操作手册.md
```

包内共有：

- 12 个案例；
- 12 条案例资格记录；
- 13 条候选级记录；
- 1 条候选对记录；
- 版本 `ROBUST-FUSION-P2-CALIBRATION-REPLAY-2026-08-29-v2`；
- manifest SHA-256 `a8eee3dba3e0a7fa5822039ce1f39b7a6b917dec0025d2b83e854ec3a4cb0df2`。

12 个案例的覆盖配额如下：

| 案例格 | 数量 | 主要边界 |
| --- | ---: | --- |
| 版本/时间冲突 | 2 | 一个可条件裁决，一个仅可检测或不可识别 |
| 数字相关边界 | 2 | 一个单位换算等价，一个真正数字冲突 |
| 否定/方向冲突 | 2 | 显式否定与语义方向反转 |
| 适用条件冲突 | 2 | 条件缺失与条件替换 |
| 事实等价 | 1 | 表述不同但可以替代 |
| 普通错误 | 1 | 主题相似但不是同事实冲突 |
| 疑似 false negative | 1 | qrel 缺席或低等级，但正文可能回答 Query |
| 错误共识/不可识别 | 1 | 候选对陈述同一错误事实，或 method view 无法处置 |

### 15.2 已准备的双人目录

```text
runs/robust_fusion/p2_human_calibration_v2/
├── annotator_a/
│   ├── INSTRUCTIONS.md
│   ├── annotation_cases.jsonl
│   ├── package_receipt.json
│   ├── view_contract.json
│   ├── 标注操作手册.md
│   ├── case_qualification.csv
│   ├── candidate_annotation.csv
│   └── pair_annotation.csv
└── annotator_b/
    ├── INSTRUCTIONS.md
    ├── annotation_cases.jsonl
    ├── package_receipt.json
    ├── view_contract.json
    ├── 标注操作手册.md
    ├── case_qualification.csv
    ├── candidate_annotation.csv
    └── pair_annotation.csv
```

两个目录均不得出现 `facilitator_key.jsonl`。

### 15.3 标注员操作

1. 只打开分配给自己的目录；
2. 阅读本手册和 `annotation_cases.jsonl`；
3. 先完整填写 `case_qualification.csv`；
4. 对资格为 `valid + unique` 的案例填写 `candidate_annotation.csv`；
5. 最后填写 `pair_annotation.csv`；
6. 保留 CSV 表头、ID、行数、行顺序和 UTF-8 编码；
7. 不与另一名标注员讨论；
8. 将三份完成的 CSV 交给主持人，不修改 `annotation_cases.jsonl`。

### 15.4 主持人锁定与比较

1. 分别接收 A/B 三份 CSV；
2. 在查看答案前记录每个提交文件的 SHA-256 和接收时间；
3. 检查行数、重复 ID、空值、非法枚举和非法组合；
4. 两份初始提交都锁定后，才允许读取 `facilitator_key.jsonl`；
5. 生成逐字段一致率和分歧清单；
6. 按第 14.2 节顺序仲裁；
7. 首轮和重放记录全部保留。

## 16. P2 校准准入线

下列条件必须同时满足：

1. 两人各提交 12 条案例资格、13 条候选和 1 条候选对；缺失、重复、非法枚举、非法组合均为 0；
2. 两人对 12 个目标参照均判 `valid`，对 12 个目标组均判 `unique`；任何 `invalid/non_unique/unresolved` 都立即暂停并复核制品；
3. `target_relation` 两人原始一致至少 12/13，且每人对锁定 facilitator key 至少 12/13；
4. key 中 9 条事实冲突的 `conflict_type`：两人原始一致至少 8/9，且每人对 key 至少 8/9；
5. 同 9 条事实冲突的 `adjudicability`：两人原始一致至少 7/9，且每人对 key 至少 7/9；
6. 唯一候选对的 `candidate_pair_relation=same_fact` 必须由两人独立判对；
7. `equivalent` 与 `factual_conflict` 之间不得发生任何互判；疑似 false negative 不得仅因 qrel 缺席或等级低被判为错误；证据定位不得只引用 qrel、相似度或排序；
8. 所有分歧完成条款级仲裁，最终机器校验错误数为 0。

第 7 条是零容忍构念错误，不能由总体准确率抵消。任一条件失败时，P2-05 不通过。应先判断问题来自手册、案例还是标注理解；如修改手册或案例，两人必须在新副本上重做全部受影响字段。

P2 通过只说明“标注构念可操作”，允许进入 30-family 可构造率先导；它不是 Gate A 证据。

### 16.1 本轮最终校准结果

| 项目 | A–B | A–key | B–key | 结论 |
| --- | ---: | ---: | ---: | --- |
| 资格字段 | 12/12 | 12/12 | 12/12 | 通过 |
| `target_relation` | 13/13 | 13/13 | 13/13 | 通过 |
| 9 条冲突的 `conflict_type` | 9/9 | 9/9 | 9/9 | 通过 |
| 9 条冲突的 `adjudicability` | 8/9 | 9/9 | 8/9 | 通过，准入线为 7/9 |
| 唯一候选对 `same_fact` | 1/1 | 1/1 | 1/1 | 通过 |
| 格式与零容忍构念错误 | 0 | 0 | 0 | 通过 |

唯一分歧是 `RF-P2R2-02/C1` 的 `adjudicability`。Query 和候选正文已经明示 `102×0.55`，冻结的确定性算术规则可仅凭 method view 推出 `56.1`，因此最终标签为 `conditionally_adjudicable`。该规则在 v3 补包发放前完成澄清；B 的原始 `unidentifiable` 与冻结 key 均原样保存。

最终 `P2-05=PASS`。主持人因创建 v3 补包而预先知道 key，所以不声称主持人盲态；A/B 独立盲标、提交先锁后比的审计主张成立。最终机器结论 SHA-256 为 `fe906b9e755135cfe4fe6607297aec5c5a0c2b2c0a0a5118e4c38ada9a01ef1c`，提交锁 SHA-256 为 `9d743fb23d4d88d128229a81d381aab444550e2663e11eacbe296cad0c722f82`。

### 16.2 Internal v6 Dev 当前双人盲审包

当前正式人工入口为：

```text
runs/robust_fusion/internal_v6_deepseek_pilot_v2_human_review_v1/
├── annotator_a/
│   ├── annotation_cases.jsonl
│   ├── case_qualification.csv          # 30 行
│   ├── candidate_annotation.csv        # 90 行
│   ├── pair_annotation.csv             # 90 行
│   └── 标注说明.md
├── annotator_b/                         # 同样结构，案例/候选显示顺序独立打乱
├── facilitator/                         # 只允许主持人读取
└── facilitator_review/
    ├── locked_submissions/              # A/B 六份原始提交快照
    ├── frozen_inputs/                    # 发包输入与构造映射快照
    ├── analysis_v3/                     # 机械校验、一致性与构造偏差
    └── final_v1/                         # 最终标签、仲裁、接纳台账与 manifest
```

本轮 30 个 family 全部是自包含的虚构微型事实世界。包内 T1 是 evaluation view 中待复核的目标参照；不联网核实，也不把现实常识带入真值判断。Query、C1/C2/C3 和空的 method-view 元数据用于 `adjudicability`；判这个字段时不得用 T1 选正确侧。

标注员看不到 generation ID、候选构造角色、冲突配额、origin、模型关系标签或源批次。A/B 的 case ID 和 candidate ID 集合相同，显示顺序不同，便于锁定后逐行比较。两人必须依次完成资格 → 候选 → 候选对，不能先读取 `pair_annotation.csv` 倒推候选类别，也不能进入另一人的目录或 `facilitator/`。

交付 manifest SHA-256 为 `b5ad4ac4663e670be02e8e71eca5257e1106d420ac3153a8ac1fe155dd514db3`。该 hash 对应空白发包版本，人工填写没有重写它。主持人于比较答案前另建只读提交锁，SHA-256 为 `72d8b77ca601c925ff3840afc4812ac1395019d1930548cd98836201adefbb00`；最终裁定 manifest SHA-256 为 `654ff9ff1959aeb18895b8a872c34665c9a262510f13d79146aca6183650b99a`。

### 16.3 Internal v6 Dev 最终双审结果

- 两位标注员的资格字段与候选级四字段全部一致；候选对 89/90 一致；唯一分歧 `RF-V6HR-2A5D398D4D/C1-C3` 最终裁定为 `factual_conflict`。
- 资格字段和四个候选字段的原始一致率、macro-F1、Krippendorff nominal alpha 与 Cohen kappa 均为 1.0。候选对的原始一致率为 0.9889、alpha 为 0.9767、kappa 为 0.9766；macro-F1 为 0.6617，因为唯一分歧恰好落在只出现一次的稀有 `same_fact` 类，故同时保留逐例审计而不以该宏平均单点否定整体一致性。
- 原始提交的机械错误、非法组合和 unresolved 均为 0。B 有 26 条可凭 ID 定位但引号内不是完全逐字的省略/缩写式定位，作为格式警告原样保留；最终表采用逐字定位，最终警告为 0。
- 模型构造角色不是答案键。`RF-V6HR-2A5D398D4D` 与 `RF-V6HR-E7058C1EB3` 的表面控制实际构成同槽事实冲突，两个 family 均拒绝；`RF-V6HR-0E6E7C8889/C2` 和 `RF-V6HR-2A5D398D4D/C2` 的预设类型由人工一致改判为 `numeric`。
- 最终接纳 28/30（93.33%）。接纳后的主冲突类型为 numeric 9、version/time 8、negation/direction 7、applicability/condition 4。
- 28 个主冲突的 `adjudicability` 全部为 `detectable_only`：本批能用于 Dev 冲突检测与压力构造校准，但不能单独验证 C2 三分边界。
- 主持人创建过包与构造映射，所以不声称主持人盲态；只主张 A/B 角色隔离、输入无答案键、提交先锁后比。
- 接纳项已经由 `scripts/materialize_robust_fusion_internal_v6_adjudicated_dev.py` 物化为 28 Query、112 文档、112 证据标签和 28 family assignment；release manifest SHA-256 为 `ad32fbb08a6b076dced1e438ff51060c46073b932cd259ff89beb157e5453bac`。这一步不生成三路分数，也不改变 Dev-only/Gate 禁入边界。

## 17. 两条完整示例

以下为虚构示例，不来自正式 P2 校准包，也不泄露 facilitator key。

### 17.1 示例共同背景

- `case_id=DEMO-01`
- Query：`XR-204 模块的额定功率是多少？`
- 目标证据：`XR-204 模块的额定功率为 3.7 kW。`
- 案例资格：`target_reference_status=valid`、`target_group_status=unique`

### 17.2 示例 1：单位换算后的等价证据

候选：`XR-204 的额定输出功率为 3700 W。`

| 字段 | 填写值 |
| --- | --- |
| `relevance_status` | `relevant_equivalent` |
| `target_relation` | `equivalent` |
| `conflict_type` | `not_applicable` |
| `adjudicability` | `not_applicable` |
| `evidence_locator` | `目标证据“3.7 kW”；候选 C1“3700 W”` |
| `rationale` | `同一实体和事实槽；3700 W 换算后等于 3.7 kW，答案不变。` |
| `confidence` | `high` |
| `adjudication_status` | `single` |

### 17.3 示例 2：无法仅凭 method view 选边的数字冲突

候选：`XR-204 的额定功率为 4.2 kW。`

| 字段 | 填写值 |
| --- | --- |
| `relevance_status` | `verified_incorrect_distractor` |
| `target_relation` | `factual_conflict` |
| `conflict_type` | `numeric` |
| `adjudicability` | `detectable_only` |
| `evidence_locator` | `目标证据“3.7 kW”；候选 C2“4.2 kW”` |
| `rationale` | `同一实体、事实槽、时间和条件下给出不相容数值；能识别存在冲突，但 Query 本身没有提供可选出正确值的信号。` |
| `confidence` | `high` |
| `adjudication_status` | `single` |

## 18. 提交前检查清单

P2 校准包标注员提交前逐项确认：

- [ ] 只填写了自己的目录；
- [ ] 没有查看另一人的文件或 facilitator key；
- [ ] 12 条案例资格均已处理；
- [ ] 只有 `valid + unique` 案例继续候选标注；
- [ ] 候选级每条都有合法的四字段组合；
- [ ] 事实冲突恰有一个主冲突类型；
- [ ] 非事实冲突的 `conflict_type/adjudicability` 均为 `not_applicable`；
- [ ] 每条都有可复核 `evidence_locator` 和非空 `rationale`；
- [ ] 没有把 qrel 缺席、相似度或排名当作错误证据；
- [ ] `reviewer_id` 正确；
- [ ] 初始 `adjudication_status` 仍为 `single`；
- [ ] 表头、ID、行数、行顺序和手册版本未被修改；
- [ ] CSV 仍为 UTF-8 编码。

Internal v6 Dev 标注员除遵守上述语义与格式规则外，另须确认：

- [ ] 只进入了自己的 `annotator_a/` 或 `annotator_b/`；
- [ ] 没有读取 `facilitator/`、另一标注员目录或任何模型原始响应；
- [ ] 已填写 30 条案例资格、90 条候选和 90 条候选对；
- [ ] 把包内 T1 用于资格/事实关系，但判 `adjudicability` 时没有用 T1 选边；
- [ ] 没有联网核证虚构实体，也没有根据候选编号、顺序或风格猜构造角色；
- [ ] 三张 CSV 的 ID、表头、行数、`reviewer_id`、`single` 状态和手册版本均未修改。

C2 边界补充标注员只有收到主持人新分配的盲化目录后才开始，并须确认：

- [ ] 自己的包恰含 8 条案例资格、16 条候选和 8 条候选对；
- [ ] 包内没有 `quota_plan`、目标类别、matched-chain ID、构造角色、origin 或 facilitator key；
- [ ] `conditionally_adjudicable` 的理由指出了具体 method-view 字段与确定性规则，而不是使用 T1 身份选边；
- [ ] `detectable_only` 只声称能发现风险，`unidentifiable` 不声称能从 method view 识别真值；
- [ ] 没有读取当前空白管理员目录或根据 slot 命名猜测答案。

主持人验收前逐项确认：

- [ ] A/B 两份提交均已记录 SHA-256 和时间；
- [ ] facilitator key 在双份提交锁定前未泄露；
- [ ] 缺失、重复、非法枚举和非法组合均为 0；
- [ ] 所有分歧按固定顺序仲裁；
- [ ] 首轮、仲裁和重放结果全部保留；
- [ ] 输出完整一致性统计和 unresolved 报告；
- [ ] P2 结果未并入 Gate A/B。

## 19. 版本、冻结与变更纪律

1. 当前 schema 版本为 `ROBUST-FUSION-ANNOTATION-HANDBOOK-2026-08-29-v2`；
2. P2 双人校准、五例替换重放、仲裁和机器复核已经通过；v2 已正式冻结；
3. 任何改变既有样本类别的修订，必须记录日期、原因、是否看过相关结果和受影响案例，并重标全部受影响 Dev 记录；
4. Gate A 快照封存后，不得因点估计、显著性或方法表现修改手册；
5. 未覆盖的语义缺陷只能按预注册规则排除、记为 Inconclusive，或进入新的研究周期；
6. 原始 qrel、原始正文、人工标签和仲裁结果必须分层保存，任何一层都不得覆盖上一层。

## 20. 当前状态与下一步

截至 2026-08-29：

- 标注字段、操作定义、合法组合和 P2 准入线已经冻结在标注手册 v2；
- A/B 双人独立校准、五例替换重放、主持人仲裁与机器复核已完成，`P2-05=PASS`；
- 所有原始提交、失败首轮、锁定快照和最终裁定均已保留；
- Gate A/B 均未运行；
- Internal Stress v6 的 30-family 首批机械结构产率为 24/30；不可覆盖恢复链补足 30 个结构合格提案；
- A/B 双人盲审、提交锁定、机械校验和主持人仲裁均已完成；最终接纳 28/30，未解决分歧为 0；接纳项已完成四张 Dev 摄取表物化；
- Dev 三路证据 v5 已独立核验：三路各覆盖 28/28 Query，112/112 已标注候选入并集；该运行没有新增或修改人工标签，evaluation view 仍只来源于既有双审与仲裁；
- 28 个接纳 family 只允许进入 `internal-v6-dev` 校准，任何一条都不得迁入 GateA/Blind；GateA/Blind 仍为空并保持 `NOT_ELIGIBLE`。
- C2 三分边界 8 槽补充已完成空白管理员初始化，但案例正文、答案键和 A/B 标注均未开始；不得把“规划槽已存在”写成标注完成。
