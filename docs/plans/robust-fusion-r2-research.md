# 高相似度干扰下检索增强生成的多路来源感知鲁棒融合方法研究：R2 正式协议

> `research_id`: `ROBUST-FUSION-R2-2026-08-29`  
> `record_id`: `ROBUST-FUSION-RESEARCH-R2-2026-08-29-v1`  
> 状态：`RESULT_BEFORE_PROTOCOL_READY_FOR_LOCAL_SEAL`

正式题目、Dense/Learned Sparse/BM25 三路来源、RQ1—RQ3 与 C1—C3 的科学角色原样继承。R1/v29 的 v1+唯一补充终局 `INCONCLUSIVE` 永久成立；R1 的 Query/document/version/template family 与正文只可作探索性设计证据，并以机器注册表 hard exclude，不进入 R2 Dev、Gate A 或 Blind。

R2 正式采用方案 B：匹配 caliper + `length×language×dataset` 条件 E5 + 7 点行为锚定量表。固定 128 个全新 family-disjoint Dev families；每 family 一个 equivalent 和一个 factual_conflict 候选，共 256 候选。每位研究员独立完成 relation 256 行与 similarity 256 行，合计 512 行。只有本 measurement 全部 PASS 才能进入 readiness；FAIL/INCONCLUSIVE 均为 R2 measurement terminal，不补样、不换模型、不降阈值。

三个 calibration dataset role 固定为 `public_general`、`public_domain`、`internal_control`；它们是 R2 测量来源层，不改写 Gate 的 T2Ranking/cMedQA2/Internal Stress v6 三数据集定义。配额 44/42/42，12 个 dataset×length×language cell 各 10–11 family，四个 length×language 聚合各 32。每聚合四类冲突各 8，每类四级编辑强度各 2。family key 为规范化 query、reference、provenance ID 的 SHA-256；任一文本或模板与 R1 相同，或规范化字符 5-gram Jaccard ≥0.82，均拒绝。

四级编辑强度在看分数前固定：1=局部词面替换；2=短语级复述；3=句法重排并保留事件框架；4=多处局部复述但不改变目标命题框架。每级都必须同时构造 equivalent 与 conflict，禁止按编码器得分保留或替换。

有效功效模拟 v2 使用 400×199 固定重采样并严格实现每个 length×language 的 4×4×2 正交轮转：ρ=.30 完整错误通过 0%，ρ=.50 通过 52.5%，规划替代值 ρ=.60 通过 91.25%（MCSE 1.41%），ρ=.65 通过 92.75%。因此 n=128 对 `.60` 的规划替代值可辨识；`.50` 只是不应被误写为高功效的点估计门槛。v1 因 frame 把 conflict type 与 edit level 错误耦合，已在正式预注册前永久标记 `INVALID_FOR_PREREGISTRATION`，结果保留但不作证据。两版模拟都只含合成 ordinal outcome，不是研究结果。

R2 Dev 只能运行一次。正文、来源、strata、固定分母、排除结果先锁；随后单次运行本地冻结 E5/DistilUSE。任何缺失、无效、未决或不可估都保留在固定分母并 fail-closed。评分者不得看到模型分数、分带、construction role 或希望提升的区域。relation 与 similarity 物理分包；先锁 A/B 提交再比较，差异与 uncertain 只能由真实人类仲裁。

旧 Gate A/Blind 只允许 outcome-blind 元数据资格审计；历史 Blind v4/v5 永久排除。资格审计通过也只保留未见身份，不授权 readiness 或 Gate。正式 measurement PASS 后仍须独立 readiness；本协议禁止提前运行 Gate A/B、Reranker 效果、D1–D3、A0 或 M1。
