# Robust Fusion R1 → R2 继承与排除矩阵

> R2 状态：`PROTOCOL_APPROVED_RESULT_BEFORE_LOCAL_SEAL`。本矩阵说明正式继承边界，不修改 R1。

| 项目 | R1 状态 | R2 处理 | 理由/限制 |
| --- | --- | --- | --- |
| 正式题目 | 已冻结 | 原样继承 | 研究问题未变 |
| Dense/Learned Sparse/BM25 三路定义 | 已冻结 | 原样继承 | 相似度校准不改变 retrieval route |
| RQ1—RQ3、C1/C2/C3 角色 | 已冻结 | 原样继承 | 只更换测量研究 ID |
| `equivalent/factual_conflict/other_incorrect/unresolved` | 已冻结 | 原样继承 | relation schema 不变 |
| `S_qg(c)=max cosine(c,A_qg)` | R1 estimand | 数学 estimand 继承 | R2 改条件标准化与设计，不改参照对象 |
| E5/DistilUSE | R1 固定角色 | 正式继承主/审计角色与 exact revision | 不能按 R1 谁通过来换位；R2 一次冻结且不得模型赛马 |
| R1 v1+supplement 结果 | terminal `INCONCLUSIVE` | 永久保留、探索性引用 | 不合并到 R2 门槛或功效分母 |
| R1 全部 family/text/template | exposed Dev | hard exclude | 不得进入 R2 Dev、Gate A、Blind |
| R1 1–5 similarity 量表 | 高区压缩 | 重写为 7 点行为锚定草案 | 新 ID 透明披露，不追溯改写 R1 |
| 全局 E5 标准化/整体相关 | R1 未冻结成功 | 改为 length×language×dataset 条件标准化 | 必须在全新 R2 Dev 一次验证 |
| 60% 共同支持思想 | R1 固定 | 保留，在四个 length×language 聚合判定；12 个条件 cell 逐项诊断 | 小 cell 极值门禁在结果前模拟中不可辨识；60% 数值线、missing-as-miss 与 12-cell 标准化不变 |
| Gate A C1 连续交互/高相似差分 | R1 草案 | 原样继承科学定义 | 仅将曝光量换为 R2 合格的条件度量 |
| Gate A 两 Reranker×三数据集、4/6 正向 | R1 草案 | 原样继承 | 资格与功效仍需 R2 readiness 复核 |
| C2 10 项比较与三分边界 | R1 草案 | 原样继承 | similarity-only 比较器需按 R2 measurement 重签实现 |
| Gate B 11 项 nAUDC、3 项 Top1 安全 | R1 草案 | 原样继承 | R2 不提前开发 M1/A0/D1–D3 |
| Gate A 一次 Inconclusive 扩样 | R1 规则 | R2 需新 ID 下重新预注册 | R1 的 P2 补充不转移；R2 measurement 本身拟议无补样 |
| 旧 Gate A/Blind sealed inventory | 未读取/未授权 | 可继续保持未见，暂不授权 | 需 outcome-blind family-disjoint 与 measurement 资格审计 |
| 历史曝光 Blind v4/v5 | 已曝光 | 永久排除 | 不能改名进入 R2 |
