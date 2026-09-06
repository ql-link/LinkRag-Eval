# Robust Fusion R2 到 Gate A 的 Delta Checklist

> `research_id`: `ROBUST-FUSION-R2-2026-08-29`
> 当前：`AWAITING_HUMAN_ADJUDICATION`。四份 A/B 提交已锁定并完成仲裁前机械审阅；readiness 与 Gate 不授权。

## A. 研究与测量批准

- [x] 研究负责人批准 R2 独立 ID、R1 永久隔离和推荐 measurement 方向。
- [x] 将 draft 升为结果前正式协议，冻结 128-family 样本、功效、strata、编辑强度、dataset 配额、排除和唯一停止规则。
- [x] 冻结 7 点量表、A/B 盲包、relation/similarity 职责、仲裁和 missing-as-miss。
- [x] 冻结 E5/DistilUSE revision、tokenizer、截断、条件标准化和 caliper 实现；无模型赛马。
- [x] 建立 R1 全 family/text/template exclusion registry，并用测试拒绝 R1/Gate/Blind 泄漏。

## B. 全新 R2 Dev（一次性）

- [x] 负责人授权 Codex source v7；001/002 继承既有首个机械合格对象，003–128 以 append-only 首个机械 PASS 完成。旧 DeepSeek source v1–v6 计划与运行现场已按负责人 2026-08-30 的明确指令物理删除，不再列为活动制品。
- [x] 完成 128 个全新 family-disjoint Dev family；v7 accepted ledger 与失败 attempt/hash 保留，未用编码器分数或人工结果调文。
- [x] 在看编码器分数前锁定全部正文、来源、strata、冲突类型、编辑强度和固定分母。旧 v7 final lock 的同-family template 作用域缺陷 fail-closed 留痕；v7.1 仅修复 cross-family 执行作用域并先封存，不改 parser/prereg/accepted rows。
- [x] 单次计算冻结 E5/DistilUSE 并封存 provenance、向量、输入/token/截断与分数哈希；未按分数替换候选。
- [x] 生成双盲 A/B relation 与 similarity 包；每位研究员 512 行。
- [x] 四份真实提交在答案解析前完成 raw-byte hash 锁；锁后 schema/ID/身份/枚举校验通过。relation 7 行、similarity 96 行需真实人类仲裁，物理隔离包已封存。
- [x] 为新仲裁员建立并校验 `human_tasks/r2-adjudication/` 浅入口；指南和交接不再暴露深层 canonical run 路径，relation/similarity 仍写入唯一冻结包。
- [ ] 安排一名新的真实研究员独立完成 relation 7 行与 similarity 96 行仲裁；收到提交后先锁后验。
- [ ] 仲裁机械校验通过后，才可按冻结协议形成唯一人工记录并一次性运行 measurement finalizer。
- [ ] 只有完整性、一致性、分辨率、人工 caliper、共同支持、条件 E5 人工效度全部 PASS 才冻结 measurement。

## C. Gate A 资格增量

- [x] 对旧 sealed Gate A/Blind inventory 做 outcome-blind 资格审计；未读取确认性排序结果，当前因 family/provenance/strata 元数据不足为 `NOT_ELIGIBLE_METADATA_INSUFFICIENT`。
- [ ] 证明旧 Gate A/Blind 与 R1、R2 Dev、彼此之间按 Query/文档族/版本/反事实模板 family 全隔离；不合格项不能补名复用。
- [ ] 将 R2 条件 measurement 字段加入候选快照 schema，并完成 method/evaluation view 泄漏测试。
- [ ] 冻结两个 Reranker 家族、三数据集有效分母、自然来源最低覆盖和 Gate A 可构造率。
- [ ] 用 R2 Dev 方差完成 Gate A C1/C2 功效；冻结最大 Query 数、每数据集最低 family、人工/API/GPU 预算。
- [ ] 冻结 `epsilon_int`、`epsilon_surf,A`、`delta_nat`、置换容差及全部 PASS/INCONCLUSIVE/FAIL。
- [ ] 冻结 C1 pooled 等权、C2 10 项家族、4/6 正向单元、2×2 相邻边界和一次 Gate A Inconclusive 扩样规则。
- [ ] 形成 clean commit/tag、root manifest 和外部时间戳 receipt；完成独立 readiness 审计。

## D. 仍然禁止

- [ ] 在上述全部完成前不运行 readiness 或 Gate A/B。
- [ ] Gate A=Go 前不开发 D1–D3、A0、M1。
- [ ] 不读取 Blind，不重用 R1 family，不把 R2 Dev 当 Gate 证据。
- [ ] 不因 R2 Dev 结果换模型、降阈值、删 strata、删数据集或追加第二批 measurement Dev。

## 当前唯一下一动作

安排一名新的真实研究员，只从项目根目录进入 `human_tasks/r2-adjudication/START_HERE.html`，并在 `human_tasks/r2-adjudication/relation/` 与 `human_tasks/r2-adjudication/similarity/` 分别填写 7 行与 96 行。不得追踪链接寻找其他版本，不得查看 A/B 以外的结果或任何模型分数；收到两份 `submission.csv` 后必须先锁后验。在此之前不得运行 measurement finalizer、readiness 或 Gate。
