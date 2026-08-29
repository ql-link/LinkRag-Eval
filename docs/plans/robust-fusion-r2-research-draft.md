# 高相似度干扰下检索增强生成的多路来源感知鲁棒融合方法研究：R2 协议草案

> `research_id`: `ROBUST-FUSION-R2-2026-08-29`  
> `record_id`: `ROBUST-FUSION-RESEARCH-R2-2026-08-29-v1-DRAFT`  
> 状态：`DRAFT_NOT_AUTHORIZED`  
> 本文件不替换或修改 R1/v29；未获得研究负责人批准前，不得生成 R2 数据、运行编码器、人工发包、readiness 或 Gate。

## 1. 研究身份与 R1 边界

正式题目保持为：**高相似度干扰下检索增强生成的多路来源感知鲁棒融合方法研究**。

“多路来源感知”仍只指 Dense、Learned Sparse、BM25 三条检索路及其分数、排名、命中和缺失证据。R2 不把信息发布者权威性改写成“来源”，不改变三路来源定义。

R1/v29 与其 v1+唯一补充的 terminal `INCONCLUSIVE` 是永久独立结论。R1 的全部 Query、文档族、版本族、反事实模板族和近重复 family 仅可作为 R2 探索性设计证据；它们必须进入 R2 exclusion registry，不得计入 R2 Dev、Gate A 或 Blind 的样本量、共同支持、功效或任何 PASS 分母。

## 2. 研究问题与贡献继承

R2 原样继承 RQ1—RQ3、C1/C2/C3 的科学角色：C1 是等价对照下的事实冲突特异性退化；C2 是可检测、条件可裁决、不可识别边界；C3 仅在 Gate A=Go 后才允许开发。

R2 只重写 P2 的实验相似度操作化和其 Dev 资格流程。它不借测量重启改变排序结局、三路候选定义、事实关系 schema、方法/评价视图隔离、两个 Reranker、数据集等权、Query-family cluster bootstrap 或 Gate A/B 的科学主张。

## 3. 候选相似度方案比较

| 方案 | 核心操作化 | 严谨性 | 预计每位研究员负荷 | 到 Gate A 距离 | 主要风险 |
| --- | --- | --- | ---: | --- | --- |
| A. 条件标准化 E5 | 在预先冻结的 length×language×dataset cell 内标准化 E5，再按 family、dataset 等权汇总 | 中高；直接处理聚合尺度偏移 | 约 3–4 小时 | 最近 | 若人工量表仍压缩，换汇总不能恢复构念分辨率 |
| B. 匹配 caliper + 条件 E5（推荐） | 先按表面结构和编辑强度构造等价/冲突成对 family；盲人工 7 点高相似量表确认匹配，E5 只在冻结 strata 内标准化并检验 | 高；同时处理设计、量表与聚合，自动分数仍可复算 | 约 5–7 小时，另加仲裁 1–2 小时 | 中等 | 工作量较高；若固定 caliper 合格率不足则一次性 Inconclusive/Fail |
| C. 人工优先分带 | 人工高相似匹配直接决定 band，编码器只作审计 | 构念解释强，但自动扩展性弱 | 约 8–12 小时 | 最远 | Gate 候选量大时人工成本和重放性不足，易把测量变成持续人工判定 |

推荐 B。R1 已显示只做全局连续相关不足，且仅换成 DistilUSE 会构成事后模型赛马；方案 B 保留 E5 的冻结主角色，但把它限制为预先分层、可审计的工具，不再要求一个全局连续分数独自承担整个“高相似”构念。

## 4. R2 Dev 固定设计草案

### 4.1 样本与功效

建议固定 `128` 个全新、family-disjoint R2 Dev Query families，每个 family 同时包含一个等价候选和一个事实冲突候选，共 `256` 个候选：

- `short-zh`、`long-zh`、`short-en`、`long-en` 各 32 families；
- 每个 cell 内四类冲突各 8 families；
- 每个冲突类型内预先轮转四级表面编辑强度，各 2 families；
- 数据集/来源配额在资格审计后、生成任何正文和分数前冻结；分析时先 family 等权、再 dataset 等权，不能按实际样本量重定权。

功效按 family 为保守独立单元，不把同一 family 的两候选当成两个独立样本。使用 Fisher-z 近似，在单侧 α=0.05 下检验真实条件化关联 `ρ=0.50` 相对不可接受边界 `ρ=0.30`，`n=128` 的规划功效约 0.85；`n=120` 约 0.83，选择 128 为 ordinal ties、family 聚类和少量不可定义 strata 留出有限裕量。正式冻结前仍须以完全写定的 R2 estimand 做模拟复核；不得看到 R2 分数后改 n。

### 4.2 一次性规则

- R2 Dev 只能有一个固定 128-family 校准周期，无追加、无第三批、无边看边扩样。
- 所有候选正文、family、strata、冲突类型、编辑强度、排除和固定分母在编码器分数与人工结果前封存。
- 结构无效、关系无效、缺失分数、缺失人工行、caliper 不合格均按预注册规则保留为 miss；不得替换或删除失败项。
- R2 Dev 只用于测量资格，不产生 Gate A 证据。
- 只有全部 R2 measurement 硬门禁 PASS，才进入 readiness 资格复核；FAIL/INCONCLUSIVE 均终止当前 R2 测量周期，不允许循环补丁。

## 5. 人工设计草案

两位真实研究员继续双盲、独立 A/B；relation 与 similarity 职责和包物理隔离。评分者看不到编码器分数、分带、希望改善的 strata 或 construction role。

每位研究员预计填写：

- relation：256 行；
- similarity：256 行；
- 合计：512 行，预计 5–7 小时；
- 主持人只处理预先定义的分歧/uncertain，预计 1–2 小时上限。

similarity 改为 7 点行为锚定量表，并明确评估“相对正确参照的语义框架、实体/事件/谓词和表面改写接近度”，事实正确性单独由 relation task 判断。候选在四级编辑强度上预先分布，避免所有等价集中 7、所有冲突集中 6。详细规则见 measurement 草案。

## 6. R2 状态机草案

1. `DRAFT_NOT_AUTHORIZED`
2. `PROTOCOL_APPROVED_NOT_PREREGISTERED`
3. `PREREGISTERED_AWAITING_R2_DEV`
4. `R2_DEV_LOCKED_AWAITING_HUMAN`
5. `R2_DEV_FINALIZED`
6. `R2_MEASUREMENT_PASS_AWAITING_READINESS` / `R2_MEASUREMENT_INCONCLUSIVE_TERMINAL` / `R2_MEASUREMENT_FAIL_TERMINAL`

只有第 6 步的 PASS 分支允许 readiness 资格复核；readiness 通过后仍只是 Gate A 可授权，不是 Gate A 已执行。

## 7. 旧 Gate/Blind 的处置

从未读取内容或结果的旧 Gate A/Blind 候选可以继续保持物理封存和“未见”，不因 R2 草案自动作废，也不能自动继承资格。R2 readiness 前必须做一次 outcome-blind 资格审计：验证它们与 R1 全部 family、R2 Dev、彼此之间均 family-disjoint，且能补齐 R2 measurement 所需 strata、provenance 与条件标准化元数据。若审计需要打开确认性排序结果或内容已被本研究人员读取，则对应集合失去未见资格；当前草案不授权该审计或使用。

## 8. 唯一待决问题

研究负责人是否批准以“128 个全新 family、匹配 caliper + length×language×dataset 条件 E5、7 点行为锚定量表、一次性无追加”为 R2 的正式 measurement 方向？批准仅允许继续写成可时间戳预注册包，不等于授权生成数据或运行 Gate。

