# C2 三分边界最小补充方案

> 记录：`ROBUST-FUSION-C2-BOUNDARY-SUPPLEMENT-2026-08-29-v1`
> 对应标注手册：`ROBUST-FUSION-ANNOTATION-HANDBOOK-2026-08-29-v2`
> 状态：Dev-only 空白方案已冻结；尚未生成正文、尚未发放人工包、不得用于 Gate A/B。

## 1. 为什么仍需补充

P2 桌面校准最终 facilitator key 的 9 条事实冲突中，`conditionally_adjudicable`、
`detectable_only`、`unidentifiable` 分别为 1、1、7 条；Internal Stress v6 首批接纳的
28 个主冲突又全部是 `detectable_only`。因此三个枚举已经有可操作性证据，但分布高度偏斜：

- 条件可裁决只有一个确定性算术案例，无法支撑不同事实类型下的规则实现；
- 当前类别来自不同案例，缺少“只改变 method-view 决定性信号”的匹配边界；
- 这些材料都是 Dev 构念校准，不是 C2 在 held-out 自然冲突上的确认性证据。

本补充只修复 Dev 测量仪器的覆盖，不改变 C2 的 Gate 估计量、10 项比较家族、显著性门槛或
GateA/Blind 人口。

> **概念解释｜匹配边界链**：围绕同一事实槽构造三种 method view：第一种有足够信号选出
> 正确侧，第二种只能发现候选冲突，第三种连风险信号也没有。三者尽量保持主题、长度和措辞
> 接近，使类别差异来自“可见信息是否足够”，而不是来自完全不同的案例。

## 2. 固定规模与配额

补充包固定为 8 个 Dev 微案例、16 条候选级记录和 8 条候选对记录；A/B 各独立提交 8 条资格、
16 条候选、8 条候选对，共 64 条人工表格行。不得为追求一致率删掉困难案例。

| slot | 匹配链 | 主冲突类型 | 目标 `adjudicability` | method-view 核心设计 |
| --- | --- | --- | --- | --- |
| `C2S-N-COND` | numeric | numeric | `conditionally_adjudicable` | Query 明示完整算式或单位换算条件；一真一假候选 |
| `C2S-N-DETECT` | numeric | numeric | `detectable_only` | 保留同槽两值冲突，移除可推出正确值的算式/单位基准 |
| `C2S-N-UNID` | numeric | numeric | `unidentifiable` | 两候选重复同一错误值，metadata 为空；仅 evaluation view 知真值 |
| `C2S-V-COND` | version | version_or_time | `conditionally_adjudicable` | Query 明示截至时间，metadata 明示生效/失效区间；冻结规则可选边 |
| `C2S-V-DETECT` | version | version_or_time | `detectable_only` | 保留两个版本值但移除决定性截至时间或有效区间 |
| `C2S-V-UNID` | version | version_or_time | `unidentifiable` | 两候选重复同一错误版本，且无版本/来源风险元数据 |
| `C2S-D-COND` | direction | negation_or_direction | `conditionally_adjudicable` | Query 明示触发条件和规则方向，可作确定性布尔推导 |
| `C2S-A-COND` | applicability | applicability_or_condition | `conditionally_adjudicable` | Query 明示地区/型号/阶段，候选明示适用范围，可按精确匹配选边 |

该设计新增 4 个条件可裁决案例，并用 numeric、version 两条三段链各提供一个仅可检测和一个
不可识别对照。既有 28 条 detectable-only 不并入本包的人工一致性分母，但可在后续 Dev
测量校准中共同使用。

## 3. 三类必须满足的闭门条件

### 3.1 `conditionally_adjudicable`

- 决定性字段必须存在于 Query、候选正文或允许的生产可见 metadata；
- 必须写出冻结规则，例如四则运算、单位换算、日历比较、版本区间匹配、布尔条件或范围匹配；
- 删除 evaluation view 的 T1、qrel 和构造角色后，仍能唯一选出正确成员；
- 仅能判断“候选未核验”或“候选可疑”不合格，必须降为 `detectable_only`。

### 3.2 `detectable_only`

- method view 中必须有稳定风险信号，如同一事实槽出现互不相容的值；
- Query 与允许元数据不能推出正确值，也不能确定哪一侧更新或适用；
- 不得用 T1 身份、qrel、origin、分路分数或人工标签选边。

### 3.3 `unidentifiable`

- evaluation view 必须有可复核证据证明候选相对目标组为事实冲突，而不是“真值未知”；
- method view 中的候选必须自洽，且没有版本未核验、低置信、来源冲突等风险提示；
- 两候选固定为 `candidate_pair_relation=same_fact`，共同重复同一错误事实；
- 任何方法在这类案例上都不应声称识别真值，M1 的安全行为是保持 LTR-v3 顺序。

## 4. 构造与人工流程

1. 只使用自包含虚构事实世界，或使用已有 Dev-exposed 公开校准记录；不得读取 GateA/Blind；
2. DeepSeek 只生成待审提案，不生成最终人工标签；每个 slot 独立调用，失败不整批自动重跑；
3. 主持人在发包前做原子性、目标唯一性、method/evaluation view 和逐字 evidence 检查；
4. `quota_cell`、目标类别、构造角色、origin、生成记录和 facilitator key 不进入 A/B 包；
5. A/B 使用标注手册 v2 独立判断，提交先锁定，再比较和仲裁；
6. 任一案例不满足预设结构时拒绝整个案例，不按模型预期标签覆盖人工判断；
7. 最终接纳项仍为 `internal-v6-dev`，不得迁入 GateA/Blind，也不得补入 C2 确认性分母。

## 5. 准入与停止规则

- 结构门禁：8/8 案例均 `valid + unique`，16 条候选和 8 条候选对 ID/顺序/合法组合零错误；
- 核心构念零容忍：`equivalent` 与 `factual_conflict` 之间不得互判；不得把 T1 当作
  `adjudicability` 的 method-view 信号；
- `adjudicability`：A/B 至少 7/8 一致，且每人对最终仲裁标签至少 7/8；
- 条件可裁决的 rationale 必须指出具体字段与确定性规则，4 个 slot 中任一无法规则化选边，
  则本补充不通过，不能用 detectable-only 替补名额；
- 不可识别的两条候选对必须由 A/B 均判 `same_fact`；否则先审查案例结构；
- 本轮最多一次、且只针对机械或案例结构缺陷的一对一替换重放；不得按已见标签比例重出全包。

通过仅表示 C2 三分边界在 Dev 上获得更均衡的测量校准，仍不授权 Gate A、M1 或 Gate B。

## 6. 制品与成本

空白管理员包由 `scripts/initialize_robust_fusion_c2_boundary_supplement.py` 生成在：

`data/robust_fusion/internal_stress_v6/dev/supplements/c2_boundary_calibration_v1/`

初始化时只有 8 个管理员 slot 和空摄取表，不包含正文、答案键或人工标签。预计后续成本为：

当前包已按上述规则初始化并独立逐文件核验：`planned_case_count=8`，case/candidate/pair
物化计数均为 0，`human_annotation_started=false`，`gate_eligibility=NOT_ELIGIBLE`；manifest
SHA-256 为 `ff4e00d857641a2d48e0ece509c29bf357f28918757dc4a1980f9906a681f347`。

- DeepSeek：最多 8 次首轮生成调用；恢复调用按失败 slot 单独授权和记账；
- 人工：每位标注员约 45—60 分钟，主持人结构审查与仲裁约 30—45 分钟；
- 检索：只有人工接纳后才进入独立 Dev 三路重算，不与当前 28-family collection 混写。
