# Robust Fusion R2 到 Gate A 的 Delta Checklist

> `research_id`: `ROBUST-FUSION-R2-2026-08-29`
> 当前：`R2_AUTOMATIC_COMPLETE_AWAITING_FOUR_HUMAN_SUBMISSIONS`。本文记录进度，不授权 measurement finalizer、readiness 或 Gate。

## A. 研究与测量批准

- [x] 研究负责人批准 R2 独立 ID、R1 永久隔离和推荐 measurement 方向。
- [x] 将 draft 升为结果前正式协议，冻结 128-family 样本、功效、strata、编辑强度、dataset 配额、排除和唯一停止规则。
- [x] 冻结 7 点量表、A/B 盲包、relation/similarity 职责、仲裁和 missing-as-miss。
- [x] 冻结 E5/DistilUSE revision、tokenizer、截断、条件标准化和 caliper 实现；无模型赛马。
- [x] 建立 R1 全 family/text/template exclusion registry，并用测试拒绝 R1/Gate/Blind 泄漏。

## B. 全新 R2 Dev（一次性）

- [x] 在任何 R2 正文前封存 DeepSeek source-generation implementation、价格快照、128-slot registry、代码快照与授权模板；零网络 dry-run 为 384 个唯一信封、理论 peak `$3.3792`、硬熔断 `$5.00`。
- [x] 永久封存 v2 prompt-contract failure 与 v3 聚合无进展现场；两者均为 source implementation diagnostic，不是数据/measurement/Gate 结果。
- [x] 协调方批准并在结果前封存最小 v4 分阶段 prompt orchestration；v4 单次正式命令在 1/128 接受后因同一 slot/stage 相同响应六次而 fail-closed。
- [x] 协调方批准并在任何新响应前封存保守 v5；逐字节继承并 hard-lock R2SRC-001，从 R2SRC-002 的全新 R 开始，substantive retry 与 crash-consistent audit 目标测试和全量非集成测试通过。
- [x] v5 单次正式命令在 R2SRC-002/R 形成 attempt-scoped lock 后，E 的两个响应 hash 分别出现 6/4 次且均因 normalized 后等于 reference 机械失败；第六次重复在 `CALL_COMPLETED` 后触发 frozen breaker，命令 fail-closed 且未重跑。
- [x] 协调方批准并在任何 v6 响应前封存 outcome-aware engineering recovery：R→EP→E→C、固定 `deepseek-v4-pro`、Flash/Pro provenance、plan exhaustion 与全部 breaker 均结果前写定。
- [x] v6 单次正式命令永久接受 R2SRC-002；R2SRC-003 的 R/EP/E 机械通过，但 C 同一 response hash 六次且 normalized 等于 equivalent，按 frozen breaker fail-closed。accepted ledger 为 2/128，未重跑、未回退 Flash。
- [x] 负责人授权 Codex source v7；逐字节 hard-lock 001/002，003–128 append-only 直接撰写，首个机械 PASS 永久接受，DeepSeek v2–v6 现场继续只读。
- [x] 完成 128 个全新 family-disjoint Dev family；accepted ledger 与失败 attempt/hash 全部保留，未用外部生成服务或模型分数调文。
- [x] 在看编码器分数前锁定全部正文、来源、strata、冲突类型、编辑强度和固定分母。旧 v7 final lock 的同-family template 作用域缺陷 fail-closed 留痕；v7.1 仅修复 cross-family 执行作用域并先封存，不改 parser/prereg/accepted rows。
- [x] 单次计算冻结 E5/DistilUSE 并封存 provenance、向量、输入/token/截断与分数哈希；未按分数替换候选。
- [x] 生成双盲 A/B relation 与 similarity 包；每位研究员 512 行，当前四份 `submission.csv` 均不存在。
- [ ] 先锁提交再校验/仲裁；一次性执行 measurement finalizer。
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

安排两名真实研究员独立完成各自 relation 256 + similarity 256 = 512 行。A 只使用 `human_packages/relation/annotator_a/` 与 `human_packages/similarity/annotator_a/`；B 只使用对应 `annotator_b/` 目录。各自复制 `submission_template.csv` 为 `submission.csv` 后填写全部行，不改表头/audit_id，不查看另一位或 facilitator 目录。收到四份提交后先锁后验；在此之前不得 finalizer/readiness/Gate。
