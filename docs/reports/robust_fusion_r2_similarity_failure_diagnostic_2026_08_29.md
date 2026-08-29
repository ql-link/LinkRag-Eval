# Robust Fusion R2 相似度失败诊断报告

## Material Passport

- Origin Skill: academic-research-suite / experiment-agent
- Origin Mode: validate
- Origin Date: 2026-08-29
- Verification Status: ANALYZED
- Version Label: robust-fusion-r2-similarity-failure-diagnostic-v1
- Research ID: `ROBUST-FUSION-R2-2026-08-29`
- Record ID: `ROBUST-FUSION-RESEARCH-R2-2026-08-29-v1-DRAFT`
- Status: `EXPLORATORY_DIAGNOSTIC_COMPLETE_R2_DRAFT_NOT_AUTHORIZED`

## 1. 证据地位

本报告在已知 R1/v29 的 v1+唯一补充终局 `INCONCLUSIVE` 后制定并执行，属于 outcome-aware、exploratory 失败诊断，不是事前确认性分析，不为 R1 或 R2 提供新的 PASS 路径。R1 全部制品和结论保持只读；R1 的所有 Query family 只能用于 R2 设计，不能进入 R2 正式 Dev、Gate A 或 Blind。

诊断运行前先写出并封存[诊断计划](../../runs/robust_fusion/r2_similarity_diagnostic_v1/robust-fusion-r2-similarity-diagnostic-v1-20260829/diagnostic_plan.md)和输入 hash manifest。首次 schema 检查发现原枚举未包含表面文本和 computation config，因此在任何统计量计算前追加两个透明输入 addendum 和一份 schema mapping spec；它们只补齐已有 R1 锁定输入，不改变分析规则或确认性权限。

## 2. 制品与可复算性

运行目录：`runs/robust_fusion/r2_similarity_diagnostic_v1/robust-fusion-r2-similarity-diagnostic-v1-20260829/`

| 制品 | SHA-256 |
| --- | --- |
| `diagnostic_plan.md` | `fbf847cc211cac27d7ab20ccfa6666c91ab8c1b0fc6c08273c4b4362b9a894f6` |
| `input_manifest.json` | `eb4894cd6986b8ffb344f60c01031926b5403d658e4027e6d5fceb2b6f28a1da` |
| `schema_mapping_spec.json` | `cffea4f13c3b04667a67e3148784fcd5ab4df31fd70df0f8aa7d4e4bb7f1a29e` |
| `diagnostic_rows.jsonl` | `48a37e4ae71c325579b9caef0920a565af9e012c1c11e2243cf76dfed74e95db` |
| `diagnostic_results.json` | `61251446ac40bda37662b1c6c30802eeae3dfbcf9157a47873e06e92ba43e3e4` |
| `manifest.json` | `872b45bdda7c236d563945814ec96d5ea88bed25da62614024af6f535dfd3bd8` |
| `receipt.json` | `e77d01448dd3862acaf5f906b894a7038a8f7c57c5799cf5d33d5bf1a4786722` |

固定复算命令如下。正式目录是 append-only，重复执行会拒绝覆盖。

```bash
PYTHONPATH=src:. .venv/bin/python scripts/run_robust_fusion_r2_similarity_diagnostic.py
```

## 3. 主要结果

### 3.1 最强证据：量表压缩与校准分布受限同时存在

| 指标 | R1 v1（n=24） | R1 supplement（n=48） |
| --- | ---: | ---: |
| 人工分唯一值 | 3（2/4/5） | 2（4/5） |
| 人工分范围 | 3 | 1 |
| 人工分方差（ddof=1） | 1.3043 | 0.2553 |
| pairwise tie 比例 | 36.23% | 48.94% |
| score=5 ceiling | 16.67% | 50.00% |
| 归一化熵 | 0.6284 | 0.4307 |
| E5 分数范围 | 0.07392 | 0.04502 |
| E5 方差 | 0.000552 | 0.000124 |
| DistilUSE 分数范围 | 0.65965 | 0.21968 |
| 单槽替换代理比例 | 33.33% | 56.25% |

supplement 的 E5 方差仅为 v1 的 22.47%，DistilUSE 方差仅为 13.49%。更关键的是，supplement 的人工分与 relation 完全重合：24 条 `equivalent` 全为 5，24 条 `factual_conflict` 全为 4；在任一 relation 内都没有人工分方差，所以 relation 内连续相关不可定义。这说明本轮 1–5 量表主要把“等价/冲突”压成两个相邻档，而没有为高相似区域提供足够的连续分辨率。

这组证据对“受限分布 × 粗量表压缩”的联合失配是强描述性支持；它不能证明哪一项单独造成 E5 overall 失败。

### 3.2 编码器关联与聚合敏感性

| 关联 | R1 v1 | R1 supplement | combined |
| --- | ---: | ---: | ---: |
| E5—人工 Spearman | 0.6320 | 0.1775 | 0.3968 |
| E5—人工 Kendall tau-b | 0.4719 | 0.1464 | 0.3176 |
| DistilUSE—人工 Spearman | 0.4873 | 0.4512 | 0.5010 |
| E5—DistilUSE Spearman | 0.7687 | 0.8672 | 0.8834 |

family-clustered bootstrap（固定 seed=20260829，10,000 次）给出：

- v1 E5—人工 Spearman 95% percentile 区间 `[0.4281, 0.7646]`；
- supplement 为 `[-0.0538, 0.4051]`；
- combined 为 `[0.2301, 0.5406]`；
- supplement DistilUSE—人工为 `[0.2377, 0.6419]`。

supplement 中 E5 overall 为 0.1775，但 short/long 分别为 0.3250/0.3612；zh/en 分别为 0.4300/0.0436；进一步按 length×language 分层时，short-zh/short-en 为 0.8504/0.8216，而 long-zh/long-en 为 0.3299/0.2309。没有稳定方向反转，但总体关联明显受 strata 混合影响。combined leave-one-length×language-out 的 E5 变化范围约为 `-0.0698` 到 `+0.0999`，支持预先条件化汇总的必要性，但不能事后选择有利 strata。

### 3.3 截断边界

E5 在 72 条人工样本中 0 条截断。DistilUSE 截断 24 条，全部来自 supplement long；其 Spearman 为 0.7344，而 12 条未截断 long 为 0.4842。这个表面差异不能解释为“截断有益”：截断状态与 cohort、文本长度、模板和评分分布完全混杂，样本也不是为截断效应随机设计。它只能说明 DistilUSE 通过并非足以排除截断影响，更不能把 DistilUSE 事后晋升为主编码器。

## 4. 五层证据—推断—尚不能区分

| 层次 | 证据与推断 | 尚不能区分 |
| --- | --- | --- |
| 标注一致性 | v1 QWK=0.9484、±1=100%；supplement QWK=1.0、48/48 exact。低标注一致性不支持作为主解释 | 高一致不等于量表在高相似区有足够分辨率 |
| 关系数据质量 | supplement 144/144 关系四字段 A/B exact，construction role 未用于真值。机械关系错标不支持作为直接原因 | 高一致不能证明 deterministic microfact 的生态多样性或外部效度 |
| 校准样本分布 | 自动分数范围/方差显著收缩，56.25% 为单槽替换代理，模板重复率 18.75%，人工分只剩 4/5 | range restriction、模板重复、单槽编辑和评分压缩在 R1 中相关，无法拆分单独因果 |
| 主编码器失配 | E5 supplement 相关显著低于 v1，而两编码器秩相关仍高 | 不能区分 E5 固有限制、受限分布、量表压缩、模板或交互；DistilUSE 不获晋升 |
| 聚合口径 | overall、length、language、length×language 关联差异大，LOSO 对 overall 有实质影响 | outcome-aware strata 不能证明哪种新汇总正确；只能在全新 R2 Dev 上事前冻结并一次验证 |

最可信的失配机制因此是：**R1 补充把高相似样本设计成高度受限、重复的微事实编辑，同时 1–5 人工量表在该区域退化为 relation 的 4/5 两档编码；全局连续 E5 排名与这种压缩后的人工尺度不再对齐。**证据强度对“分布受限”和“评分压缩”为强，对“聚合敏感”为中等，对“E5 本身不适配”为中低；单一因果仍不能确定。

## 5. 11/11 方法学谬误扫描

| 谬误 | 结论 |
| --- | --- |
| Simpson's paradox | `possible`：已比较总体与冻结 strata；无稳定反转，但有明显聚合衰减 |
| Ecological fallacy | `not_applicable`：不作个体或人口外推 |
| Berkson's paradox | `possible`：两批都是经过筛选的相似性审计框 |
| Collider bias | `not_applicable`：未作协变量调整 |
| Base-rate neglect | `not_applicable`：不作诊断概率主张 |
| Regression to the mean | `not_applicable`：无极端组前后测 |
| Survivorship bias | `not_detected`：全部锁定正式人工行均保留 |
| Look-elsewhere effect | `possible`：探索性 strata 较多，故全部报告且不提供 PASS |
| Garden of forking paths | `caution`：结果感知诊断；计划、输入补充和 mapping 均在统计前透明封存 |
| Correlation ≠ causation | `guarded`：只作关联描述，不写单因果 |
| Reverse causality | `not_applicable`：无方向性因果主张 |

覆盖率为 `11/11`。

## 6. 对 R2 的边界

本诊断支持在 R2 中同时解决分布设计、量表分辨率和条件化汇总，不能支持简单换模型、降低 0.50 门槛或把 DistilUSE 改成主编码器。R2 的具体建议见[研究协议草案](../plans/robust-fusion-r2-research-draft.md)和[相似度 measurement 草案](../plans/robust-fusion-r2-similarity-measurement-draft.md)。
