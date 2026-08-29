# P2-01 Dev 相似度人工审阅与仲裁后效度报告

> 状态：`REVIEW_COMPLETE_FORMAL_FREEZE_BLOCKED`
> 范围：只审阅 Internal v6-Dev 的两份相似度人工提交与一份真实仲裁提交；Gate A/B、Reranker 效果与 M1 均未运行。

## Material Passport

| 字段 | 值 |
| --- | --- |
| Material ID | `ROBUST-FUSION-SIMILARITY-HUMAN-REVIEW-2026-08-29-v2` |
| Material Type | Human-study submission validation, adjudication and Dev measurement-validity analysis |
| Verification Status | `ANALYZED_FORMAL_FREEZE_BLOCKED` |
| 自动校准 manifest | `b44d13f5a5e4f6bea2225ec8c29588db10a37ad1da124eb2d8ff7fb09f08454c` |
| A 提交 SHA-256 | `c99af7d3b9d67e2c7a6cf697434ba37b4997c5774f2552189486e48a800b3563` |
| B 提交 SHA-256 | `d9aa18643f76db1c6f5bb0f33eaa21997cca393a8cf907d46196a9b005273a6f` |
| 提交锁 SHA-256 | `f6a87dea77ca754a5b622c7237c9da134e1d5176d2a52a3cd9297dc1c5e4499b` |
| 仲裁包 manifest | `6c215194227efc3d166168f5528c174cdb3a849ab74aefb08b0de4c017d1d98b` |
| 仲裁提交 SHA-256 | `888f0915a775e755f52de8a551d5de54877fd2e0345bf59a156c12b0b45e163d` |
| 仲裁锁 SHA-256 | `631d92814beb1436040330c9bab872bc8ed9da135a8b44fa9a85da8ff09161cf` |
| 最终制品 manifest | `463c31cbf0dbf112b8be087a42ce20239ea46b4729d9863498ca9a484a41647d` |

## 1. 先锁后比与机械校验

两份 `submission.csv` 在读取评分内容前完成文件大小、角色包 manifest 与 SHA-256 锁定。A/B 均提交 24/24 行；表头、`audit_id` 集合、唯一性、1–5 分枚举、置信度、不确定标志及不确定说明全部合法，机械错误为 0。

独立评分比较结果：

| 指标 | 结果 | 冻结门槛 | 判定 |
| --- | ---: | ---: | --- |
| 完全一致 | 21/24（87.5%） | 描述性 | — |
| ±1 分一致 | 24/24（100%） | ≥90% | PASS |
| 二次加权 κ | 0.9484240688 | ≥0.60 | PASS |

双人一致性门禁通过。冻结规则产生 8 条强制仲裁项；为获得每个样本的唯一最终 ordinal score，又纳入其余 1 条非一致项，形成 9 行最小仲裁包。

## 2. 仲裁提交核验

仲裁文件在读取内容前先按路径、大小和 SHA-256 建立独立锁；随后机械校验确认：9/9 行齐全，`audit_id` 与冻结仲裁集合完全相等且无重复，评分全部属于 1–5，`arbiter_id` 与理由均非空。9 行来自一名真实仲裁员；最短理由为 46 个字符。最终 24 行由 9 条 `human_arbiter` 分数与 15 条 A/B 完全一致分数组成，长/短各 12 行，`equivalent`、`factual_conflict`、`other_incorrect` 各 8 行。

仲裁锁固定原始提交，不修改 A/B 原始值。最终分数制品为 `final_scores.jsonl`，SHA-256 `899f610cfe1edf42079078186f71edefe611891b476dd33d937580db6fb4cb67`；最终判定为 `final_review.json`，SHA-256 `90ed2c7e930b3628f87529dfa876603aacf94a2eb292105a5f586d12f1433a71`。

## 3. 仲裁后人工测量效度

所有阈值均在正式人工提交前冻结，现按同一规则一次性报告：

| 指标 | 结果 | 冻结门槛 | 判定 |
| --- | ---: | ---: | --- |
| E5 overall Spearman | 0.6319511997 | ≥0.50 | PASS |
| E5 short Spearman | 0.5740743399 | ≥0.30 | PASS |
| E5 long Spearman | 0.5810872031 | ≥0.30 | PASS |
| DistilUSE overall Spearman | 0.4872876721 | ≥0.40 | PASS |
| E5 最高分带人工中位数 | 4.0 | ≥4.0 | PASS |
| E5 最高分带中评分≥4比例 | 100% | ≥70% | PASS |

因此 `human_measurement_decision=PASS`。这只说明冻结的 E5 主测量和 DistilUSE 独立审计在本次 24 对 Dev 分层审计框中通过人工效度阈值；不构成总体人口推断、因果结论或 Gate 结果。

## 4. 共同支持与正式冻结判定

自动共同支持区间仍为 `[0.9843160362038024, 0.9955983802559442]`，等价/冲突覆盖分别为 17.86%/57.14%，低于两侧各 60% 的冻结下限。人工效度 PASS 不能覆盖这个独立失败，也不能用于放宽下限、换编码器或改变 \(S_{qg}(c)\) estimand。

因此联合判定为 `combined_similarity_freeze_decision=INCONCLUSIVE`：provisional 均值/标准差和 q25/q75 分带不升级为正式数值，`formal_numeric_freeze_complete=false`，P2-01/P2-04 均保持未完成，`GATE_A_AUTHORIZATION: false`。

## 5. 统计解释与 11 项谬误扫描

本分析是冻结的、分层选择的 24 对 Dev 测量效度审计，Spearman 使用含并列值的平均秩；未预注册总体推断区间或 p 值，因此不补做事后显著性声明。

- Simpson：overall、short、long 方向均为正，冻结长度分层未见方向反转；关系层内部分数无方差，不能据此作关系内相关推断。
- 生态谬误：分析与表述单位均为候选—参照文本对，不外推个体层结论。
- Berkson：样本按关系、长度和编码器一致/分歧区域选择，存在选择框限制；结论只适用于该 Dev 审计框。
- Collider：未作协变量调整，不适用。
- 基率忽视：没有灵敏度、特异度或后验诊断概率主张，不适用。
- 均值回归：没有按极端值入组的前后测设计，不适用。
- 幸存者偏差：24/24 均有最终分数，无流失。
- Look-elsewhere：六项冻结阈值全部报告，没有只报告通过项。
- Forking paths：抽样、阈值和仲裁规则在提交前冻结；额外纳入全部非一致项已披露。
- 相关即因果：仅表述测量相关与效度，不使用因果措辞。
- 反向因果：无方向性因果主张，不适用。

覆盖：`11/11 checked`。唯一实质性警示是选择性 Dev 审计框，故结果应作描述性校准证据，而非总体效应证明。
