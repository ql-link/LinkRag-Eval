# Robust Fusion R2 相似度 measurement 草案

> 记录：`ROBUST-FUSION-RESEARCH-R2-2026-08-29-v1-DRAFT`
> 状态：`DRAFT_NOT_AUTHORIZED`
> 推荐方案：`MATCHED_CALIPER_CONDITIONAL_E5_V1_DRAFT`

## 1. 保持不变的 estimand

候选 (c) 仍锚定唯一目标等价组 (g)，正确参照集合仍为 Clean evaluation view 中的 (A_{qg})。编码器 (z) 下的候选相似度仍为：

\[
S_{qg}(c)=\max_{h\in A_{qg}}\cos(z(c),z(h))
\]

它不是 Query—Chunk 相似度，不是 M1 的候选—近邻特征，也不读取 construction role 形成真值。R2 不因 R1 结果更换主编码器；E5 继续是拟议主工具，DistilUSE 继续是独立敏感性审计，二者 revision 必须在正式预注册时重新逐项列出并一次冻结。

## 2. 操作化变化

R1 要求全局连续 E5 分数同时承担高相似定义、跨长度/语言可比性和人工效度。R2 草案把三个职责分开：

1. **设计匹配**：在任何编码器结果前，按 length、language、dataset、冲突类型和四级表面编辑强度固定成对 family；等价与冲突候选共享表面模板和编辑强度。
2. **人工 caliper**：两候选各自用 7 点行为锚定量表评价相对正确参照的结构/语义接近度；预先要求 family 内绝对评分差不超过 1，且两者均位于拟议高相似区 `>=5`。未满足者保留为 miss，不替换。
3. **条件自动度量**：只在冻结的 `length×language×dataset` cell 内，用 R2 Dev 的 E5 均值与样本标准差（ddof=1）形成条件 z 分数；Gate 层先对候选聚合到 family/压力集，再 dataset 等权。禁止全局 micro 标准化替代。

## 3. 7 点人工量表草案

| 分值 | 行为锚点 |
| ---: | --- |
| 1 | 主题、实体和事件均基本无关 |
| 2 | 仅共享宽泛主题或少量词面 |
| 3 | 同一领域或实体，但事件/谓词不同 |
| 4 | 同一事件框架，但多个关键槽或语义关系不同 |
| 5 | 高度相似；同一框架，存在明显结构改写或一个关键槽差异 |
| 6 | 极高相似；近似复述或单一局部差异，除该差异外结构一致 |
| 7 | 命题含义等价，仅措辞/句法变化 |

评分说明不得告诉研究员 candidate 的正式 relation。事实正确性、目标组唯一性和冲突类型在单独 relation 包中标注。量表校准只允许在不属于 R1、R2 正式 Dev、Gate A、Blind 的练习例上完成。

## 4. 固定 R2 Dev frame 草案

- 128 families、256 候选；四个 length×language cell 各 32 families。
- 每个 cell：numeric、version/time、negation/direction、applicability/condition 各 8。
- 每个类型：四级表面编辑强度各 2；编辑级别通过冻结的词面/句法规则构造，不看 E5/DistilUSE 后决定保留。
- R1 所有 family/text/template hash 进入 hard exclusion；近重复阈值与扩展 family key 必须在正式协议中写死。
- relation 双审 256 行/人，similarity 双审 256 行/人；先锁后比，任何缺失和 uncertain 按固定规则处理。

## 5. 拟议 PASS/INCONCLUSIVE/FAIL

以下仅是待负责人批准的结果前规则草案：

### 5.1 完整性与一致性硬门禁

- 128/128 family 和 256/256 候选进入固定分母；无 R1/Gate/Blind family 泄漏。
- relation A/B 经预定仲裁后全部为 valid reference、unique group 和合法 relation；unresolved 计 miss。
- similarity QWK `>=0.60`、within-one `>=90%`；否则 `FAIL`。
- 每个 length×language cell 的最终人工分至少覆盖 4 个不同档位，单一档位不超过 60%；否则该 cell 无测量分辨率，整体 `INCONCLUSIVE`。

### 5.2 匹配与共同支持

- family 内人工 caliper：两候选均 `>=5` 且差值 `<=1`；总体命中至少 80%，每个 length×language cell 至少 75%。
- 条件 E5 共同支持：等价和冲突在每个可估 cell 的重叠区间各自覆盖至少 60%；missing-as-miss，固定分母不变。
- 任一总体命中点估计低于门槛为 `FAIL`；点估计达到但 family-clustered 单侧 95% 下界未达到门槛为 `INCONCLUSIVE`。正式协议需固定区间算法。

### 5.3 人工效度主门禁

- 主统计量是把每个 cell 内 E5 条件标准化后、按 family 和 dataset 等权得到的 E5—人工 Spearman；点估计 `>=0.50`，且 family-clustered 单侧 95% 下界 `>0.30`。
- 相同规则的 Kendall tau-b 作为共同必要的秩稳健性检查，拟议点估计 `>=0.35`；正式数值需在预注册前由模拟功效和外部解释性确认。
- 四个 length×language cell 的 E5—人工方向均须 `>0`，且不得有预定义 leave-one-cell-out 后主关联下降超过 0.15；这些是聚合稳定性门禁，不提供替代 PASS。
- relation 内分别报告关联；若任一 relation 内人工分为常数，则整体 `INCONCLUSIVE`，因为不能再次让 relation 类别独自制造总体相关。
- DistilUSE、相邻 caliper 和 raw E5 仅作敏感性，不提供 PASS 替代路径。

### 5.4 唯一终止

完整性、一致性、人工分辨率、匹配/共同支持和人工效度全部 PASS，才可一次性冻结条件标准化参数、caliper 和 Gate 用 measurement manifest。任一 FAIL 即 `R2_MEASUREMENT_FAIL_TERMINAL`；未失败但证据不足即 `R2_MEASUREMENT_INCONCLUSIVE_TERMINAL`。两者都不授权 readiness/Gate，也不允许补样、换模型、降阈值或重画 strata。

## 6. 截断与编码器角色

正式预注册必须给每个 encoder 固定最大长度、tokenizer revision、截断侧和超长处理。R2 Dev 必须在每个 length×language cell 报告截断比例，并对 DistilUSE 截断/未截断作预定敏感性；任何 cell 截断状态与 cohort 完全共线时，该敏感性记不可解释。E5 主角色不能因为 R1 失败被事后替换，DistilUSE 也不能因为 R1 combined 通过而晋升。若未来提议新主编码器，必须给出独立学术理由、单一候选、全新 family-disjoint Dev 一次验证，禁止模型赛马。
