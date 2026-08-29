# Robust Fusion P2-01 Dev 相似度自动校准与盲审发包报告

> 记录：`ROBUST-FUSION-SIMILARITY-DEV-CALIBRATION-2026-08-29-v1`
> 日期：2026-08-29
> 状态：`AWAITING_HUMAN_SUBMISSIONS`
> 边界：只使用 Internal v6-Dev；Gate A/B 未运行，P2-01/P2-04 未完成。

## Material Passport

| 项目 | 内容 |
| --- | --- |
| Dev 输入 | `internal-v6-dev-route-evidence-v5-20260829` |
| route manifest SHA-256 | `a2ee6147a791903fa0aceae3be7f3b6a7f54277a58f5241cb62d1e944974734d` |
| route content root | `1bae0b158a16f5d0aab161cff28245283fd487c9a5f41f23a6c4d02305c57550` |
| adjudicated release manifest | `ad32fbb08a6b076dced1e438ff51060c46073b932cd259ff89beb157e5453bac` |
| 编码器资格 manifest | `931946bd244d794bf390d5c37f166308d010870b429919b1167131fd0ceb1f2a` |
| 自动制品 manifest | `b44d13f5a5e4f6bea2225ec8c29588db10a37ad1da124eb2d8ff7fb09f08454c` |
| 主编码器 | `intfloat/multilingual-e5-base@d128750597153bb5987e10b1c3493a34e5a4502a` |
| 独立审计编码器 | `sentence-transformers/distiluse-base-multilingual-cased-v2@bfe45d0732ca50787611c0fe107ba278c7f3f889` |
| 人工工作量 | A/B 各 24 行，物理隔离、无答案键 |

## 1. 自动部分结论

从 v5 的物理双视图中封存了 28 个 `query_uid × target_equivalence_group_id` 参照集合。每个集合恰含一条经双审仲裁的 `relevant_gold`；待测的等价候选没有被纳入自己的参照集合，因此不会机械产生 1.0。参照集合制品 SHA-256 为 `89e9a7d821e890705eb574dc8a5092f8796ac4520b18442cf49d583d32cdbefc`。

两个冻结编码器分别对同一 112 条 Chunk 编码，并保存 float32 向量、逐 Chunk 原始/规范化输入摘要、未截断 token 数、截断标记和向量摘要。E5 与 DistilUSE 向量文件摘要分别为 `876c5000b73f90207cd309e3083b220fb4adcbc4ba7b5bb7380edd2139b42998`、`65b138fea30c2e434f516d5788941e2900d2bb5851099bc1a78e9f408e5f29ba`。本批 112 条在 E5 512-token 与 DistilUSE 128-token 上均无截断；长/短仍按 E5 候选—参照 pair 的未截断 token 最大值中位数 50 分层，84 个待测候选为 short 48、long 36。

候选相似度制品包含 84 行：`equivalent=28`、`factual_conflict=28`、`other_incorrect=28`，并按四类冲突、长短、合成来源及编码器一致/分歧区域输出分层统计。其 SHA-256 为 `0a0962970a28724d48dad83619adb3b6252916361568e8f62e0d3621c435fb5e`。

核心文件在另一个输出目录完成第二次完整编码；参照集合、84 行相似度、两个向量矩阵、输入元数据、抽样 registry 和 A/B `pairs.csv` 逐字节一致。正式制品的独立 verifier 同时重算了 112 条主/审计向量摘要，并验证 24 个受管文件与盲包禁入字段。

## 2. 结果前统计规则及当前边界

数据源内标准化只使用合并后的 28 条等价和 28 条事实冲突候选，固定 `ddof=1`。Dev 预估均值为 `0.9841916433456961`，标准差为 `0.01442102645074964`；这些数值仍是待人工效度通过后才能接受的 provisional 值。

共同支持算法固定为两类观测范围的交集，并要求等价、冲突两侧覆盖率均不低于 60%。当前交集为 `[0.9843160362038024, 0.9955983802559442]`，覆盖率分别为 17.86% 和 57.14%，因此自动覆盖门禁失败。此前先尝试的关系内 q10–q90 交集为空；该尝试没有读取人工结果或 Gate 结果，失败目录原样保留，未据结果换模型或改 estimand。观测范围交集只避免小样本预裁剪制造空区间，60% 覆盖门禁负责阻止过窄交集被误写成有效共同支持。

解释性分带规则固定为合并等价/冲突候选的 pooled q25/q75，中间为模糊带；相邻敏感性固定为 q30/q70 与 q20/q80。当前 provisional 主边界为 low `≤0.9770479717675954`、high `≥0.9951423425431406`，中间只进入连续分析。自动制品生成时共同支持未通过且盲人工效度尚未返回，因此其 `formal_numeric_freeze_allowed=false`。后续真实仲裁已使人工效度 PASS，但共同支持仍 FAIL；该数值仍不得升级为 Gate A 的正式分带，详见[仲裁后效度报告](robust_fusion_similarity_human_review_2026_08_29.md)。

## 3. 盲人工效度包

抽样框在人工提交前固定为 84 个非参照候选。正式抽取 24 对，保证：等价/冲突/普通错误各 8；long/short 各 12；四类冲突均覆盖；E5/DistilUSE percentile-rank 一致区 11、分歧区 9、中间区 4。A/B 的行顺序和左右文本方向分别确定性扰动。

标注员目录只含 opaque `audit_id`、两段文本、统一说明与空白提交表；不含 Query、原始 Query/Chunk ID、关系/冲突类型、模型身份、分数、分带、来源角色或答案键。A 包 manifest SHA-256 为 `6a4ca9b07632aafb457586d91b5148a014bf105740a4488d90ccb2b7d25d33e9`；B 包为 `3b9e16262827d6e886215ae80ab8e32845aff85294021cbd4f8d0484c62a92db`。

人工量表为 1–5：1 表示不同主题/实体/事实槽；2 表示同领域但实体或事实槽不同；3 表示同实体/主题且部分事实槽或条件重合；4 表示同一事实槽且语义高度接近，允许关键事实或条件不同；5 表示近乎等价或紧密改写。A/B 另填 confidence、uncertain 与必要说明。

冻结的机械和效度规则见 `human_audit_rules.json`（SHA-256 `268598c122096874409cd7f81b6b3e175933b837d987c8d047fc1312afdd52a6`）：两份提交必须先锁后比；分差至少 2 或任一不确定必须仲裁；二次加权 κ 至少 0.60、相差不超过 1 分的比例至少 0.90；最终还须满足 E5 overall/长短 Spearman、DistilUSE overall Spearman 与最高分带人工近邻阈值。未通过时只能判 `FAIL` 或 `INCONCLUSIVE`，不得据提交更换编码器、改 estimand、放宽共同支持或重新切分分带。

## 4. 停止点

当前无需人工输入的工作已经完成。下一步只接受两名真实研究员各自生成的 `submission.csv`；Codex、模型或工具不得代填。收到两份提交后，执行顺序固定为：先锁定两份原始文件及摘要，再做机械校验和 A/B 比较，按冻结规则形成仲裁记录，最后判定人工效度及是否接受 provisional 标准化/分带数值。

在此之前状态保持 `AWAITING_HUMAN_SUBMISSIONS`，P2-01 与 P2-04 均不得标为完成，Gate A/B 保持未运行、未授权。
